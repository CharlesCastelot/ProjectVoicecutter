"""tvh/audio.py — audio-related Premiere automation."""

import os
import pyautogui
import keyboard
import win32gui

from .config import AUDIO_CHANNELS, SELECT_FIND_BOX, PROJECT_PANEL, TIMELINE_PANEL, EFFECTS_PANEL, SOURCE_ASSIGN, OVERWRITE, WORKING_DIR
from .utils import sleep, tippy, block_input, image_search, is_premiere_active
from .panel_focus import pr_focus


def audio_mono_maker(track):
    """
    Configure mono audio via the Audio Channels dialog (Shift+G).
    track: 'left' or 'right'

    REFERENCE IMAGE needed in WORKING_DIR (tvh/config.py):
      audio_channels_checkbox_empty.png — screenshot of one unchecked checkbox

    HOW TO TAKE IT:
      1. Select a clip, open Audio Channels (Clip > Modify > Audio Channels or Shift+G)
      2. Crop-screenshot one unchecked checkbox → save as audio_channels_checkbox_empty.png
    """
    if not is_premiere_active():
        return

    block_input(True)
    orig_x, orig_y = pyautogui.position()

    keyboard.send(AUDIO_CHANNELS)

    # Wait for the dialog by title — no screenshot needed
    dialog_hwnd = None
    for _ in range(20):
        sleep(50)
        def _find(hwnd, _):
            nonlocal dialog_hwnd
            title = win32gui.GetWindowText(hwnd)
            if 'Audio Channels' in title or 'Modify Clip' in title:
                dialog_hwnd = hwnd
        win32gui.EnumWindows(_find, None)
        if dialog_hwnd:
            break

    if not dialog_hwnd:
        tippy("audio_mono_maker: Audio Channels dialog did not appear")
        block_input(False)
        pyautogui.moveTo(orig_x, orig_y, duration=0)
        return

    # Get the dialog bounds so we only search inside it
    left, top, right, bottom = win32gui.GetWindowRect(dialog_hwnd)
    dialog_region = (left, top, right, bottom)

    # Find all unchecked checkboxes inside the dialog
    unchecked_img = os.path.join(WORKING_DIR, 'audio_channels_checkbox_empty.png')
    try:
        all_unchecked = list(pyautogui.locateAllOnScreen(
            unchecked_img, region=dialog_region, confidence=0.9
        ))
    except Exception:
        all_unchecked = []

    if all_unchecked:
        xs = [loc.left + loc.width // 2 for loc in all_unchecked]
        mid_x = (min(xs) + max(xs)) / 2 if len(xs) > 1 else xs[0]

        for loc in all_unchecked:
            cx = loc.left + loc.width // 2
            cy = loc.top + loc.height // 2
            in_left_col = cx <= mid_x
            if (track == 'left' and in_left_col) or (track == 'right' and not in_left_col):
                pyautogui.click(cx, cy)
                sleep(10)

    sleep(5)
    keyboard.send('enter')
    pyautogui.moveTo(orig_x, orig_y, duration=0)
    block_input(False)


def add_gain(amount=7):
    """
    Open the Gain dialog (F2) and add the specified dB value to the selected clip.
    amount: gain in dB (default: 7)
    """
    keyboard.send('f2')
    sleep(50)
    keyboard.write(str(amount))
    sleep(50)
    keyboard.send('enter')


def insert_sfx(sound_name):
    """
    Search the project bin for a sound effect and overwrite it to the timeline.

    ⚠ CALIBRATION REQUIRED:
      Update the bin click coordinate (-6000, 250) to match where your
      project bin lives on screen. See comments in the original audio.py.
    """
    if not is_premiere_active():
        return

    orig_x, orig_y = pyautogui.position()
    block_input(True)

    keyboard.send('ctrl+shift+x')
    sleep(10)
    keyboard.send(SOURCE_ASSIGN)
    sleep(10)
    keyboard.send(PROJECT_PANEL)
    sleep(20)
    keyboard.send(SELECT_FIND_BOX)
    keyboard.write(sound_name)
    keyboard.send(SOURCE_ASSIGN)
    sleep(400)

    # ⚠ Update this to your bin's screen coordinates
    pyautogui.moveTo(-6000, 250, duration=0)
    pyautogui.click()
    sleep(10)

    keyboard.send(SOURCE_ASSIGN)
    sleep(5)
    keyboard.send(SELECT_FIND_BOX)
    sleep(10)
    keyboard.send('shift+backspace')
    sleep(10)

    pyautogui.moveTo(orig_x, orig_y, duration=0)
    sleep(20)

    keyboard.send(SOURCE_ASSIGN)
    sleep(50)
    keyboard.send(OVERWRITE)
    sleep(30)

    keyboard.send(EFFECTS_PANEL)
    sleep(30)
    keyboard.send(TIMELINE_PANEL)

    block_input(False)
