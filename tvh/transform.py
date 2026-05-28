"""tvh/transform.py — Effect Controls transform/motion icon interaction."""

import os
import pyautogui
import keyboard

from .config import WORKING_DIR, DIRECT_MANIP, EFFECT_CTRL_ALT, TIMELINE_ALT, TRANSFORM_ICON_X_OFFSET, TRANSFORM_ICON_Y_OFFSET
from .utils import sleep, tippy, tooltip, block_input, image_search, is_premiere_active
from .panel_focus import pr_focus


def crop_click():
    """
    Click the Crop transform button in Effect Controls for live drag handles.

    ⚠ REQUIRES: CROP_transform_2020.png in WORKING_DIR (tvh/config.py).
      Take a screenshot of the Crop transform icon at your UI scale and save it there.
    """
    if not is_premiere_active():
        return

    orig_x, orig_y = pyautogui.position()
    block_input(True)

    ec_x, ec_y = 10, 200
    result = image_search(
        os.path.join(WORKING_DIR, 'CROP_transform_2020.png'),
        search_region=(ec_x, ec_y, ec_x + 200, ec_y + 800)
    )
    if result is None:
        result = image_search(
            os.path.join(WORKING_DIR, 'CROP_transform_2020.png'),
            search_region=(ec_x, ec_y, ec_x + 400, ec_y + 1200)
        )

    if result is None:
        tippy("crop_click: CROP_transform_2020.png not found — add it to WORKING_DIR in tvh/config.py")
    else:
        found_x, found_y = result
        pyautogui.moveTo(found_x + 10, found_y + 10, duration=0)
        sleep(5)
        pyautogui.click()

    pyautogui.moveTo(orig_x, orig_y, duration=0)
    block_input(False)


def click_transform_icon2():
    """
    Click the Motion/Transform expand arrow in Effect Controls for direct manipulation.

    ⚠ REQUIRES CALIBRATION: update the win32gui ClassNN lookup in this function
      for your panel layout. See original transform.py for instructions.
    """
    if not is_premiere_active():
        return

    keyboard.send(DIRECT_MANIP)
    sleep(5)
    block_input(True)
    keyboard.send(EFFECT_CTRL_ALT)
    sleep(20)

    tooltip("click_transform_icon2: calibrate ClassNN + offsets for your panel layout in tvh/transform.py")
    # Full impl: use win32gui.FindWindowEx with your Effect Controls ClassNN to
    # get the panel rect, then click at (left + TRANSFORM_ICON_X_OFFSET, top + TRANSFORM_ICON_Y_OFFSET)

    keyboard.send(TIMELINE_ALT)
    sleep(10)
    keyboard.send(DIRECT_MANIP)
    sleep(10)
    keyboard.send(EFFECT_CTRL_ALT)
    block_input(False)


def click_transform_icon():
    """Legacy version of click_transform_icon2 — kept for internal use by vfx_scrubber."""
    keyboard.send(EFFECT_CTRL_ALT)
    sleep(10)
    tooltip("click_transform_icon (legacy): calibrate ClassNN + offsets in tvh/transform.py")
