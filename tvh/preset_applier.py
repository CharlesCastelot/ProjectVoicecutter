"""tvh/preset_applier.py — apply named presets from the Effects panel by drag-drop."""

import pyautogui
import keyboard

from .config import SHUTTLE_STOP, SELECT_FIND_BOX, EFFECTS_PANEL, MAG_GLASS_X_OFFSET, MAG_GLASS_Y_OFFSET, PRESET_ICON_X_OFFSET, PRESET_ICON_Y_OFFSET
from .utils import sleep, tippy, block_input, get_caret_pos, is_premiere_active
from .panel_focus import pr_focus


def preset(item):
    """
    Apply a named preset to a clip on the Premiere timeline.

    *** CURSOR MUST BE HOVERING OVER THE TARGET CLIP BEFORE CALLING THIS ***

    ⚠ REQUIRES CALIBRATION in tvh/config.py:
      MAG_GLASS_X_OFFSET, MAG_GLASS_Y_OFFSET  — offset from caret to magnifying glass
      PRESET_ICON_X_OFFSET, PRESET_ICON_Y_OFFSET — offset to first result icon
      Also requires these Premiere shortcuts set in tvh/config.py:
        SHUTTLE_STOP, EFFECTS_PANEL, SELECT_FIND_BOX

    item: exact preset name as it appears in Premiere (e.g. 'crop 50', 'blur edges')
    """
    if not is_premiere_active():
        return

    block_input(True)

    keyboard.send(SHUTTLE_STOP)
    sleep(10)
    keyboard.send(SHUTTLE_STOP)
    sleep(5)

    orig_x, orig_y = pyautogui.position()

    pyautogui.middleClick()
    sleep(5)

    pr_focus('effects')
    sleep(15)
    keyboard.send(SELECT_FIND_BOX)
    sleep(5)

    caret_x, caret_y = get_caret_pos()
    if caret_x == 0 and caret_y == 0:
        waiting = 0
        while True:
            waiting += 1
            sleep(33)
            caret_x, caret_y = get_caret_pos()
            if caret_x != 0 or caret_y != 0:
                break
            if waiting > 40:
                tippy("preset(): no caret found — Premiere may be busy. Update shortcuts in tvh/config.py")
                block_input(False)
                return

    sleep(1)
    pyautogui.moveTo(caret_x, caret_y, duration=0)
    sleep(5)
    pyautogui.moveRel(MAG_GLASS_X_OFFSET, MAG_GLASS_Y_OFFSET, duration=0)
    sleep(5)
    keyboard.write(item)
    sleep(5)

    pyautogui.moveRel(PRESET_ICON_X_OFFSET, PRESET_ICON_Y_OFFSET, duration=0)
    sleep(5)
    icon_x, icon_y = pyautogui.position()

    pyautogui.moveRel(50, 50, duration=0)
    sleep(5)
    pyautogui.click()
    sleep(5)

    pyautogui.moveTo(icon_x, icon_y, duration=0)
    sleep(5)
    pyautogui.drag(orig_x - icon_x, orig_y - icon_y, duration=0, button='left')
    sleep(5)

    pyautogui.middleClick()
    block_input(False)

    if 'CROP' in item.upper():
        from .transform import crop_click
        sleep(320)
        crop_click()
