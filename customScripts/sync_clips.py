"""sync_clips.py — Select two clips by clicking then synchronize them.

Voice trigger: "sync"
Usage:
  1. Say "sync" — Jarvis starts listening for two left-clicks.
  2. Click clip 1 (selected normally, no modifier).
  3. Click clip 2 — Shift is held automatically so Premiere adds it to
     the selection.
  4. Ctrl+Alt+Shift+S (Synchronize...) fires and the dialog opens.
"""

import time
import pyautogui
from pynput import mouse

_click_tracker = 0


def on_click(x, y, button, pressed):
    global _click_tracker

    # Only react to press events — pynput fires on both press AND release,
    # so without this filter a single click would advance the tracker twice.
    if not pressed:
        return

    # Ignore anything that isn't the left mouse button.
    if button != mouse.Button.left:
        return

    if _click_tracker == 0:
        print("[sync] 1st clip clicked — holding Shift for 2nd selection...")
        pyautogui.keyDown('shift')
        _click_tracker = 1

    elif _click_tracker == 1:
        print("[sync] 2nd clip clicked — releasing Shift and synchronizing...")
        pyautogui.keyUp('shift')
        time.sleep(0.1)   # Let Premiere register the Shift release
        pyautogui.hotkey('ctrl', 'alt', 'shift', 's')  # Open Synchronize dialog
        # Wait long enough for the dialog to fully initialize and load its
        # remembered sync method before Enter confirms it.  Too short = Premiere
        # defaults back to Clip Start instead of your saved method.
        time.sleep(0.6)
        pyautogui.press('enter')
        _click_tracker = 0
        return False                                 # Returning False stops the listener


def main():
    global _click_tracker
    _click_tracker = 0          # Always reset on entry in case of a previous failure
    print("[sync] Waiting for two mouse clicks to synchronize clips...")
    with mouse.Listener(on_click=on_click) as listener:
        listener.join()
    print("[sync] Done.")


if __name__ == "__main__":
    main()
