# ABOUTME: Stores and retrieves click-point calibrations for Jarvis search bars.
# Supports multiple named targets (effects panel search box, transcript search bar, etc.).
# On first use for a target, opens a fullscreen picker so the user clicks once.
# Coordinates are saved per-target and reused automatically.
#
# Thread-safety: Tkinter must run on the main thread.  When called from a
# background thread (e.g. the Jarvis voice loop), run_picker() spawns a
# subprocess so the GUI gets a fresh main thread.

import argparse
import ctypes
import json
import subprocess
import sys
import threading
import tkinter as tk
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageTk

# ---------------------------------------------------------------------------
# Calibration file paths — one JSON per target
# ---------------------------------------------------------------------------

_EFFECTS_CALIB_FILE  = Path("ImageReference") / ".search_box.json"   # effects panel search
_SEARCH_BAR_FILE     = Path("ImageReference") / ".search_bar.json"    # transcript / find bar

# Keep the old name as an alias so existing callers don't break
_CALIB_FILE = _EFFECTS_CALIB_FILE


# ---------------------------------------------------------------------------
# Load / save  (both accept an optional calib_file so callers can target
# either calibration without duplicating code)
# ---------------------------------------------------------------------------

def load(calib_file: Path | None = None) -> tuple[int, int] | None:
    """Return (x, y) from *calib_file*, or None if missing/corrupt."""
    if calib_file is None:
        calib_file = _EFFECTS_CALIB_FILE
    try:
        with open(calib_file) as f:
            d = json.load(f)
        return int(d["x"]), int(d["y"])
    except Exception:
        return None


def save(x: int, y: int, calib_file: Path | None = None) -> None:
    """Persist (x, y) to *calib_file*."""
    if calib_file is None:
        calib_file = _EFFECTS_CALIB_FILE
    calib_file.parent.mkdir(parents=True, exist_ok=True)
    with open(calib_file, "w") as f:
        json.dump({"x": x, "y": y}, f, indent=2)
    print(f"[calibration] Saved ({x}, {y})  →  {calib_file.name}")


# ---------------------------------------------------------------------------
# Screenshot helper (DPI-aware, same as image_matcher.py)
# ---------------------------------------------------------------------------

def _set_dpi_aware() -> None:
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            pass


def _grab_screenshot() -> np.ndarray:
    try:
        import win32gui, win32ui, win32con
        hdc   = win32gui.GetDC(0)
        dc    = win32ui.CreateDCFromHandle(hdc)
        memdc = dc.CreateCompatibleDC()
        w = ctypes.windll.user32.GetSystemMetrics(0)
        h = ctypes.windll.user32.GetSystemMetrics(1)
        bmp = win32ui.CreateBitmap()
        bmp.CreateCompatibleBitmap(dc, w, h)
        memdc.SelectObject(bmp)
        memdc.BitBlt((0, 0), (w, h), dc, (0, 0), win32con.SRCCOPY)
        info = bmp.GetInfo()
        data = bmp.GetBitmapBits(True)
        img  = np.frombuffer(data, dtype=np.uint8).reshape(
            info["bmHeight"], info["bmWidth"], 4
        )
        memdc.DeleteDC()
        win32gui.DeleteObject(bmp.GetHandle())
        win32gui.ReleaseDC(0, hdc)
        return cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)
    except Exception:
        import pyautogui
        shot = pyautogui.screenshot()
        return cv2.cvtColor(np.array(shot), cv2.COLOR_RGB2BGR)


# ---------------------------------------------------------------------------
# Fullscreen click-picker
# ---------------------------------------------------------------------------

class _ClickPicker:
    """Dim the screen and let the user click exactly one point."""

    def __init__(self, screenshot_bgr: np.ndarray,
                 prompt_text: str = "Click on the target  •  ESC to cancel"):
        self.h, self.w = screenshot_bgr.shape[:2]
        self.result: tuple[int, int] | None = None

        # Root window must exist before PhotoImage
        self.root = tk.Tk()
        self.root.overrideredirect(True)
        self.root.geometry(f"{self.w}x{self.h}+0+0")
        self.root.attributes("-topmost", True)

        rgb = cv2.cvtColor(screenshot_bgr, cv2.COLOR_BGR2RGB)
        self.photo = ImageTk.PhotoImage(Image.fromarray(rgb))

        self.canvas = tk.Canvas(
            self.root, width=self.w, height=self.h,
            cursor="crosshair", highlightthickness=0,
        )
        self.canvas.pack()
        self.canvas.create_image(0, 0, anchor="nw", image=self.photo)

        # Semi-transparent dark overlay
        self.canvas.create_rectangle(
            0, 0, self.w, self.h,
            fill="black", stipple="gray25", outline=""
        )

        # Centred instruction banner
        bw, bh = max(len(prompt_text) * 10, 500), 44
        bx, by = self.w // 2 - bw // 2, 20
        self.canvas.create_rectangle(bx, by, bx + bw, by + bh,
                                     fill="#1a1a1a", outline="#444444", width=1)
        self.canvas.create_text(
            self.w // 2, by + bh // 2,
            text=prompt_text,
            fill="white", font=("Segoe UI", 13, "bold"),
        )

        self.canvas.bind("<ButtonPress-1>", self._on_click)
        self.root.bind("<Escape>", lambda _: self.root.destroy())

    def _on_click(self, event):
        x, y = event.x, event.y
        self.result = (x, y)

        # Brief confirmation dot before closing
        r = 10
        self.canvas.create_oval(x - r, y - r, x + r, y + r,
                                 outline="#00FF00", fill="#00FF00", width=2)
        self.canvas.create_oval(x - r - 6, y - r - 6, x + r + 6, y + r + 6,
                                 outline="#00FF00", width=2)
        self.canvas.create_text(
            x, y + r + 16, anchor="n",
            text=f"({x}, {y})  ✓",
            fill="#00FF00", font=("Segoe UI", 11, "bold"),
        )
        self.root.after(700, self.root.destroy)

    def run(self) -> tuple[int, int] | None:
        self.root.mainloop()
        return self.result


# ---------------------------------------------------------------------------
# Internal: GUI — must be called from the main thread
# ---------------------------------------------------------------------------

def _run_gui_direct(calib_file: Path | None = None,
                    prompt_text: str | None = None) -> None:
    """Run the picker on the calling thread (must be main thread).
    Saves result to *calib_file* if the user clicks; does nothing on ESC.
    """
    if calib_file is None:
        calib_file = _EFFECTS_CALIB_FILE
    if prompt_text is None:
        prompt_text = "Click on the Effects panel search box  •  ESC to cancel"

    _set_dpi_aware()
    shot   = _grab_screenshot()
    picker = _ClickPicker(shot, prompt_text=prompt_text)
    result = picker.run()

    if result is None:
        print("[calibration] Picker cancelled — no change.")
        return
    x, y = result
    save(x, y, calib_file)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def run_picker(calib_file: Path | None = None,
               prompt_text: str | None = None) -> tuple[int, int] | None:
    """Open the fullscreen click-picker, save the result, return (x, y).

    Thread-safe: if called from a background thread the GUI is spawned in a
    separate subprocess (Tkinter requires the main thread).  Blocks until the
    subprocess exits, then reads the saved coordinates.

    Returns the (possibly unchanged) calibration, or None if nothing is saved.
    """
    if calib_file is None:
        calib_file = _EFFECTS_CALIB_FILE
    if prompt_text is None:
        prompt_text = "Click on the Effects panel search box  •  ESC to cancel"

    print(f"[calibration] Opening picker — {prompt_text}")

    import mouse_tracker
    with mouse_tracker.suppress_clicks():
        if threading.current_thread() is threading.main_thread():
            _run_gui_direct(calib_file, prompt_text)
        else:
            # Background thread — spawn subprocess so Tkinter gets a proper main thread.
            print("[calibration] (Spawning GUI subprocess — Tkinter requires the main thread)")
            subprocess.run(
                [
                    sys.executable, __file__,
                    "--picker",
                    "--file",   str(calib_file),
                    "--prompt", prompt_text,
                ],
                check=False,
            )

    pos = load(calib_file)
    if pos:
        print(f"[calibration] Position is {pos}")
    else:
        print("[calibration] Picker was cancelled or failed — no calibration saved.")
    return pos


def get_or_calibrate(calib_file: Path | None = None,
                     prompt_text: str | None = None) -> tuple[int, int]:
    """Return the saved position for *calib_file*, running the picker if none exists.

    Raises RuntimeError if the picker is also cancelled (no calibration at all).
    """
    if calib_file is None:
        calib_file = _EFFECTS_CALIB_FILE
    if prompt_text is None:
        prompt_text = "Click on the Effects panel search box  •  ESC to cancel"

    pos = load(calib_file)
    if pos is not None:
        return pos

    print(f"[calibration] No calibration for {calib_file.name} — opening picker.")
    pos = run_picker(calib_file, prompt_text)
    if pos is None:
        raise RuntimeError(
            f"Not calibrated: {calib_file.name}\n"
            f"Run:  python search_calibration.py\n"
            f"or use the 'recalibrate' / 'recalibrate search' voice command."
        )
    return pos


# ---------------------------------------------------------------------------
# Convenience wrappers for each named target
# ---------------------------------------------------------------------------

def get_or_calibrate_effects() -> tuple[int, int]:
    """Effects panel search box (used by _effects_search)."""
    return get_or_calibrate(
        _EFFECTS_CALIB_FILE,
        "Click on the Effects panel search box  •  ESC to cancel",
    )


def get_or_calibrate_search_bar() -> tuple[int, int]:
    """Transcript / Find search bar (used by the 'search' voice command)."""
    return get_or_calibrate(
        _SEARCH_BAR_FILE,
        "Click on the search bar  •  ESC to cancel",
    )


def run_effects_picker() -> tuple[int, int] | None:
    return run_picker(
        _EFFECTS_CALIB_FILE,
        "Click on the Effects panel search box  •  ESC to cancel",
    )


def run_search_bar_picker() -> tuple[int, int] | None:
    return run_picker(
        _SEARCH_BAR_FILE,
        "Click on the search bar  •  ESC to cancel",
    )


# ---------------------------------------------------------------------------
# Standalone entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Jarvis click-point calibration picker")
    parser.add_argument("--picker",  action="store_true",
                        help="Run the GUI directly (called by subprocess)")
    parser.add_argument("--file",    type=str, default=None,
                        help="Calibration JSON file path")
    parser.add_argument("--prompt",  type=str, default=None,
                        help="Instruction text shown in the overlay")
    parser.add_argument("--target",  type=str, default="effects",
                        choices=["effects", "search"],
                        help="Named target shortcut (effects or search)")
    args = parser.parse_args()

    # Resolve calib_file: explicit --file wins, then --target shortcut
    if args.file:
        calib_file = Path(args.file)
    elif args.target == "search":
        calib_file = _SEARCH_BAR_FILE
    else:
        calib_file = _EFFECTS_CALIB_FILE

    prompt_text = args.prompt  # None → _run_gui_direct picks a default

    if args.picker:
        # Called by run_picker() subprocess — run GUI directly on this main thread
        _run_gui_direct(calib_file, prompt_text)
    else:
        # Direct user invocation
        current = load(calib_file)
        if current:
            print(f"[calibration] Current position ({calib_file.name}): {current}")
        _run_gui_direct(calib_file, prompt_text)
