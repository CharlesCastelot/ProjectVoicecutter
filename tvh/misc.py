"""tvh/misc.py — miscellaneous Premiere utilities."""

import pyautogui
import keyboard
import win32gui

from .utils import sleep, tippy, tooltip, block_input, is_premiere_active


def kb_shortcuts_find_box():
    """
    Open the Keyboard Shortcuts panel and click its search box.
    Obsolete in newer Premiere versions (find box is auto-selected),
    but kept for older version compatibility.
    """
    orig_x, orig_y = pyautogui.position()
    import time; time.sleep(0.5)

    kb_hwnd = win32gui.FindWindow(None, 'Keyboard Shortcuts')
    if not kb_hwnd:
        tooltip("kb_shortcuts_find_box: 'Keyboard Shortcuts' dialog not found")
        return

    block_input(True)
    try:
        edit_hwnd = win32gui.FindWindowEx(kb_hwnd, None, 'Edit', None)
        if edit_hwnd:
            left, top, right, bottom = win32gui.GetWindowRect(edit_hwnd)
            pyautogui.moveTo(left - 20, top + 10, duration=0)
            sleep(1)
            pyautogui.click()
            sleep(20)
        else:
            tooltip("kb_shortcuts_find_box: Edit control not found in dialog")
    finally:
        pyautogui.moveTo(orig_x, orig_y, duration=0)
        block_input(False)


def close_titler():
    """
    Close the Legacy Titler window by clicking its X button.
    If a Marker dialog is open instead, uses Shift+Tab then Enter to close it.
    """
    if not is_premiere_active():
        return

    orig_x, orig_y = pyautogui.position()
    hwnd = win32gui.GetForegroundWindow()
    title = win32gui.GetWindowText(hwnd)
    left, top, right, bottom = win32gui.GetWindowRect(hwnd)
    width = right - left

    if 'Marker @' in title:
        keyboard.send('shift+tab')
        sleep(10)
        keyboard.send('enter')
    else:
        close_x = left + width - 35
        close_y = top - 15
        pyautogui.moveTo(close_x, close_y, duration=0)
        pyautogui.click()
        sleep(50)
        pyautogui.moveTo(orig_x, orig_y, duration=0)
