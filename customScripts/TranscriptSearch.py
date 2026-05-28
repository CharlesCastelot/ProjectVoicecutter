"""TranscriptSearch — click the Premiere Pro transcript search bar and type text.

Called by VoiceCutter when a parameterised "Search" command is triggered:
    python TranscriptSearch.py "Charles is doing great"

Strategy (in order):
  1. UIA accessibility tree — find the Edit control named 'UI_TextEdit' directly.
     Fast, reliable, and unaffected by whatever text is already in the box.
  2. Image matching fallback — template-match against Transcript_Search.png /
     Transcript_Search_Select.png if UIA is unavailable.
"""
import ctypes
import ctypes.wintypes
import json
import sys
import time
from pathlib import Path

import cv2
import numpy as np
import pyautogui

# ── DPI detection ─────────────────────────────────────────────────────────── #
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)   # PER_MONITOR_DPI_AWARE
except Exception:
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass


def _get_primary_dpi() -> float:
    try:
        pt = ctypes.wintypes.POINT(0, 0)
        hmon = ctypes.windll.user32.MonitorFromPoint(pt, 1)
        dpi_x = ctypes.c_uint(0)
        dpi_y = ctypes.c_uint(0)
        ctypes.windll.shcore.GetDpiForMonitor(hmon, 0, ctypes.byref(dpi_x), ctypes.byref(dpi_y))
        return float(dpi_x.value)
    except Exception:
        try:
            return float(ctypes.windll.user32.GetDpiForSystem())
        except Exception:
            return 96.0


_dpi = _get_primary_dpi()
_DPI_SCALE = _dpi / 96.0

# ── Scale cache (same logic as image_matcher.py) ──────────────────────────── #
_CACHE_FILE = Path(__file__).parent.parent / "ImageReference" / ".scale_cache.json"
_scale_cache: dict[str, float] = {}


def _load_cache() -> None:
    global _scale_cache
    try:
        with open(_CACHE_FILE) as f:
            _scale_cache = json.load(f)
    except Exception:
        _scale_cache = {}


def _save_scale(key: str, scale: float) -> None:
    _scale_cache[key] = round(scale, 4)
    try:
        _CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(_CACHE_FILE, "w") as f:
            json.dump(_scale_cache, f, indent=2)
    except Exception:
        pass


def _cache_key(path: Path) -> str:
    return f"{_dpi:.0f}:{path.as_posix()}"


_load_cache()


# ── Win32 GDI screenshot (physical pixels, DPI-correct) ───────────────────── #
def _grab_screenshot() -> np.ndarray:
    try:
        import win32gui, win32ui, win32con
        hdc = win32gui.GetDC(0)
        dc = win32ui.CreateDCFromHandle(hdc)
        memdc = dc.CreateCompatibleDC()
        w = ctypes.windll.user32.GetSystemMetrics(0)
        h = ctypes.windll.user32.GetSystemMetrics(1)
        bmp = win32ui.CreateBitmap()
        bmp.CreateCompatibleBitmap(dc, w, h)
        memdc.SelectObject(bmp)
        memdc.BitBlt((0, 0), (w, h), dc, (0, 0), win32con.SRCCOPY)
        info = bmp.GetInfo()
        data = bmp.GetBitmapBits(True)
        img = np.frombuffer(data, dtype=np.uint8).reshape(
            info["bmHeight"], info["bmWidth"], 4
        )
        memdc.DeleteDC()
        win32gui.DeleteObject(bmp.GetHandle())
        win32gui.ReleaseDC(0, hdc)
        return cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)
    except Exception:
        return cv2.cvtColor(np.array(pyautogui.screenshot()), cv2.COLOR_RGB2BGR)


# ── Multi-scale matching with cache hint ──────────────────────────────────── #
def _multiscale_match(
    screen_bgr: np.ndarray,
    template: np.ndarray,
    hint_scale: float | None = None,
):
    """Wide-range multi-scale match with a fast grayscale-only cache path.

    Pass 1: exact cached scale, grayscale only (1 matchTemplate call).
    Pass 2: small 5-scale band around cached scale, grayscale only.
    Pass 3: full 0.4×–2.5× sweep in color+grayscale (first run / cache miss).
    """
    base_h, base_w = template.shape[:2]
    screen_h, screen_w = screen_bgr.shape[:2]
    best_val, best_loc, best_scale = 0.0, (0, 0), _DPI_SCALE

    screen_gray = cv2.cvtColor(screen_bgr, cv2.COLOR_BGR2GRAY)
    tmpl_gray   = cv2.cvtColor(template,   cv2.COLOR_BGR2GRAY)

    def _try_gray(scales):
        nonlocal best_val, best_loc, best_scale
        for scale in scales:
            w = int(base_w * scale)
            h = int(base_h * scale)
            if w >= screen_w or h >= screen_h or w < 4 or h < 4:
                continue
            interp = cv2.INTER_AREA if scale < 1.0 else cv2.INTER_LINEAR
            scaled_g = cv2.resize(tmpl_gray, (w, h), interpolation=interp)
            _, val_g, _, loc_g = cv2.minMaxLoc(
                cv2.matchTemplate(screen_gray, scaled_g, cv2.TM_CCOEFF_NORMED))
            if val_g > best_val:
                best_val, best_loc, best_scale = val_g, loc_g, scale

    def _try_color_and_gray(scales):
        nonlocal best_val, best_loc, best_scale
        for scale in scales:
            w = int(base_w * scale)
            h = int(base_h * scale)
            if w >= screen_w or h >= screen_h or w < 4 or h < 4:
                continue
            interp = cv2.INTER_AREA if scale < 1.0 else cv2.INTER_LINEAR
            scaled_c = cv2.resize(template,  (w, h), interpolation=interp)
            scaled_g = cv2.resize(tmpl_gray, (w, h), interpolation=interp)
            _, val_c, _, loc_c = cv2.minMaxLoc(
                cv2.matchTemplate(screen_bgr,  scaled_c, cv2.TM_CCOEFF_NORMED))
            _, val_g, _, loc_g = cv2.minMaxLoc(
                cv2.matchTemplate(screen_gray, scaled_g, cv2.TM_CCOEFF_NORMED))
            val, loc = (val_c, loc_c) if val_c >= val_g else (val_g, loc_g)
            if val > best_val:
                best_val, best_loc, best_scale = val, loc, scale

    # Use the cached scale when available; fall back to the device's DPI scale
    # so first-time images on the same machine still hit Pass 1 or 2 rather
    # than always paying the full sweep cost.
    effective_hint = hint_scale if hint_scale is not None else _DPI_SCALE

    # Pass 1: exact scale — 1 call
    _try_gray([effective_hint])
    if best_val >= 0.70:
        return best_val, best_loc, int(base_w * best_scale), int(base_h * best_scale), best_scale

    # Pass 2: narrow band — 5 calls
    _try_gray(np.linspace(max(0.3, effective_hint - 0.1), effective_hint + 0.1, 5))
    if best_val >= 0.70:
        return best_val, best_loc, int(base_w * best_scale), int(base_h * best_scale), best_scale

    # Pass 3: full wide search (only if DPI guess was wrong)
    coarse = np.linspace(0.4, 2.5, 18)
    fine   = np.linspace(max(0.4, _DPI_SCALE - 0.25), _DPI_SCALE + 0.25, 12)
    _try_color_and_gray(np.unique(np.concatenate([coarse, fine])))

    return best_val, best_loc, int(base_w * best_scale), int(base_h * best_scale), best_scale


# ── Paths ─────────────────────────────────────────────────────────────────── #
_IMAGES_DIR = Path(__file__).parent.parent / "ImageReference" / "Images"
SEARCH_BAR_IMAGE        = _IMAGES_DIR / "Transcript_Search.png"
SEARCH_BAR_IMAGE_SELECT = _IMAGES_DIR / "Transcript_Search_Select.png"
MATCH_THRESHOLD  = 0.70

# Caches the screen coordinates found by UIA so subsequent calls are instant.
# Delete this file if you move/resize the transcript panel.
_UIA_CACHE_FILE = Path(__file__).parent.parent / "ImageReference" / ".uia_cache.json"


def _load_uia_cache() -> dict:
    try:
        with open(_UIA_CACHE_FILE) as f:
            return json.load(f)
    except Exception:
        return {}


def _save_uia_cache(data: dict) -> None:
    try:
        _UIA_CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(_UIA_CACHE_FILE, "w") as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        print(f"[TranscriptSearch] UIA cache write failed: {e}")


# ── Primary: UIA accessibility tree ──────────────────────────────────────── #

# Known path from Accessibility Insights — same for all Premiere Pro installs.
# Each entry is the window_text() of the node at that level.
_TRANSCRIPT_PATH = [
    "WorkspaceFrame",
    "TabPanelContainer",
    "dvauxpuiUXPPanel",
    "OS_ViewContainer",
    "OS_EditText",
]


def _step_down(root, titles: list[str]):
    """Walk a known path using direct children only at every level.

    If multiple siblings share the same title (e.g. several TabPanelContainer
    nodes under WorkspaceFrame), each candidate is tried in turn before giving
    up — so the correct branch is always found without a full recursive search.
    Cost is O(direct children per level × duplicate count), typically < 100
    total node touches for a full Premiere workspace.
    """
    def _walk(current, remaining):
        if not remaining:
            return current
        title = remaining[0]
        rest  = remaining[1:]
        actual_names = []
        try:
            children = current.children()
        except Exception as e:
            print(f"[TranscriptSearch]     step '{title}': children() failed — {e}")
            return None
        for child in children:
            try:
                name = child.window_text()
                actual_names.append(name)
                if name == title:
                    result = _walk(child, rest)
                    if result is not None:
                        return result   # this branch works — done
            except Exception:
                continue
        # Every candidate with this title was tried and none led to the full path
        preview = actual_names[:10]
        more    = f" … (+{len(actual_names)-10} more)" if len(actual_names) > 10 else ""
        print(f"[TranscriptSearch]     step '{title}': not found in any branch. "
              f"Actual children: {preview}{more}")
        return None

    return _walk(root, titles)


def _shallow_find(root, title: str, max_depth: int = 3):
    """BFS up to max_depth levels deep looking for a node by window_text().

    Faster than a full recursive search when the target is known to be shallow.
    Returns the element wrapper or None.
    """
    from collections import deque
    queue = deque([(root, 0)])
    while queue:
        node, depth = queue.popleft()
        if depth > max_depth:
            break
        try:
            for child in node.children():
                try:
                    if child.window_text() == title:
                        return child
                    if depth + 1 <= max_depth:
                        queue.append((child, depth + 1))
                except Exception:
                    continue
        except Exception:
            continue
    return None


def _find_via_uia() -> tuple[int, int] | None:
    """Locate the transcript search box via Premiere Pro's accessibility tree.

    Fast path : returns cached (x, y) instantly if available.
    Search path: walks _TRANSCRIPT_PATH step by step through direct children
                 only — near-instant since each level has only a handful of
                 children instead of thousands of descendants.
    Fallback   : full recursive search if any path step name has changed.

    Delete ImageReference/.uia_cache.json if the panel is moved or resized.
    """
    import time as _time

    # ── Fast path: cached coordinates ────────────────────────────────────── #
    cache = _load_uia_cache()
    cached = cache.get("transcript_search")
    if cached:
        print(f"[TranscriptSearch] UIA cache hit → ({cached['cx']}, {cached['cy']})")
        return cached["cx"], cached["cy"]

    # ── Search path ───────────────────────────────────────────────────────── #
    print("[TranscriptSearch] UIA cache miss — searching...")
    t_start = _time.perf_counter()

    try:
        from pywinauto import Application

        t0 = _time.perf_counter()
        app = Application(backend="uia").connect(path="Adobe Premiere Pro.exe", timeout=2)
        print(f"[TranscriptSearch]   connect:      {_time.perf_counter()-t0:.2f}s")

        t0 = _time.perf_counter()
        win = app.top_window()
        print(f"[TranscriptSearch]   top_window:   {_time.perf_counter()-t0:.2f}s")

        # Primary: direct-children path walk (near-instant when path is correct)
        t0 = _time.perf_counter()
        element = _step_down(win, _TRANSCRIPT_PATH)
        print(f"[TranscriptSearch]   path walk:    {_time.perf_counter()-t0:.2f}s")

        # Secondary: shallow BFS from WorkspaceFrame looking for OS_ViewContainer.
        # Avoids the wrong-TabPanelContainer problem by skipping that level entirely.
        if element is None:
            print("[TranscriptSearch]   trying shallow BFS from WorkspaceFrame...")
            t0 = _time.perf_counter()
            try:
                workspace = _step_down(win, ["WorkspaceFrame"])
                if workspace is not None:
                    os_view = _shallow_find(workspace, "OS_ViewContainer", max_depth=4)
                    if os_view is not None:
                        element = _step_down(os_view, ["OS_EditText"])
                print(f"[TranscriptSearch]   shallow BFS:  {_time.perf_counter()-t0:.2f}s"
                      f"  → {'found' if element else 'not found'}")
            except Exception as e:
                print(f"[TranscriptSearch]   shallow BFS:  {_time.perf_counter()-t0:.2f}s  (failed: {e})")

        # Last resort: full recursive search.
        if element is None:
            print("[TranscriptSearch]   falling back to full recursive search...")
            t0 = _time.perf_counter()
            try:
                element = win.child_window(
                    title="OS_EditText", control_type="Edit", found_index=0
                ).wrapper_object()
                print(f"[TranscriptSearch]   recursive:    {_time.perf_counter()-t0:.2f}s")
            except Exception as e:
                print(f"[TranscriptSearch]   recursive:    {_time.perf_counter()-t0:.2f}s  (failed: {e})")

        if element is None:
            print("[TranscriptSearch] UIA: OS_EditText not found")
            return None

        # Always trace the parent chain on a cache miss so we can see the
        # correct path regardless of which strategy found the element.
        # Copy this line into _TRANSCRIPT_PATH to make future runs instant.
        try:
            path_names = []
            node = element
            win_name = win.window_text()
            for _ in range(12):
                name = node.window_text()
                path_names.insert(0, name)
                parent = node.parent()
                if parent is None or parent.window_text() == win_name:
                    break
                node = parent
            print(f"[TranscriptSearch]   >>> Correct path (update _TRANSCRIPT_PATH): "
                  f"{' → '.join(repr(n) for n in path_names)}")
        except Exception as pe:
            print(f"[TranscriptSearch]   (parent trace failed: {pe})")

        rect = element.rectangle()
        cx = (rect.left + rect.right) // 2
        cy = (rect.top + rect.bottom) // 2

        total = _time.perf_counter() - t_start
        print(f"[TranscriptSearch] UIA found at ({cx}, {cy})  — total {total:.2f}s")

        # Cache so next call is instant
        cache["transcript_search"] = {"cx": cx, "cy": cy}
        _save_uia_cache(cache)
        print("[TranscriptSearch] Coordinates cached → delete .uia_cache.json if panel moves")

        return cx, cy

    except Exception as e:
        total = _time.perf_counter() - t_start
        print(f"[TranscriptSearch] UIA search failed after {total:.2f}s: {e}")
        return None


# ── Fallback: image matching ──────────────────────────────────────────────── #
def _find_via_image() -> tuple[int, int] | None:
    """Locate the search bar via template matching against reference images.

    Tries Transcript_Search.png then Transcript_Search_Select.png (if present),
    keeps whichever scores highest.  Returns (x, y) centre point or None.
    """
    candidates = [p for p in (SEARCH_BAR_IMAGE, SEARCH_BAR_IMAGE_SELECT) if p.exists()]
    if not candidates:
        print("[TranscriptSearch] No search bar images found.")
        print("  → Ensure Transcript_Search.png (and optionally Transcript_Search_Select.png)")
        print(f"    are in {_IMAGES_DIR}")
        return None

    screen_bgr = _grab_screenshot()

    best_val, best_loc, best_w, best_h, best_path, best_scale = 0.0, (0, 0), 0, 0, None, _DPI_SCALE
    for img_path in candidates:
        template = cv2.imread(str(img_path))
        if template is None:
            print(f"[TranscriptSearch] Could not read image: {img_path}")
            continue
        ckey = _cache_key(img_path)
        val, loc, w, h, scale = _multiscale_match(
            screen_bgr, template, hint_scale=_scale_cache.get(ckey)
        )
        print(f"[TranscriptSearch] Image '{img_path.name}' confidence={val:.2f}")
        if val > best_val:
            best_val, best_loc, best_w, best_h, best_path, best_scale = val, loc, w, h, img_path, scale

    if best_val < MATCH_THRESHOLD:
        print(f"[TranscriptSearch] Image matching failed (best confidence: {best_val:.2f})")
        return None

    _save_scale(_cache_key(best_path), best_scale)
    x, y = best_loc
    cx = x + best_w // 2
    cy = y + int(best_h * 2 / 3)
    print(f"[TranscriptSearch] Image match '{best_path.name}' confidence={best_val:.2f} → ({cx}, {cy})")
    return cx, cy


# ── Entry point ───────────────────────────────────────────────────────────── #
def main() -> None:
    search_text = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else ""

    # Try UIA first — fast, reliable, works regardless of box contents
    click_pos = _find_via_uia()

    # Fall back to image matching if UIA couldn't reach the element
    if click_pos is None:
        print("[TranscriptSearch] Falling back to image matching...")
        click_pos = _find_via_image()

    if click_pos is None:
        print("[TranscriptSearch] Search bar not found — aborting.")
        return

    click_x, click_y = click_pos
    print(f"[TranscriptSearch] Clicking at ({click_x}, {click_y})")
    pyautogui.click(click_x, click_y)

    if search_text:
        time.sleep(0.25)
        pyautogui.hotkey('ctrl', 'a')   # clear any existing text
        time.sleep(0.05)
        pyautogui.typewrite(search_text, interval=0.04)
        print(f"[TranscriptSearch] Typed: '{search_text}'")


if __name__ == "__main__":
    main()
