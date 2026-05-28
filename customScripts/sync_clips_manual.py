"""sync_clips_manual.py — Select two clips by clicking, open Synchronize dialog.

Voice trigger: "sync window"
Same as sync_clips.py but does NOT press Enter — the Synchronize dialog stays
open so you can choose the sync method (Clip Marker, Timecode, Audio, etc.)
before confirming.

Usage:
  1. Say "sync window" — Jarvis starts listening for two left-clicks.
  2. Click clip 1 (selected normally, no modifier).
  3. Click clip 2 — Shift is held automatically so Premiere adds it to
     the selection.
  4. Ctrl+Alt+Shift+S fires — Synchronize dialog opens. Adjust and confirm.
"""

import time
import pyautogui
from pynput import mouse

_click_tracker = 0


def on_click(x, y, button, pressed):
    global _click_tracker

    if not pressed:
        return

    if button != mouse.Button.left:
        return

    if _click_tracker == 0:
        print("[sync window] 1st clip clicked — holding Shift for 2nd selection...")
        pyautogui.keyDown('shift')
        _click_tracker = 1

    elif _click_tracker == 1:
        print("[sync window] 2nd clip clicked — releasing Shift and opening Synchronize dialog...")
        pyautogui.keyUp('shift')
        time.sleep(0.1)
        pyautogui.hotkey('ctrl', 'alt', 'shift', 's')  # Opens Synchronize dialog — no Enter
        _click_tracker = 0
        return False


def main():
    global _click_tracker
    _click_tracker = 0
    print("[sync window] Waiting for two mouse clicks...")
    with mouse.Listener(on_click=on_click) as listener:
        listener.join()
    print("[sync window] Dialog open — adjust sync method and confirm.")


if __name__ == "__main__":
    main()
