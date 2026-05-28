"""
tvh/config.py
=============
User-configurable settings for the tvh Premiere automation package.

SETUP REQUIRED:
  1. Set WORKING_DIR to the folder containing your reference PNG images.
  2. Assign the panel shortcuts below inside Premiere's Keyboard Shortcuts panel
     (Edit > Keyboard Shortcuts).  The defaults here match the original AHK script —
     change them to match whatever you set in Premiere.
  3. For clipboard functions: install InsideClipboard.exe and update its paths.
  4. For ease_in_and_out: assign Ease In (Ctrl+Shift+F10) and Ease Out (Shift+F10)
     in Premiere's Keyboard Shortcuts panel.
"""

import os

# ── File Paths ─────────────────────────────────────────────────────────────────
# Folder containing reference PNG images (track icons, crop transform icon, etc.)
WORKING_DIR = r'D:\Jarvis\ImageReference'

INSIDECLIPBOARD_EXE = r'C:\AHK\2nd-keyboard\insideclipboard\InsideClipboard.exe'
INSIDECLIPBOARD_DIR = r'C:\AHK\2nd-keyboard\insideclipboard\clipboards'

# ── Premiere Panel Shortcuts ───────────────────────────────────────────────────
# These MUST be assigned in Premiere's Keyboard Shortcuts panel to match.
SHUTTLE_STOP     = 'ctrl+alt+shift+k'   # Application > Shuttle Stop
EFFECTS_PANEL    = 'ctrl+alt+shift+7'   # Window > Effects
TIMELINE_PANEL   = 'ctrl+alt+shift+3'   # Window > Timeline
PROGRAM_MONITOR  = 'ctrl+alt+shift+4'   # Window > Program Monitor
EFFECT_CONTROLS  = 'ctrl+alt+shift+5'   # Window > Effect Controls
PROJECT_PANEL    = 'ctrl+alt+shift+1'   # Window > Project
SOURCE_MONITOR   = 'ctrl+alt+shift+2'   # Window > Source Monitor
SELECT_FIND_BOX  = 'ctrl+b'             # Select Find Box in Effects panel

# ── Editing Shortcuts ──────────────────────────────────────────────────────────
EASE_IN          = 'ctrl+shift+f10'     # Keyframe > Ease In  (assign in Premiere)
EASE_OUT         = 'shift+f10'          # Keyframe > Ease Out (assign in Premiere)
OVERWRITE        = 'ctrl+/'
CREATE_MARKER    = 'ctrl+;'
AUDIO_CHANNELS   = 'f3'                 # Clip > Audio Channels
DIRECT_MANIP     = 'f5'                 # Activate Direct Manipulation
EFFECT_CTRL_ALT  = 'f22'               # Alternative Effect Controls shortcut
TIMELINE_ALT     = 'f16'               # Alternative Timeline shortcut
SOURCE_ASSIGN    = 'ctrl+shift+9'
DESELECT_ALL     = 'ctrl+alt+f11'

# ── UI / Display ───────────────────────────────────────────────────────────────
UI_SCALE = 100   # 100 or 150 — affects pixel-based coordinate offsets

# ── Pixel Offsets (calibrated for UI_SCALE = 100) ─────────────────────────────
TRANSFORM_ICON_X_OFFSET = 56
TRANSFORM_ICON_Y_OFFSET = 66
TRIANGLE_X_OFFSET       = 13
TRIANGLE_Y_OFFSET       = 66
PRESET_ICON_X_OFFSET    = 41
PRESET_ICON_Y_OFFSET    = 63
MAG_GLASS_X_OFFSET      = -15
MAG_GLASS_Y_OFFSET      = 10
