"""
Interactive calibration tool for Premiere Pro Project panel.

Run once per monitor/column layout change.
Hover over each element when prompted — position is captured automatically
after a 3-second countdown so you have time to switch to Premiere.
"""

import json
import time
from pathlib import Path

import pyautogui

CALIBRATION_FILE = Path(__file__).parent / "calibration.json"

FIELDS = [
    ("scene",       "SCENE column header"),
    ("take",        "TAKE column header"),
    ("camera",      "CAMERA column header"),
    ("description", "DESCRIPTION column header"),
    ("location",    "LOCATION column header"),
    ("character",   "CHARACTER column header"),
    ("notes",       "NOTES column header"),
]


# ── Helpers ───────────────────────────────────────────────────────────────────

def _countdown_capture(prompt: str) -> tuple[int, int]:
    """Print a 3-second countdown then capture current mouse position."""
    print(f"  >> {prompt}")
    for n in (3, 2, 1):
        print(f"     Capturing in {n}...", end="\r", flush=True)
        time.sleep(1)
    x, y = pyautogui.position()
    print(f"     Captured at ({x}, {y})           ")
    return x, y


def _sample_row_color(screenshot, row_y: int, screen_w: int) -> list[int]:
    """Average RGB across a horizontal strip at row_y."""
    samples = []
    for x in range(10, min(screen_w, 400), 25):
        try:
            r, g, b = screenshot.getpixel((x, row_y))
            samples.append((r, g, b))
        except Exception:
            pass
    if not samples:
        return [0, 0, 0]
    return [
        int(sum(c[i] for c in samples) / len(samples))
        for i in range(3)
    ]


# ── Main calibration flow ─────────────────────────────────────────────────────

def calibrate():
    print()
    print("=" * 60)
    print("  PREMIERE PRO COLUMN CALIBRATION")
    print("=" * 60)
    print()
    print("  Requirements:")
    print("  - Premiere Pro open, Project panel in List View")
    print("  - Metadata columns you use visible and ordered")
    print("  - At least two clips visible in the panel")
    print()
    input("  Press Enter when ready, then switch to Premiere quickly...")
    time.sleep(1.5)

    calibration: dict = {
        "columns":            {},
        "row_height":         25,
        "first_row_y":        None,
        "selection_color":    None,
        "selection_tolerance": 30,
    }

    # ── Step 1: Column headers ────────────────────────────────────────────
    print()
    print("── Step 1: Column headers ──────────────────────────────")
    print("   For each field, press Enter to calibrate or S+Enter to skip.")
    print()

    for field, label in FIELDS:
        choice = input(f"  [{field.upper()}] Calibrate? (Enter=yes, S=skip): ").strip().lower()
        if choice == "s":
            print(f"  Skipped.\n")
            continue
        x, _ = _countdown_capture(f"Hover over the {label}")
        calibration["columns"][field] = x
        print()

    if not calibration["columns"]:
        print("No columns calibrated — aborting.")
        return

    # ── Step 2: Row height ────────────────────────────────────────────────
    print()
    print("── Step 2: Row height ──────────────────────────────────")
    print()

    _, y1 = _countdown_capture("Hover over the FIRST clip row (anywhere in that row)")
    calibration["first_row_y"] = y1
    print()

    _, y2 = _countdown_capture("Hover over the SECOND clip row (anywhere in that row)")
    calibration["row_height"] = abs(y2 - y1)
    print()
    print(f"  Row height: {calibration['row_height']}px | First row y: {y1}px")

    # ── Step 3: Selection highlight color ────────────────────────────────
    print()
    print("── Step 3: Selection color ─────────────────────────────")
    print()
    print("  Click any clip in Premiere to select it, then return here.")
    input("  Press Enter when a clip is selected in the panel...")
    time.sleep(0.4)

    screenshot = pyautogui.screenshot()
    screen_w = pyautogui.size().width
    color = _sample_row_color(screenshot, calibration["first_row_y"], screen_w)
    calibration["selection_color"] = color
    print(f"  Selection color: RGB({color[0]}, {color[1]}, {color[2]})")

    # ── Save ──────────────────────────────────────────────────────────────
    with open(CALIBRATION_FILE, "w") as f:
        json.dump(calibration, f, indent=4)

    print()
    print("=" * 60)
    print(f"  Saved: {CALIBRATION_FILE.name}")
    print(f"  Columns: {list(calibration['columns'].keys())}")
    print(f"  Row height: {calibration['row_height']}px")
    print("=" * 60)
    print()
    print("  Run 'python test_writer.py' to verify before live use.")
    print()


if __name__ == "__main__":
    calibrate()
