"""tvh/panel_focus.py — reliably bring Premiere panels into focus."""

import keyboard

from .config import (
    EFFECTS_PANEL, TIMELINE_PANEL, PROGRAM_MONITOR,
    EFFECT_CONTROLS, PROJECT_PANEL, SOURCE_MONITOR, SELECT_FIND_BOX
)
from .utils import sleep, is_premiere_active


def pr_focus(panel):
    """
    Bring a Premiere panel into focus reliably.
    Sends Effects panel shortcut twice first as a neutral reset, then the target.
    panel: 'effects' | 'timeline' | 'program' | 'source' | 'project' | 'effect controls'
    """
    keyboard.send(EFFECTS_PANEL)
    sleep(12)
    keyboard.send(EFFECTS_PANEL)
    sleep(5)

    panel = panel.lower().strip()
    if panel == 'effects':
        pass
    elif panel == 'timeline':
        keyboard.send(TIMELINE_PANEL)
    elif panel == 'program':
        keyboard.send(PROGRAM_MONITOR)
    elif panel == 'source':
        keyboard.send(SOURCE_MONITOR)
    elif panel == 'project':
        keyboard.send(PROJECT_PANEL)
    elif panel in ('effect controls', 'effect_controls', 'effectcontrols'):
        keyboard.send(EFFECT_CONTROLS)


def effects_panel_find_box():
    """Focus the Effects panel and select its search box."""
    pr_focus('effects')
    keyboard.send(SELECT_FIND_BOX)


def effects_panel_type(item):
    """Type a search term into the Effects panel find box."""
    if not is_premiere_active():
        return
    keyboard.send(EFFECTS_PANEL)
    sleep(20)
    keyboard.send(SELECT_FIND_BOX)
    keyboard.send('shift+backspace')
    sleep(10)
    keyboard.write(item)
    keyboard.send('ctrl+alt+b')
