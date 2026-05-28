"""tvh/utils.py — shared helpers for Premiere automation."""

import time
import ctypes

import pyautogui
import keyboard
import win32gui
import win32process

from PIL import ImageGrab

from .config import WORKING_DIR

# Note: pyautogui.PAUSE is intentionally NOT set here so Jarvis's timing is unaffected.
pyautogui.FAILSAFE = True


def sleep(ms):
    time.sleep(ms / 1000.0)


def tooltip(text):
    if text:
        print(f"[STATUS] {text}")


def tippy(message, wait=333):
    tooltip(message)
    sleep(abs(wait))
    tooltip("")


def block_input(block=True):
    ctypes.windll.user32.BlockInput(block)


def get_caret_pos():
    class POINT(ctypes.Structure):
        _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]
    pt = POINT()
    ctypes.windll.user32.GetCaretPos(ctypes.byref(pt))
    return pt.x, pt.y


def pixel_get_color(x, y):
    screenshot = ImageGrab.grab(bbox=(x, y, x + 1, y + 1))
    return screenshot.getpixel((0, 0))[:3]


def image_search(image_path, search_region=None, confidence=0.9):
    try:
        loc = pyautogui.locateOnScreen(image_path, region=search_region, confidence=confidence)
        if loc:
            return int(loc.left + loc.width / 2), int(loc.top + loc.height / 2)
    except Exception as e:
        print(f"[image_search] {image_path}: {e}")
    return None


def is_premiere_active():
    hwnd = win32gui.GetForegroundWindow()
    return 'Adobe Premiere Pro' in win32gui.GetWindowText(hwnd)


def get_premiere_hwnd():
    result = []
    def _cb(hwnd, _):
        if win32gui.IsWindowVisible(hwnd):
            if 'Adobe Premiere Pro' in win32gui.GetWindowText(hwnd):
                result.append(hwnd)
        return True
    win32gui.EnumWindows(_cb, None)
    return result[0] if result else None


def coord_get_control(x_coord, y_coord, hwnd):
    matches = []
    def _cb(child, _):
        try:
            left, top, right, bottom = win32gui.GetWindowRect(child)
            if left <= x_coord <= right and top <= y_coord <= bottom:
                w, h = right - left, bottom - top
                matches.append((w * h, w))
        except Exception:
            pass
        return True
    try:
        win32gui.EnumChildWindows(hwnd, _cb, None)
    except Exception:
        pass
    if matches:
        matches.sort(key=lambda m: m[0])
        return matches[0][1]
    return 0


def modsl():
    keyboard.release('left ctrl')
    keyboard.release('left alt')
    keyboard.release('left shift')
    sleep(1)


def modsr():
    keyboard.release('right ctrl')
    keyboard.release('right alt')
    keyboard.release('right shift')
    sleep(1)


def send_key(the_key, fun="", sometext=""):
    tooltip(f"send_key → {the_key}  [{fun}] {sometext}")
    keyboard.send(the_key)
    sleep(100)
    tooltip("")
