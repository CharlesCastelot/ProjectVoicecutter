"""tvh/vfx_scrubber.py — real-time VFX parameter scrubbing in Effect Controls."""

import os
import pyautogui
import keyboard

from PIL import ImageGrab

from .config import WORKING_DIR, EFFECT_CONTROLS, TRIANGLE_X_OFFSET, TRIANGLE_Y_OFFSET
from .utils import sleep, tippy, tooltip, block_input, get_caret_pos, image_search, is_premiere_active
from .panel_focus import pr_focus
from .transform import click_transform_icon, click_transform_icon2

Xbegin = 0
Ybegin = 0


def reset_from_auto_vfx(clicky=0):
    global Xbegin, Ybegin
    try:
        pyautogui.moveTo(Xbegin, Ybegin, duration=0)
        if clicky == 1:
            pyautogui.middleClick()
    except Exception:
        pass
    block_input(False)
    tooltip("")


def find_hot_text(param):
    """
    Find Premiere's blue scrubable value for a VFX parameter and hold-drag it.

    ⚠ For anchor_point_vertical: requires anti-flicker-filter_000_D2019_ui100.png
      in WORKING_DIR (tvh/config.py).
    """
    tooltip("")
    mouse_x, mouse_y = pyautogui.position()
    px, py = None, None

    if param in ('scale', 'anchor_point', 'rotation'):
        search_w = 200
        screenshot = ImageGrab.grab(bbox=(mouse_x + 50, mouse_y, mouse_x + 50 + search_w, mouse_y + 11))
        pixels = screenshot.load()
        target = (0x2D, 0x8C, 0xEB)
        for x in range(screenshot.width):
            for y in range(screenshot.height):
                r, g, b = pixels[x, y][:3]
                if abs(r - target[0]) + abs(g - target[1]) + abs(b - target[2]) < 90:
                    px = mouse_x + 50 + x
                    py = mouse_y + y
                    break
            if px is not None:
                break

        if px is None:
            reset_from_auto_vfx(0)
            return
        pyautogui.moveTo(px + 10, py + 5, duration=0)

    elif param == 'anchor_point_vertical':
        result = image_search(
            os.path.join(WORKING_DIR, 'anti-flicker-filter_000_D2019_ui100.png'),
            search_region=(mouse_x + 50, mouse_y, mouse_x + 800, mouse_y + 100)
        )
        if result is None:
            result = image_search(
                os.path.join(WORKING_DIR, 'anti-flicker-filter_000_D2019_2.png'),
                search_region=(mouse_x + 50, mouse_y, mouse_x + 800, mouse_y + 100)
            )
        if result is None:
            reset_from_auto_vfx(0)
            return
        px, py = result
        pyautogui.moveTo(px + 80, py - 20, duration=0)
    else:
        reset_from_auto_vfx(0)
        return

    pyautogui.mouseDown()
    block_input(False)
    sleep(1000)   # Scrub duration — replace with voice-controlled hold logic if desired
    block_input(True)
    pyautogui.mouseUp()
    sleep(15)
    reset_from_auto_vfx(1)


def find_vfx(param):
    """Search Effect Controls for a VFX parameter label image, then scrub it."""
    sleep(5)
    mouse_x, mouse_y = pyautogui.position()
    img = os.path.join(WORKING_DIR, f'{param}_D2019_ui100.png')

    result = image_search(img, search_region=(mouse_x - 90, mouse_y, mouse_x + 800, mouse_y + 900))
    if result is None:
        result = image_search(img, search_region=(mouse_x - 30, mouse_y, mouse_x + 1200, mouse_y + 1200), confidence=0.8)

    if result is None:
        tippy(f"find_vfx: '{param}' label not found — add {param}_D2019_ui100.png to WORKING_DIR in tvh/config.py")
        reset_from_auto_vfx(0)
        return

    found_x, found_y = result
    pyautogui.moveTo(found_x, found_y, duration=0)
    sleep(5)
    find_hot_text(param)


def untwirl():
    """
    Ensure the Motion effect triangle in Effect Controls is open (expanded).

    REFERENCE IMAGE needed in WORKING_DIR (tvh/config.py):
      motion_triangle_closed.png — the Motion arrow while collapsed (pointing right ▶)

    HOW TO TAKE IT:
      1. Select a clip so Effect Controls shows its properties
      2. Make sure the Motion section is collapsed (arrow points right)
      3. Crop-screenshot just that arrow → save as motion_triangle_closed.png
      If the arrow is already open (pointing down), just click it once to collapse it first.
    """
    pr_focus('effect controls')
    keyboard.send('tab')
    sleep(10)

    caret_x, caret_y = get_caret_pos()
    if caret_x == 0 and caret_y == 0:
        # No clip selected — try Selection Follows Playhead to select the top clip
        keyboard.send('ctrl+p')
        sleep(10)
        keyboard.send('ctrl+p')
        sleep(15)
        caret_x, caret_y = get_caret_pos()
        if caret_x == 0 and caret_y == 0:
            return 'reset'

    closed_img = os.path.join(WORKING_DIR, 'motion_triangle_closed.png')

    # Search the left side of the screen where Effect Controls typically lives
    search_region = (0, 0, 900, 1400)

    closed_pos = image_search(closed_img, search_region=search_region)
    if closed_pos:
        # Triangle is collapsed — click to open it
        pyautogui.click(closed_pos[0], closed_pos[1])
        sleep(5)
    # If not found, it's already open — nothing to do

    return 'untwirled'


def instant_vfx(param):
    """
    Navigate to a VFX parameter in Effect Controls and enable scrubbing.
    param: 'scale' | 'rotation' | 'anchor_point' | 'anchor_point_vertical'

    ⚠ REQUIRES CALIBRATION: TRIANGLE_X/Y_OFFSET in tvh/config.py and
      reference PNGs (scale_D2019_ui100.png, etc.) in WORKING_DIR.
    """
    global Xbegin, Ybegin

    if not is_premiere_active():
        return

    block_input(True)
    pr_focus('effect controls')
    sleep(10)

    Xbegin, Ybegin = pyautogui.position()

    result = untwirl()
    if result == 'reset':
        reset_from_auto_vfx(0)
        return

    click_transform_icon()
    find_vfx(param)
