"""tvh/timeline.py — timeline controls: markers, track targeting, monitor keys."""

import os
import pyautogui
import keyboard

from .config import WORKING_DIR, SHUTTLE_STOP, EFFECTS_PANEL, TIMELINE_PANEL, PROGRAM_MONITOR, SOURCE_MONITOR, EFFECT_CONTROLS
from .utils import sleep, tippy, tooltip, block_input, image_search, is_premiere_active, get_premiere_hwnd
from .panel_focus import pr_focus


def marker():
    """Stop playback and create a marker at the current playhead position."""
    keyboard.send(SHUTTLE_STOP)
    sleep(5)
    keyboard.send('ctrl+;')


def reselect():
    """Re-focus timeline and reset clip selection. (Obsolete in newer Premiere.)"""
    keyboard.send(SHUTTLE_STOP)
    sleep(5)
    keyboard.send(EFFECTS_PANEL)
    sleep(5)
    keyboard.send(TIMELINE_PANEL)
    sleep(5)
    keyboard.send('ctrl+alt+d')
    sleep(10)
    keyboard.send('ctrl+p')
    sleep(1)
    keyboard.send('ctrl+p')


def target(v1_or_a1, on_off, all_none_solo=0, number=0):
    """
    Target or untarget video/audio tracks using image search.

    ⚠ REQUIRES reference PNGs in WORKING_DIR (tvh/config.py):
      v1_unlocked_targeted_alone.png, v1_locked_targeted_alone.png,
      v1_unlocked_untargeted_alone.png, a1 variants, etc.
    """
    pr_focus('timeline')

    wrench_x, wrench_y = 400, 800
    target_distance = 98

    result = image_search(
        os.path.join(WORKING_DIR, 'timelineUniqueLocator2.png'),
        search_region=(wrench_x, wrench_y, wrench_x + 600, wrench_y + 1000)
    )
    if result is None:
        tippy("target(): timeline locator image not found — add reference PNGs to WORKING_DIR in tvh/config.py")
        return

    x_time, y_time = result
    x_time -= target_distance

    targeted = image_search(
        os.path.join(WORKING_DIR, f'{v1_or_a1}_unlocked_targeted_alone.png'),
        search_region=(x_time, y_time, x_time + 100, y_time + 1000)
    )
    if targeted is None:
        targeted = image_search(
            os.path.join(WORKING_DIR, f'{v1_or_a1}_locked_targeted_alone.png'),
            search_region=(x_time, y_time, x_time + 100, y_time + 1000)
        )

    if targeted:
        if v1_or_a1 == 'v1':
            keyboard.send('shift+9')
            sleep(10)
            if on_off == 'on':
                keyboard.send('shift+9')
            sleep(10)
            if number > 0:
                keyboard.send(f'shift+{number}')
        elif v1_or_a1 == 'a1':
            keyboard.send('alt+9')
            sleep(10)
            if on_off == 'on':
                keyboard.send('alt+9')
            sleep(10)
            if number > 0:
                keyboard.send(f'alt+{number}')
    else:
        untargeted = image_search(
            os.path.join(WORKING_DIR, f'{v1_or_a1}_unlocked_untargeted_alone.png'),
            search_region=(x_time, y_time, x_time + 100, y_time + 1000)
        )
        if untargeted is None:
            untargeted = image_search(
                os.path.join(WORKING_DIR, f'{v1_or_a1}_locked_untargeted_alone.png'),
                search_region=(x_time, y_time, x_time + 100, y_time + 1000)
            )
        if untargeted:
            if v1_or_a1 == 'v1':
                keyboard.send('ctrl+f9')
                sleep(10)
                if on_off == 'off':
                    keyboard.send('shift+9')
                sleep(10)
                if number > 0:
                    keyboard.send(f'shift+{number}')
            elif v1_or_a1 == 'a1':
                keyboard.send('ctrl+shift+f9')
                sleep(10)
                if on_off == 'off':
                    keyboard.send('alt+9')
                sleep(10)
                if number > 0:
                    keyboard.send(f'alt+{number}')

    tooltip("")


def track_locker():
    """
    Toggle the lock state of V1 + A1 tracks simultaneously via image search.

    ⚠ REQUIRES reference PNGs in WORKING_DIR (tvh/config.py):
      v1_unlocked_targeted_2019_ui100.png
      v1_ALT_unlocked_targeted_2019_ui100.png
      v1_ALT_locked_targeted_2019_ui100.png
    """
    block_input(True)
    orig_x, orig_y = pyautogui.position()
    x_pos, y_pos = 450, 1000

    result = image_search(
        os.path.join(WORKING_DIR, 'v1_unlocked_targeted_2019_ui100.png'),
        search_region=(x_pos, y_pos, x_pos + 600, y_pos + 1000)
    )
    if result is None:
        result = image_search(
            os.path.join(WORKING_DIR, 'v1_ALT_unlocked_targeted_2019_ui100.png'),
            search_region=(x_pos, y_pos, x_pos + 600, y_pos + 1000)
        )

    if result:
        fx, fy = result
        pyautogui.moveTo(fx + 10, fy + 10, duration=0)
        sleep(5)
        pyautogui.click()
        pyautogui.moveTo(fx + 10, fy + 60, duration=0)
        pyautogui.click()
    else:
        result = image_search(
            os.path.join(WORKING_DIR, 'v1_ALT_locked_targeted_2019_ui100.png'),
            search_region=(x_pos, y_pos, x_pos + 600, y_pos + 1000)
        )
        if result:
            fx, fy = result
            pyautogui.moveTo(fx + 10, fy + 10, duration=0)
            sleep(5)
            pyautogui.click()
            pyautogui.moveTo(fx + 10, fy + 60, duration=0)
            pyautogui.click()
        else:
            tippy("track_locker: lock icon not found — add reference PNGs to WORKING_DIR in tvh/config.py")

    pyautogui.moveTo(orig_x, orig_y, duration=0)
    block_input(False)
    sleep(10)


def monitor_keys(which_monitor, shortcut, use_space=True):
    """
    Send a playback-resolution shortcut to the Source or Program monitor.
    which_monitor: 'source' or 'program'
    shortcut: key string to send (e.g. 'ctrl+shift+2')
    use_space: if True, toggles playback twice to apply the resolution change
    """
    if not is_premiere_active():
        return

    if which_monitor == 'source':
        pr_focus('source')
    else:
        pr_focus('program')
    sleep(20)

    keyboard.send(shortcut)

    if which_monitor != 'source':
        pr_focus('timeline')

    if use_space:
        keyboard.send('space')
        sleep(50)
        keyboard.send('space')
