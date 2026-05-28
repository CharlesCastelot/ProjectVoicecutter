"""tvh/playback.py — playback controls and keyframe easing."""

import keyboard
import win32gui

from .config import SHUTTLE_STOP, EFFECT_CONTROLS, EASE_IN, EASE_OUT
from .utils import sleep, is_premiere_active, get_premiere_hwnd
from .panel_focus import pr_focus


def stop_playing():
    """
    Toggle play/pause even when Premiere is not the active window.
    If Premiere IS focused: just sends Space.
    If not: temporarily focuses Premiere, sends Space, then restores focus.
    """
    if is_premiere_active():
        keyboard.send('space')
        return

    current_hwnd = win32gui.GetForegroundWindow()
    hwnd = get_premiere_hwnd()
    if not hwnd:
        return

    win32gui.SetForegroundWindow(hwnd)
    sleep(30)
    keyboard.send(EFFECT_CONTROLS)
    sleep(40)
    keyboard.send(EFFECT_CONTROLS)
    sleep(10)
    keyboard.send('space')
    sleep(20)
    if current_hwnd:
        try:
            win32gui.SetForegroundWindow(current_hwnd)
        except Exception:
            pass


def ease_in_and_out():
    """
    Apply Ease In + Ease Out to selected keyframes in Effect Controls.
    Requires: assign EASE_IN (Ctrl+Shift+F10) and EASE_OUT (Shift+F10)
    in Premiere's Keyboard Shortcuts panel, or update config.py.
    """
    keyboard.release('shift')
    keyboard.release('ctrl')
    keyboard.release('alt')
    keyboard.send(EASE_IN)
    sleep(10)
    keyboard.send(EASE_OUT)
    sleep(5)
