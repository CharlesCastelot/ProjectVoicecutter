"""
Premiere Pro metadata UI writer.

Reads calibration.json and uses pyautogui + clipboard to write
ParseResult rows into the Project panel's metadata columns.

Column-by-column write strategy:
  - Finish all rows for column 1, then move to column 2, etc.
  - Only touches columns present in ParseResult.columns AND in calibration.
  - Unspecified columns are never clicked.
"""

import json
import time
from pathlib import Path

import numpy as np
import pyautogui
import pyperclip

from metadata_parser import MetadataCommandParser, ParseResult

CALIBRATION_FILE = Path(__file__).parent / "calibration.json"


# ── Calibration ───────────────────────────────────────────────────────────────

def load_calibration() -> dict:
    if not CALIBRATION_FILE.exists():
        raise FileNotFoundError(
            f"{CALIBRATION_FILE.name} not found.\n"
            "Run: python premiere_calibration.py"
        )
    with open(CALIBRATION_FILE) as f:
        return json.load(f)


# ── Row detection ─────────────────────────────────────────────────────────────

def find_selected_row_y(calibration: dict) -> int | None:
    """
    Scan a narrow left-side strip of the screen for the selection
    highlight color recorded during calibration.

    Returns the y-coordinate of the selected row, or None on failure.
    Falls back to calibration['first_row_y'] if no color was stored.
    """
    sel_color  = calibration.get("selection_color")
    tolerance  = calibration.get("selection_tolerance", 30)
    first_row_y = calibration.get("first_row_y", 500)

    if not sel_color:
        return first_row_y

    screenshot = pyautogui.screenshot()
    img = np.array(screenshot)
    sr, sg, sb = sel_color

    # Scan rows in a window around the expected first row
    scan_start = max(0, first_row_y - 20)
    scan_end   = min(img.shape[0], first_row_y + 300)
    strip      = img[scan_start:scan_end, 5:80]  # narrow left strip

    for rel_y in range(strip.shape[0]):
        row   = strip[rel_y]
        avg_r = int(np.mean(row[:, 0]))
        avg_g = int(np.mean(row[:, 1]))
        avg_b = int(np.mean(row[:, 2]))
        if (abs(avg_r - sr) < tolerance and
                abs(avg_g - sg) < tolerance and
                abs(avg_b - sb) < tolerance):
            return scan_start + rel_y

    return first_row_y


# ── Cell interaction ──────────────────────────────────────────────────────────

def _write_cell(x: int, y: int, value: str, delay: float, dry_run: bool) -> None:
    """
    Double-click a cell, select-all, paste value via clipboard, confirm.
    Double-click is used instead of single-click to reliably enter edit mode
    regardless of whether the clip was already selected.
    """
    if dry_run:
        return
    pyautogui.doubleClick(x, y)
    time.sleep(delay)
    pyautogui.hotkey("ctrl", "a")
    time.sleep(0.05)
    pyperclip.copy(value)
    pyautogui.hotkey("ctrl", "v")
    time.sleep(0.05)
    pyautogui.press("enter")
    time.sleep(delay)


# ── Writer ────────────────────────────────────────────────────────────────────

def write_metadata(
    result:          ParseResult,
    calibration:     dict,
    starting_row_y:  int | None = None,
    delay:           float      = 0.2,
    dry_run:         bool       = False,
) -> None:
    """
    Write a ParseResult into Premiere's Project panel cells.

    Args:
        result:         ParseResult from MetadataCommandParser.parse().
        calibration:    Loaded calibration dict.
        starting_row_y: y-pixel of the first clip row. Auto-detected if None.
        delay:          Seconds between actions. Increase on slow machines.
        dry_run:        Print actions without clicking (for testing).
    """
    col_positions: dict[str, int] = calibration.get("columns", {})
    row_height:    int            = calibration.get("row_height", 25)
    mode = "[DRY RUN] " if dry_run else ""

    # Only write columns that the command specified AND that we have positions for
    writable = [c for c in result.columns if c in col_positions]
    if not writable:
        print(f"{mode}[Writer] No writable columns — check calibration.")
        print(f"  Command columns : {result.columns}")
        print(f"  Calibrated cols : {list(col_positions.keys())}")
        return

    if starting_row_y is None:
        starting_row_y = find_selected_row_y(calibration)

    print(f"{mode}[Writer] {len(result.rows)} row(s) | "
          f"columns: {writable} | starting y={starting_row_y}")

    for col in writable:
        col_x = col_positions[col]
        print(f"\n  -- {col.upper()} (x={col_x}) --")

        for row_idx, row in enumerate(result.rows):
            value = getattr(row, col, "")
            if not value:
                print(f"    row {row_idx + 1}: (empty — skip)")
                continue

            row_y = starting_row_y + row_idx * row_height
            print(f"    row {row_idx + 1} @ ({col_x}, {row_y}): {value!r}")
            _write_cell(col_x, row_y, value, delay, dry_run)

    print(f"\n{mode}[Writer] Done.")


# ── High-level interface ──────────────────────────────────────────────────────

class PremierMetadataWriter:
    """
    Single entry point combining parser + UI writer.
    Intended to be called from the voice assistant's processVoiceInput.

    Usage:
        writer = PremierMetadataWriter()
        writer.load_calibration()
        writer.execute("log scene 4A takes 1 through 5 cam A through B wide John enters")
    """

    def __init__(self):
        self.parser        = MetadataCommandParser()
        self._calibration: dict | None = None

    def load_calibration(self) -> bool:
        try:
            self._calibration = load_calibration()
            cols = list(self._calibration.get("columns", {}).keys())
            print(f"[Writer] Calibration loaded — columns: {cols}")
            return True
        except FileNotFoundError as e:
            print(f"[Writer] {e}")
            return False

    def execute(self, command: str, dry_run: bool = False) -> bool:
        """
        Parse a log command and write to Premiere.

        Returns True if rows were written (or would be in dry_run),
        False for control commands or errors.
        """
        result = self.parser.parse(command)

        if result is None:
            # Control command (base/config/profile) — nothing to write
            return False

        if not result.rows:
            print("[Writer] No rows generated.")
            return False

        if self._calibration is None and not self.load_calibration():
            return False

        write_metadata(result, self._calibration, dry_run=dry_run)
        return True
