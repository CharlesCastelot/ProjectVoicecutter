"""
tvh/clipboard.py — numbered clipboard slots via InsideClipboard.exe.

⚠ REQUIRES: InsideClipboard.exe
  Update INSIDECLIPBOARD_EXE and INSIDECLIPBOARD_DIR in tvh/config.py.
  Also create clipTEXT.clp — see module docstring in the original clipboard.py.
"""

import subprocess
import keyboard
import pyperclip
import win32gui

from .config import INSIDECLIPBOARD_EXE, INSIDECLIPBOARD_DIR, DESELECT_ALL
from .utils import sleep, tooltip, is_premiere_active, get_premiere_hwnd
from .panel_focus import pr_focus
from .timeline import target


def save_to_file(name):
    subprocess.run([INSIDECLIPBOARD_EXE, '/saveclp', name], cwd=INSIDECLIPBOARD_DIR)


def load_from_file(name):
    subprocess.run([INSIDECLIPBOARD_EXE, '/loadclp', name], cwd=INSIDECLIPBOARD_DIR)


def save_clipboard(slot):
    """
    Copy the current Premiere selection and save it to numbered slot file clip{slot}.clp.
    slot: integer (1–9)
    """
    if not is_premiere_active():
        return

    slot_str = str(slot)
    tooltip(f"Saving → clip{slot_str}.clp")
    sleep(10)

    keyboard.send('ctrl+c')
    sleep(20)
    import time; time.sleep(0.25)
    sleep(20)

    filename = f'clip{slot_str}.clp'
    save_to_file(filename)
    sleep(1000)
    save_to_file(filename)
    tooltip("")


def recall_clipboard(slot, transition=0):
    """
    Paste numbered clipboard slot back into the Premiere timeline.
    slot: integer (1–9)

    Uses a three-step clipboard flush to bypass Premiere's internal clipboard cache.
    """
    hwnd = get_premiere_hwnd()
    if hwnd:
        win32gui.SetForegroundWindow(hwnd)

    pr_focus('timeline')

    load_from_file('clipTEXT.clp')
    sleep(15)
    pyperclip.copy('')
    sleep(10)

    if hwnd:
        win32gui.SetForegroundWindow(hwnd)
    tooltip("Flushing Premiere clipboard...")
    keyboard.send('ctrl+v')
    sleep(25)

    pyperclip.copy('')
    sleep(30)

    if hwnd:
        win32gui.SetForegroundWindow(hwnd)
    load_from_file(f'clip{slot}.clp')
    sleep(15)

    if hwnd:
        win32gui.SetForegroundWindow(hwnd)
    tooltip(f"Pasting clip{slot}...")
    keyboard.send('ctrl+v')
    sleep(15)

    if transition == 0:
        target('v1', 'on', 'all')
    sleep(10)

    keyboard.send(DESELECT_ALL)
    tooltip("")
