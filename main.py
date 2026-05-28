import comtypes.client  # must be first: pre-initializes comtypes.gen before win32gui/sounddevice touch COM
import json
import logging
import os
import re
import site
import threading

# Register nvidia CUDA 12 DLL directories so ctranslate2/faster-whisper can find
# cublas64_12.dll. os.add_dll_directory() is required on Windows (Python 3.8+);
# PATH alone is not searched for DLL dependencies of extension modules.
for _site in site.getsitepackages():
    for _nvidia_pkg in ("cublas", "cuda_runtime", "cudnn"):
        _dll_dir = os.path.join(_site, "nvidia", _nvidia_pkg, "bin")
        if os.path.isdir(_dll_dir):
            os.add_dll_directory(_dll_dir)
            os.environ["PATH"] = _dll_dir + os.pathsep + os.environ["PATH"]
import time
import queue

import numpy as np
from faster_whisper import WhisperModel
import pyautogui
import sounddevice as sd
import win32gui
from openwakeword.model import Model
from rapidfuzz import fuzz

import openwakeword
import allowedCommands
import commandMethods
import mouse_tracker
from voice_ui import VoiceCutterUI
import sys

try:
    from premiere_writer import PremierMetadataWriter as _MetadataWriter
    _metadata_writer = _MetadataWriter()
except Exception as _e:
    print(f"premiere_writer unavailable: {_e}")
    _metadata_writer = None

try:
    import vosk
    vosk.SetLogLevel(-1)
    _vosk_available = True
except ImportError:
    _vosk_available = False
    print("Vosk not installed — pip install vosk to enable fast command recognition")

ui: VoiceCutterUI | None = None

# --- Configuration ---
SAMPLING_RATE = 16000

# Wake / sleep words
WakeUpWord = "hey_jarvis"
sleepWord = "go to sleep"

# Thread-safe signal for wake/sleep state (set = awake, cleared = asleep)
awake_event = threading.Event()

# Write mode: when True, spoken text is typed out instead of being processed as commands
write_mode = False

# Initialize OpenWakeWord
_oww_model_dir = os.path.join(os.path.dirname(openwakeword.__file__), "resources", "models")
oww_model = Model(wakeword_models=[os.path.join(_oww_model_dir, "hey_jarvis_v0.1.onnx")])

# Initialize faster-whisper (GPU with fallback to CPU)
_using_gpu = False
print("Loading Whisper model...")
try:
    print("  Attempting CUDA (GPU) with large-v3-turbo...")
    _whisper_model = WhisperModel("large-v3-turbo", device="cuda", compute_type="float16")
    _probe = np.zeros(SAMPLING_RATE, dtype=np.float32)
    list(_whisper_model.transcribe(_probe, language="en")[0])
    _using_gpu = True
    print("  GPU ready - large-v3-turbo (float16)")
except Exception as e:
    print(f"  CUDA unavailable ({e})")
    print("  Falling back to CPU - loading small.en...")
    _whisper_model = WhisperModel("small.en", device="cpu", compute_type="int8")
    print("  CPU ready - small.en (int8)")

# --- Vosk setup (small model on CPU — handles fixed command grammar) ---
VOSK_MODEL_PATH = os.path.join(os.path.dirname(__file__), "vosk-model-small-en-us")
_vosk_model = None
if _vosk_available:
    if os.path.isdir(VOSK_MODEL_PATH):
        print("Loading Vosk model...")
        _vosk_model = vosk.Model(VOSK_MODEL_PATH)
        print(f"  Vosk ready - vosk-model-small-en-us (CPU)")
    else:
        print(
            f"Vosk model not found at '{VOSK_MODEL_PATH}'.\n"
            "  Download vosk-model-small-en-us from https://alphacephei.com/vosk/models\n"
            "  and extract it as 'vosk-model-small-en-us' in the project directory.\n"
            "  Falling back to Whisper-only mode."
        )

_audio_queue: queue.Queue = queue.Queue()

# Start tracking mouse clicks so _effects_search() can drag to the last clicked spot
mouse_tracker.start()

# --- Logging ---
logging.basicConfig(filename="commands.log", level=logging.INFO, format="%(asctime)s - %(message)s", force=True)
logging.getLogger("httpx").setLevel(logging.WARNING)


# --- Post-STT Vocabulary Correction ---
_COMMAND_VOCAB = set()
for _cmd in allowedCommands.ALLOWED_COMMANDS:
    for _word in re.split(r"[\s_]+", _cmd):
        if len(_word) > 2:
            _COMMAND_VOCAB.add(_word)

# Load custom command keywords from customCommands.json into ALLOWED_COMMANDS so
# fast-matching can find them.
try:
    with open("customCommands.json", encoding="utf-8") as _f:
        _custom_data = json.load(_f)
    for _kw, _cmd in _custom_data.items():
        if _kw not in allowedCommands.ALLOWED_COMMANDS:
            allowedCommands.ALLOWED_COMMANDS.append(_kw)
        for _word in re.split(r"[\s_]+", _kw):
            if len(_word) > 2:
                _COMMAND_VOCAB.add(_word)
except (FileNotFoundError, json.JSONDecodeError):
    pass

# Load image reference names split by folder (Click/ → hold-click, Effects/ → effects search).
import image_matcher as _image_matcher_mod
_IMAGE_NAMES: set[str] = set()
_EFFECT_IMAGE_NAMES: set[str] = set()

def _reload_image_names():
    _IMAGE_NAMES.clear()
    _EFFECT_IMAGE_NAMES.clear()
    click_names, effect_names = _image_matcher_mod.list_references_by_type()
    _IMAGE_NAMES.update(click_names)
    _EFFECT_IMAGE_NAMES.update(effect_names)
    for name in click_names | effect_names:
        for _word in re.split(r"[\s_]+", name):
            if len(_word) > 2:
                _COMMAND_VOCAB.add(_word)

_reload_image_names()

# Auto-generate DPI-scaled copies for every image in Effects/ and Click/.
# Skips files that already exist, so this is fast after the first run.
# Also covers images the user adds manually — just restart Jarvis.
_image_matcher_mod.generate_dpi_versions()
_image_matcher_mod.build_reference_index()


def correct_vocabulary(text, threshold=80):
    """Correct STT misrecognitions toward known command vocabulary."""
    words = text.split()
    corrected = []
    for word in words:
        if word in _COMMAND_VOCAB or len(word) <= 2:
            corrected.append(word)
            continue

        best_match = None
        best_score = 0
        for vocab_word in _COMMAND_VOCAB:
            score = fuzz.ratio(word, vocab_word)
            if score > best_score:
                best_score = score
                best_match = vocab_word

        if best_score >= threshold:
            corrected.append(best_match)
        else:
            corrected.append(word)

    return " ".join(corrected)


# --- Filler words ---
FILLER_WORDS = frozenset({
    "a", "an", "the", "and", "then", "also", "please", "can", "you",
    "do", "just", "now", "right", "okay", "hey", "so", "um", "uh",
    "like", "well", "go", "ahead", "it", "that", "this",
})


# --- Key aliases ---
_KEY_ALIASES = {
    # Modifier keys
    "control": "ctrl", "ctrl": "ctrl",
    "left control": "ctrl", "right control": "ctrl",
    "shift": "shift", "left shift": "shift", "right shift": "shift",
    "alt": "alt", "left alt": "alt", "right alt": "alt",
    "windows": "win", "win": "win", "super": "win",
    # Common keys
    "enter": "enter", "return": "enter",
    "space": "space", "spacebar": "space",
    "tab": "tab",
    "escape": "escape", "esc": "escape",
    "backspace": "backspace", "back space": "backspace",
    "delete": "delete", "del": "delete",
    # Arrow keys
    "up": "up", "down": "down", "left": "left", "right": "right",
    "up arrow": "up", "down arrow": "down", "left arrow": "left", "right arrow": "right",
    # Navigation
    "home": "home", "end": "end",
    "page up": "pageup", "page down": "pagedown",
    # Function keys
    **{f"f{i}": f"f{i}" for i in range(1, 13)},
    # Punctuation / symbols
    "period": ".", "dot": ".",
    "comma": ",",
    "slash": "/", "forward slash": "/",
    "backslash": "\\",
    "dash": "-", "minus": "-", "hyphen": "-",
    "plus": "+",
    "equals": "=", "equal": "=",
    "semicolon": ";",
    "colon": ":",
    "quote": "'", "single quote": "'",
    "double quote": '"',
    "tilde": "`", "backtick": "`", "grave": "`",
    "bracket": "[", "left bracket": "[", "right bracket": "]",
}


# Phonetic letter aliases — ONLY applied inside the "press" keyword handler
_PRESS_PHONETIC = {
    "and": "n", "are": "r", "why": "y", "you": "u", "see": "c",
    "be": "b", "jay": "j", "kay": "k", "el": "l", "em": "m",
    "ex": "x", "zee": "z", "zed": "z", "queue": "q", "pee": "p",
    "tea": "t", "oh": "o", "eye": "i", "hey": "a", "dee": "d",
    "ef": "f", "gee": "g", "aitch": "h", "haitch": "h",
    "double you": "w", "double u": "w", "vee": "v", "ess": "s",
}

_MODIFIER_ALIASES = {
    "control": "ctrl", "ctrl": "ctrl",
    "left control": "ctrl", "right control": "ctrl",
    "shift": "shift", "left shift": "shift", "right shift": "shift",
    "alt": "alt", "left alt": "alt", "right alt": "alt",
    "windows": "win", "win": "win", "super": "win",
}


def _resolve_key(key_name: str) -> str | None:
    key_lower = key_name.lower().strip()
    if key_lower in _KEY_ALIASES:
        return _KEY_ALIASES[key_lower]
    if len(key_lower) == 1 and (key_lower.isalpha() or key_lower.isdigit()):
        return key_lower
    return None


def _parse_key_combo(key_name: str) -> tuple[list[str], str | None]:
    """Split 'control shift n' into (['ctrl', 'shift'], 'n').

    Modifiers are collected from the left; the first non-modifier token
    (and everything after it) is treated as the key.
    """
    tokens = key_name.lower().strip().split()
    modifiers: list[str] = []
    for i, token in enumerate(tokens):
        if token in _MODIFIER_ALIASES:
            modifiers.append(_MODIFIER_ALIASES[token])
        else:
            # Remaining tokens form the key name (handles "page up", "f1", etc.)
            key = _resolve_key(" ".join(tokens[i:]))
            return modifiers, key
    return modifiers, None


def _press_single_key(key_name: str) -> str | None:
    """Press a key or modifier+key combination.

    Supports:
        "t"               → press t
        "1"               → press 1
        "control n"       → Ctrl+N
        "ctrl shift z"    → Ctrl+Shift+Z
        "alt f4"          → Alt+F4
    """
    modifiers, key = _parse_key_combo(key_name)
    if not key:
        print(f"Unknown key: '{key_name}'")
        return None

    if modifiers:
        combo = modifiers + [key]
        print(f"Pressing combo: {' + '.join(combo)}")
        pyautogui.hotkey(*combo)
        logging.info(f"Key combo: {combo}")
        return "+".join(combo)
    else:
        print(f"Pressing key: '{key}'")
        pyautogui.press(key)
        logging.info(f"Key press: {key}")
        return key


# --- Hold / Release key state ---
_held_keys: set[str] = set()


def _hold_key(key_name: str) -> str | None:
    key = _resolve_key(key_name)
    if not key:
        print(f"Unknown key: '{key_name}'")
        return None
    if key in _held_keys:
        print(f"Key '{key}' is already held")
        return key
    print(f"Holding key: '{key}'")
    pyautogui.keyDown(key)
    _held_keys.add(key)
    logging.info(f"Key hold: {key}")
    return key


def _release_key(key_name: str) -> str | None:
    key = _resolve_key(key_name)
    if not key:
        print(f"Unknown key: '{key_name}'")
        return None
    if key not in _held_keys:
        print(f"Key '{key}' is not currently held - releasing anyway")
    pyautogui.keyUp(key)
    _held_keys.discard(key)
    logging.info(f"Key release: {key}")
    print(f"Released key: '{key}'")
    return key


def _release_all_keys():
    released = []
    for key in list(_held_keys):
        pyautogui.keyUp(key)
        released.append(key)
    _held_keys.clear()
    for btn in list(_held_mouse_buttons):
        pyautogui.mouseUp(button=btn)
        released.append(f"mouse:{btn}")
    _held_mouse_buttons.clear()
    # Unconditionally send mouseUp for every button regardless of tracking state.
    # click_image() calls pyautogui.mouseDown() directly, so if anything went
    # wrong with the tracking (image not found reported incorrectly, exception,
    # etc.) the physical button would still be held with no way to free it.
    # Sending mouseUp on a button that isn't down is a no-op, so this is safe.
    for _btn in ("left", "right", "middle"):
        if f"mouse:{_btn}" not in released:
            pyautogui.mouseUp(button=_btn)
    if released:
        logging.info(f"Released all: {released}")
        print(f"Released all: {released}")
    else:
        print("Nothing tracked as held — sent release signals to all mouse buttons anyway")


# --- Hold / Release mouse button state ---
_held_mouse_buttons: set[str] = set()

# Spoken phrases that resolve to a mouse button name.
# Only explicit "click" phrases are included — bare "left"/"right" resolve as arrow keys.
_MOUSE_BUTTON_ALIASES = {
    "left click": "left", "left-click": "left",
    "right click": "right", "right-click": "right",
    "middle click": "middle", "middle-click": "middle",
    "scroll click": "middle",
}


def _resolve_mouse_button(name: str) -> str | None:
    return _MOUSE_BUTTON_ALIASES.get(name.lower().strip())


def _hold_mouse_button(button_name: str) -> str | None:
    btn = _resolve_mouse_button(button_name)
    if not btn:
        return None
    if btn in _held_mouse_buttons:
        print(f"Mouse '{btn}' is already held")
        return btn
    print(f"Holding mouse button: '{btn}'")
    pyautogui.mouseDown(button=btn)
    _held_mouse_buttons.add(btn)
    logging.info(f"Mouse hold: {btn}")
    return btn


def _release_mouse_button(button_name: str) -> str | None:
    btn = _resolve_mouse_button(button_name)
    if not btn:
        return None
    if btn not in _held_mouse_buttons:
        print(f"Mouse '{btn}' is not currently held - releasing anyway")
    pyautogui.mouseUp(button=btn)
    _held_mouse_buttons.discard(btn)
    logging.info(f"Mouse release: {btn}")
    print(f"Released mouse button: '{btn}'")
    return btn


def _release_all_mouse_buttons():
    for btn in list(_held_mouse_buttons):
        pyautogui.mouseUp(button=btn)
    _held_mouse_buttons.clear()


# --- Mouse click helpers ---
_MOUSE_CLICK_ALIASES = {
    "left click":   "left",
    "left-click":   "left",
    "click":        "left",
    "right click":  "right",
    "right-click":  "right",
    "middle click": "middle",
    "middle-click": "middle",
    "scroll click": "middle",
}

_MOUSE_DOUBLE_ALIASES = {
    "double click":   "left",
    "double-click":   "left",
    "double left":    "left",
    "double right":   "right",
    "double middle":  "middle",
}


def _do_mouse_click(button: str, double: bool = False) -> str:
    action = "double-click" if double else "click"
    print(f"{action.capitalize()} [{button} button] at current cursor position")
    if double:
        pyautogui.doubleClick(button=button)
    else:
        pyautogui.click(button=button)
    logging.info(f"Mouse {action}: {button}")
    return f"{action} {button}"


def _focus_premiere():
    """Bring the Premiere Pro window to the foreground before sending keys."""
    try:
        target = None
        def _find(h, _):
            nonlocal target
            if win32gui.IsWindowVisible(h) and "Adobe Premiere Pro" in win32gui.GetWindowText(h):
                target = h
        win32gui.EnumWindows(_find, None)
        if target:
            if win32gui.GetForegroundWindow() == target:
                return                           # already focused — don't disturb panel focus
            if win32gui.IsIconic(target):        # only restore if actually minimised
                win32gui.ShowWindow(target, 9)   # SW_RESTORE
            win32gui.SetForegroundWindow(target)
            time.sleep(0.1)                      # let the OS finish the focus switch
    except Exception as e:
        print(f"Could not focus Premiere: {e}")


# "move left/right N" — focuses timeline then sends arrow keys
_MOVE_PATTERN = re.compile(
    r"^(?:move\s+)?(left|right|up|down)\s+(\d+|once|twice|one|two|three|four|five|six|seven|eight|nine|ten)(?:\s+times?)?$"
)

# ── tvh parameterized patterns ────────────────────────────────────────────────
_NUMS_EXTENDED = r"once|twice|one|two|three|four|five|six|seven|eight|nine|ten|twelve|fifteen|twenty"
_GAIN_PATTERN = re.compile(
    rf"^(?:add\s+)?(?:gain|boost)\s+(\d+|{_NUMS_EXTENDED})$"
)
_SCRUB_PATTERN = re.compile(r"^(?:scrub|adjust|change)\s+(.+)$")
_PRESET_PATTERN = re.compile(r"^(?:apply\s+)?preset\s+(.+)$")
_SAVE_CLIP_PATTERN = re.compile(
    rf"^(?:save\s+clip|save\s+clipboard)\s+(\d+|{_NUMS_EXTENDED})$"
)
_RECALL_CLIP_PATTERN = re.compile(
    rf"^(?:(?:paste|recall)\s+clip|recall\s+clipboard)\s+(\d+|{_NUMS_EXTENDED})$"
)
_GAIN_NUMS = {
    "once": 1, "one": 1, "twice": 2, "two": 2, "three": 3, "four": 4,
    "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
    "twelve": 12, "fifteen": 15, "twenty": 20,
}

# "search <query>" — click calibrated search bar and type the spoken query
_SEARCH_QUERY_PATTERN = re.compile(r"^search\s+(.+)$")


def _do_search_query(query: str) -> None:
    """Click the calibrated search bar, clear it, type the query, and confirm."""
    import search_calibration
    import pyperclip
    _focus_premiere()
    time.sleep(0.15)
    sx, sy = search_calibration.get_or_calibrate_search_bar()
    with mouse_tracker.suppress_clicks():
        pyautogui.click(sx, sy)
    time.sleep(0.15)
    pyautogui.hotkey("ctrl", "a")   # select-all so first char clears old text
    old_clip = pyperclip.paste()
    pyperclip.copy(query)
    pyautogui.hotkey("ctrl", "v")
    time.sleep(0.1)
    pyperclip.copy(old_clip)
    pyautogui.press("enter")
    print(f"[search] '{query}'")
    logging.info(f"Search query: '{query}'")


# Labeled marker pattern — "[color] marker <title>"
# e.g. "marker wright's chapel intro"  /  "red marker act two"
_LABELED_MARKER_PATTERN = re.compile(
    r"^(?:(red|green|blue|violet|orange|yellow|cyan|white)\s+)?marker\s+(.+)$"
)

# "[color] <title>" — color word directly followed by a label, no "marker" keyword.
# e.g. "red chapter two" / "yellow b-roll" / "cyan interview"
_COLOR_MARKER_DIRECT_PATTERN = re.compile(
    r"^(red|green|blue|violet|orange|yellow|cyan|white)\s+(.+)$"
)

# Color words that should trigger a Whisper re-run so a title spoken in the
# same breath as the color is captured (mirrors the "press" re-run strategy).
_MARKER_COLOR_WORDS: frozenset[str] = frozenset(
    {"red", "green", "blue", "violet", "orange", "yellow", "cyan", "white"}
)

# Color → Premiere hotkey (matches commandMethods.py marker shortcuts)
_MARKER_COLOR_KEYS: dict[str, tuple[str, ...]] = {
    "green":  ("m",),
    "red":    ("alt", "1"),
    "orange": ("alt", "2"),
    "yellow": ("alt", "3"),
    "cyan":   ("alt", "4"),
    "blue":   ("alt", "5"),
    "violet": ("alt", "6"),
    "white":  ("alt", "7"),
}


# --- Labeled marker ---
def _do_labeled_marker(title: str, color: str = "green") -> None:
    """Create a colored marker at playhead and label it via the Edit Marker dialog.

    Flow:
      1. Press the color hotkey  → creates the marker (green = plain M)
      2. Press M again           → opens the Edit Marker dialog for that marker
      3. Ctrl+A + Ctrl+V         → clears the name field and pastes the spoken title
      4. Enter                   → confirms
    Clipboard is restored afterward so the user's copy buffer is untouched.
    """
    import pyperclip
    _focus_premiere()
    time.sleep(0.2)

    keys = _MARKER_COLOR_KEYS.get(color, ("m",))
    if len(keys) == 1:
        pyautogui.press(keys[0])
    else:
        pyautogui.hotkey(*keys)
    time.sleep(0.3)

    # Open Edit Marker dialog
    pyautogui.press("m")
    time.sleep(1.2)

    old_clip = pyperclip.paste()
    pyperclip.copy(title)
    pyautogui.hotkey("ctrl", "a")
    time.sleep(0.05)
    pyautogui.hotkey("ctrl", "v")
    time.sleep(0.1)
    pyperclip.copy(old_clip)

    pyautogui.press("enter")
    logging.info(f"[marker] {color} — '{title}'")
    print(f"[marker] {color} — '{title}'")


# --- Span marker ---
def _do_span_marker() -> None:
    """Hold Alt so the user can click-drag to create a range marker, then auto-release.

    Starts a daemon thread that watches for a left-click press+release and then
    lifts Alt, so voice recognition keeps running while the user drags.
    """
    _focus_premiere()
    time.sleep(0.2)

    pyautogui.keyDown("alt")
    _held_keys.add("alt")
    print("[span] Alt held — drag the marker edge, then release.")
    if ui:
        ui.add_command_history("span", "Alt held — drag marker edge now")

    def _finish():
        try:
            import win32api
            # Wait for left mouse button to go down, then come back up
            while not (win32api.GetAsyncKeyState(0x01) & 0x8000):
                time.sleep(0.03)
            while win32api.GetAsyncKeyState(0x01) & 0x8000:
                time.sleep(0.03)
        except Exception:
            time.sleep(3.0)  # fallback: release after 3 s if win32api unavailable
        pyautogui.keyUp("alt")
        _held_keys.discard("alt")
        logging.info("Span marker drag complete.")
        print("[span] Done.")
        if ui:
            ui.add_command_history("span", "drag complete")

    threading.Thread(target=_finish, daemon=True).start()


# --- Trigger commands ---
def _load_trigger_commands() -> dict:
    """Load triggerCommands.json, ignoring the _instructions entry."""
    path = "triggerCommands.json"
    if not os.path.exists(path):
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return {k: v for k, v in data.items() if not k.startswith("_")}
    except Exception as e:
        print(f"[triggers] Failed to load {path}: {e}")
        return {}


def _execute_trigger_command(config: dict, title: str):
    """Run the script assigned to this trigger, passing the spoken text as argv[1]."""
    import subprocess

    script_path = config.get("path", "")
    if not script_path or not os.path.exists(script_path):
        print(f"[trigger] Script not found: '{script_path}'")
        logging.warning(f"Trigger script not found: '{script_path}'")
        return

    print(f"[trigger] Running '{script_path}' with: '{title}'")
    logging.info(f"Trigger: '{script_path}' — '{title}'")

    try:
        subprocess.Popen([sys.executable, script_path, title])
    except Exception as e:
        print(f"[trigger] Error running script: {e}")
        logging.error(f"Trigger script error: {e}")


def _should_fast_match(clean_text, found_matches):
    """Decide if input is a pure command (fast-match).

    Strips matched commands and filler words from the input.
    If nothing meaningful remains -> fast-match.
    """
    if not found_matches:
        return False
    residue = clean_text
    for _, cmd in sorted(found_matches, key=lambda m: len(m[1]), reverse=True):
        residue = residue.replace(cmd, "", 1)
    remaining_tokens = [tok for tok in residue.split() if tok not in FILLER_WORDS]
    return len(remaining_tokens) == 0


# --- Wake word listener ---
def wakeListener():
    SAMPLE_RATE = 16000
    FRAME_LENGTH = 1280
    CONFIDENCE_THRESHOLD = 0.5

    oww_model.reset()
    time.sleep(0.5)

    with sd.RawInputStream(
        samplerate=SAMPLE_RATE,
        blocksize=FRAME_LENGTH,
        dtype="int16",
        channels=1,
    ) as stream:
        print("Listening for wake word...")

        # Drain stale audio
        for _ in range(5):
            stream.read(FRAME_LENGTH)

        while True:
            audio, _ = stream.read(FRAME_LENGTH)
            pcm = np.frombuffer(audio, dtype=np.int16)

            predictions = oww_model.predict(pcm)

            if any(conf > CONFIDENCE_THRESHOLD for conf in predictions.values()):
                print("Wake word detected!")
                if ui:
                    ui.set_listening()
                return


_WORD_NUMS = {
    "once": 1, "one": 1, "twice": 2, "two": 2, "three": 3, "four": 4,
    "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
}


# Commands that naturally contain " and " — exempt from the chain splitter so
# "clear in and out" and "ease in and out" are never split mid-name.
_AND_EXEMPT: frozenset = frozenset(
    cmd for cmd in allowedCommands.ALLOWED_COMMANDS if " and " in cmd
)


# ── Merge-window ────────────────────────────────────────────────────────────
# Prevents a compound command (e.g. "center split") from being mis-executed as
# two separate commands ("center" then "split") when Vosk emits them as
# back-to-back results.  If the recognised command is a known prefix of a
# compound command, Jarvis waits _MERGE_WINDOW_SEC for the next Vosk result.
# • Next result completes a compound → execute the compound.
# • Next result doesn't form a compound → flush the held command first, then
#   process the new result normally.
# • No second result arrives within the window → flush and execute as-is.

_compound_set: frozenset[str] = frozenset(allowedCommands.ALLOWED_COMMANDS)

# Map: command → [(suffix, compound), …] for every split of a compound where
# the left part is itself a valid standalone command.
_potential_prefixes: dict[str, list[tuple[str, str]]] = {}
for _cmd in allowedCommands.ALLOWED_COMMANDS:
    _parts = _cmd.split()
    for _i in range(1, len(_parts)):
        _left  = " ".join(_parts[:_i])
        _right = " ".join(_parts[_i:])
        if _left in _compound_set:
            _potential_prefixes.setdefault(_left, []).append((_right, _cmd))

_MERGE_WINDOW_SEC: float = 0.7
_merge_pending: str | None = None
_merge_timer: threading.Timer | None = None
_merge_lock = threading.Lock()


def _flush_merge_pending():
    """Timer callback — merge window expired; execute the held command as-is."""
    global _merge_pending, _merge_timer
    with _merge_lock:
        cmd = _merge_pending
        _merge_pending = None
        _merge_timer = None
    if cmd:
        print(f"[merge] Flushed: '{cmd}'")
        logging.info(f"Merge-flush: '{cmd}'")
        _focus_premiere()
        commandMethods.Command(cmd).execute()
        if ui:
            ui.add_command_history(cmd, cmd)


def _try_merge(incoming: str) -> bool:
    """Check whether *incoming* completes a compound with the pending command.

    Returns True and executes the compound if matched.
    Flushes the pending command and returns False if no compound is formed
    (caller should then process *incoming* normally).
    """
    global _merge_pending, _merge_timer
    with _merge_lock:
        if _merge_pending is None:
            return False
        pending = _merge_pending
        old_timer = _merge_timer
        _merge_pending = None
        _merge_timer = None

    if old_timer:
        old_timer.cancel()

    # 1. Suffix-based compound match  ("center" + "split" → "center split")
    for suffix, compound in _potential_prefixes.get(pending, []):
        if incoming == suffix:
            print(f"[merge] Compound: '{pending}' + '{incoming}' → '{compound}'")
            logging.info(f"Merge: '{compound}' (from '{pending}' + '{incoming}')")
            _focus_premiere()
            commandMethods.Command(compound).execute()
            if ui:
                ui.add_command_history(f"{pending} {incoming}", compound)
            return True

    # 2. Direct combined-string match
    #    (Vosk already output the full compound while we were holding)
    combined = pending + " " + incoming
    if combined in _compound_set:
        print(f"[merge] Compound (direct): '{combined}'")
        logging.info(f"Merge (direct): '{combined}'")
        _focus_premiere()
        commandMethods.Command(combined).execute()
        if ui:
            ui.add_command_history(combined, combined)
        return True

    # 3. No compound — flush the held command, let caller process incoming
    print(f"[merge] No compound for '{pending}' + '{incoming}', flushing '{pending}'")
    logging.info(f"Merge-flush (no compound): '{pending}'")
    _focus_premiere()
    commandMethods.Command(pending).execute()
    if ui:
        ui.add_command_history(pending, pending)
    return False


def _hold_for_merge(cmd: str):
    """Hold *cmd* for _MERGE_WINDOW_SEC before executing it."""
    global _merge_pending, _merge_timer
    with _merge_lock:
        old_timer = _merge_timer
        _merge_pending = cmd
        new_timer = threading.Timer(_MERGE_WINDOW_SEC, _flush_merge_pending)
        new_timer.daemon = True
        _merge_timer = new_timer
    if old_timer:
        old_timer.cancel()
    new_timer.start()
    print(f"[merge] Holding '{cmd}' for {_MERGE_WINDOW_SEC}s…")


# --- Core command processing ---
def processVoiceInput(text):
    # Strip punctuation for matching
    clean_text = re.sub(r"[^\w\s]", "", text.lower().strip())
    if not clean_text:
        return

    # MERGE WINDOW — if a prefix command is pending, try to form a compound
    if _merge_pending is not None and _try_merge(clean_text):
        return

    # "press <key combo>" — send any keystroke directly, e.g. "press control n"
    if clean_text.startswith("press "):
        key_text = clean_text[6:].strip()

        # ── Chain detection ────────────────────────────────────────────────────
        # "press a and press z" must be split BEFORE phonetic correction runs,
        # because _PRESS_PHONETIC maps "and" → "n" (the letter N), which would
        # otherwise mangle the conjunction into garbage like "a n press z".
        # The pattern "… and press …" unambiguously marks chained presses;
        # plain "press control and z" (a hotkey with no second "press") is
        # unaffected because it never contains the substring "and press".
        _press_chain = re.split(r"\s+and\s+press\s+", key_text)
        if len(_press_chain) > 1:
            _chain_results = []
            for _part in _press_chain:
                # Apply phonetic correction to each segment individually
                _pt = _part.strip().split()
                _pc = []
                _pi = 0
                while _pi < len(_pt):
                    _two = " ".join(_pt[_pi:_pi + 2])
                    if _two in _PRESS_PHONETIC:
                        _pc.append(_PRESS_PHONETIC[_two])
                        _pi += 2
                    elif _pt[_pi] in _PRESS_PHONETIC:
                        _pc.append(_PRESS_PHONETIC[_pt[_pi]])
                        _pi += 1
                    else:
                        _pc.append(_pt[_pi])
                        _pi += 1
                _pk = " ".join(_pc)
                _focus_premiere()
                _pr = _press_single_key(_pk)
                _chain_results.append(_pr if _pr else f"?{_pk}")
            chain_summary = " → ".join(f"press {r}" for r in _chain_results)
            print(f"[Press chain] {chain_summary}")
            logging.info(f"Press chain: {_chain_results}")
            if ui:
                ui.add_command_history(clean_text, chain_summary)
            return
        # ──────────────────────────────────────────────────────────────────────

        # ── Repeat detection ──────────────────────────────────────────────────
        # "press tab 5 times" / "press enter twice" — must be caught before
        # phonetic correction so "tab 5 times" isn't treated as a key name.
        _press_repeat = re.match(
            r"^(.+?)\s+(\d+|once|twice|one|two|three|four|five|six|seven|eight|nine|ten)\s+times?$",
            key_text,
        )
        if _press_repeat:
            _rkey_raw  = _press_repeat.group(1).strip()
            _rcount_raw = _press_repeat.group(2)
            _rcount = _WORD_NUMS.get(_rcount_raw, int(_rcount_raw) if _rcount_raw.isdigit() else 1)
            _rcount = max(1, min(_rcount, 20))
            # Apply phonetic correction to the extracted key
            _rt, _rc, _ri = _rkey_raw.split(), [], 0
            while _ri < len(_rt):
                _rtwo = " ".join(_rt[_ri:_ri + 2])
                if _rtwo in _PRESS_PHONETIC:
                    _rc.append(_PRESS_PHONETIC[_rtwo]); _ri += 2
                elif _rt[_ri] in _PRESS_PHONETIC:
                    _rc.append(_PRESS_PHONETIC[_rt[_ri]]); _ri += 1
                else:
                    _rc.append(_rt[_ri]); _ri += 1
            _rkey = " ".join(_rc)
            _focus_premiere()
            for _ri2 in range(_rcount):
                _press_single_key(_rkey)
                if _ri2 < _rcount - 1:
                    time.sleep(0.05)
            print(f"[Press repeat] '{_rkey}' x{_rcount}")
            logging.info(f"Press repeat: '{_rkey}' x{_rcount}")
            if ui:
                ui.add_command_history(clean_text, f"press {_rkey} x{_rcount}")
            return
        # ──────────────────────────────────────────────────────────────────────

        # Apply phonetic letter corrections (e.g. "and" → "n") only here
        tokens = key_text.split()
        corrected = []
        i = 0
        while i < len(tokens):
            two_word = " ".join(tokens[i:i+2])
            if two_word in _PRESS_PHONETIC:
                corrected.append(_PRESS_PHONETIC[two_word])
                i += 2
            elif tokens[i] in _PRESS_PHONETIC:
                corrected.append(_PRESS_PHONETIC[tokens[i]])
                i += 1
            else:
                corrected.append(tokens[i])
                i += 1
        key_text = " ".join(corrected)
        _focus_premiere()
        result = _press_single_key(key_text)
        if result:
            print(f"Pressed: {result}")
            logging.info(f"Press command: '{result}'")
            if ui:
                ui.add_command_history(clean_text, f"press {result}")
        else:
            print(f"[press] Unknown key: '{key_text}'")
            if ui:
                ui.add_command_history(clean_text, f"(unknown key: {key_text})")
        return

    # Metadata log commands — intercepted before vocab correction or fuzzy matching
    if _metadata_writer is not None and (clean_text.startswith("log ") or clean_text == "log"):
        _wrote = _metadata_writer.execute(text)
        status = "rows written" if _wrote else "control command"
        logging.info(f"Metadata log: '{text}'")
        if ui:
            ui.add_command_history(clean_text, f"[log] {status}")
        return

    # CHAIN SYNTAX — "X and Y and Z" runs each part in sequence.
    # Split on " and " unless the whole phrase is a known command containing "and".
    if " and " in clean_text and clean_text not in _AND_EXEMPT:
        parts = [p.strip() for p in clean_text.split(" and ") if p.strip()]
        if len(parts) > 1:
            print(f"Chain x{len(parts)}: {parts}")
            for part in parts:
                processVoiceInput(part)
            if ui:
                ui.add_command_history(clean_text, " → ".join(parts))
            return

    # "move left/right/up/down N" — focuses Premiere first, then sends arrow keys
    move_match = _MOVE_PATTERN.match(clean_text)
    if move_match:
        direction = move_match.group(1)
        count_raw = move_match.group(2)
        count = _WORD_NUMS.get(count_raw, int(count_raw) if count_raw.isdigit() else 1)
        count = max(1, min(count, 100))
        print(f"Move {direction} x{count}")
        _focus_premiere()
        time.sleep(0.1)
        for i in range(count):
            pyautogui.press(direction)
            if i < count - 1:
                time.sleep(0.05)
        if ui:
            ui.add_command_history(clean_text, f"arrow {direction} x{count}")
        return

    # ── tvh: "gain <n>" / "boost <n>" / "add gain <n>" ──────────────────────────
    gain_match = _GAIN_PATTERN.match(clean_text)
    if gain_match:
        amount_raw = gain_match.group(1)
        amount = _GAIN_NUMS.get(amount_raw, int(amount_raw) if amount_raw.isdigit() else 7)
        print(f"Add gain: {amount} dB")
        from tvh.audio import add_gain
        add_gain(amount)
        if ui:
            ui.add_command_history(clean_text, f"gain +{amount} dB")
        return

    # "span" → hold Alt so user can click-drag a range marker
    if clean_text == "span":
        _do_span_marker()
        return

    # "[color] marker <title>" → create a labeled marker in the chosen color
    marker_match = _LABELED_MARKER_PATTERN.match(clean_text)
    if marker_match:
        color = marker_match.group(1) or "green"
        title = marker_match.group(2).strip()
        _do_labeled_marker(title, color)
        if ui:
            ui.add_command_history(clean_text, f"{color} marker: '{title}'")
        return

    # "[color] <title>" — same but without the "marker" keyword.
    # Reached when Whisper transcribes the full "red chapter two" phrase.
    color_direct_match = _COLOR_MARKER_DIRECT_PATTERN.match(clean_text)
    if color_direct_match:
        _cd_color = color_direct_match.group(1)
        _cd_title = color_direct_match.group(2).strip()
        _do_labeled_marker(_cd_title, _cd_color)
        if ui:
            ui.add_command_history(clean_text, f"{_cd_color} marker: '{_cd_title}'")
        return

    # "search <query>" — click calibrated search bar and type the spoken query.
    # Whisper already re-ran on the same audio in the Vosk path, so clean_text
    # here is the full phrase (e.g. "search wright chapel intro").
    search_match = _SEARCH_QUERY_PATTERN.match(clean_text)
    if search_match:
        _sq_query = search_match.group(1).strip()
        _do_search_query(_sq_query)
        if ui:
            ui.add_command_history(clean_text, f"search: '{_sq_query}'")
        return

    # ── tvh: "scrub <param>" / "adjust <param>" ──────────────────────────────
    scrub_match = _SCRUB_PATTERN.match(clean_text)
    if scrub_match:
        param_text = scrub_match.group(1).strip()
        print(f"VFX scrub: '{param_text}'")
        from tvh.vfx_scrubber import instant_vfx
        _VFX_PARAM_MAP = {
            "scale": "scale", "rotation": "rotation",
            "anchor point": "anchor_point", "horizontal anchor": "anchor_point",
            "vertical anchor": "anchor_point_vertical", "anchor vertical": "anchor_point_vertical",
        }
        from rapidfuzz import process as _rp, fuzz as _rf
        vfx_match = _rp.extractOne(param_text, list(_VFX_PARAM_MAP.keys()), scorer=_rf.WRatio, score_cutoff=60)
        if vfx_match:
            param = _VFX_PARAM_MAP[vfx_match[0]]
            instant_vfx(param)
            if ui:
                ui.add_command_history(clean_text, f"scrub {param}")
        else:
            print(f"Unknown VFX param: '{param_text}'")
            if ui:
                ui.add_command_history(clean_text, "(unknown VFX param)")
        return

    # ── tvh: "preset <name>" / "apply preset <name>" ─────────────────────────
    preset_match = _PRESET_PATTERN.match(clean_text)
    if preset_match:
        preset_name = preset_match.group(1).strip()
        print(f"Apply preset: '{preset_name}'")
        from tvh.preset_applier import preset
        preset(preset_name)
        if ui:
            ui.add_command_history(clean_text, f"preset '{preset_name}'")
        return

    # ── tvh: "save clip <n>" / "save clipboard <n>" ───────────────────────────
    save_clip_match = _SAVE_CLIP_PATTERN.match(clean_text)
    if save_clip_match:
        slot_raw = save_clip_match.group(1)
        slot = _GAIN_NUMS.get(slot_raw, int(slot_raw) if slot_raw.isdigit() else None)
        if slot:
            print(f"Save clipboard slot: {slot}")
            from tvh.clipboard import save_clipboard
            save_clipboard(slot)
            if ui:
                ui.add_command_history(clean_text, f"saved clip{slot}.clp")
        return

    # ── tvh: "recall clip <n>" / "paste clip <n>" ────────────────────────────
    recall_clip_match = _RECALL_CLIP_PATTERN.match(clean_text)
    if recall_clip_match:
        slot_raw = recall_clip_match.group(1)
        slot = _GAIN_NUMS.get(slot_raw, int(slot_raw) if slot_raw.isdigit() else None)
        if slot:
            print(f"Recall clipboard slot: {slot}")
            from tvh.clipboard import recall_clipboard
            recall_clipboard(slot)
            if ui:
                ui.add_command_history(clean_text, f"recalled clip{slot}.clp")
        return

    # "[trigger word] <title>" → look up triggerCommands.json and execute
    _triggers = _load_trigger_commands()
    for _trigger, _config in sorted(_triggers.items(), key=lambda x: len(x[0]), reverse=True):
        _t_match = re.match(rf"^{re.escape(_trigger)}\s+(.+)$", clean_text)
        if _t_match:
            _title = _t_match.group(1).strip()
            _execute_trigger_command(_config, _title)
            if ui:
                ui.add_command_history(clean_text, f"{_trigger}: '{_title}'")
            return

    # REPEAT SYNTAX — "X N times" / "X twice" etc.
    # Must be checked before everything else so "press e 3 times" works end-to-end.
    repeat_match = re.match(
        r"^(.+?)\s+(\d+|once|twice|one|two|three|four|five|six|seven|eight|nine|ten)\s+times?$",
        clean_text,
    )
    if repeat_match:
        base_cmd = repeat_match.group(1).strip()
        count_raw = repeat_match.group(2)
        count = _WORD_NUMS.get(count_raw, int(count_raw) if count_raw.isdigit() else 1)
        count = max(1, min(count, 20))  # safety cap
        print(f"Repeat x{count}: '{base_cmd}'")
        _focus_premiere()
        time.sleep(0.1)
        for i in range(count):
            processVoiceInput(base_cmd)
            if i < count - 1:
                time.sleep(0.15)
        if ui:
            ui.add_command_history(clean_text, f"{base_cmd} x{count}")
        return

    # "hold <key or mouse button>"
    hold_match = re.match(r"^hold\s+(.+)$", clean_text)
    if hold_match:
        hold_name = hold_match.group(1).strip()
        # Try keyboard key first; only fall through to mouse if phrase contains "click"
        _focus_premiere()
        held_key = _hold_key(hold_name)
        if held_key:
            if ui:
                ui.add_command_history(clean_text, f"hold '{held_key}'")
            return
        held_btn = _hold_mouse_button(hold_name)
        if held_btn:
            if ui:
                ui.add_command_history(clean_text, f"hold mouse '{held_btn}'")
            return

    # "<modifier> down" → hold that key  (e.g. "shift down", "alt down", "control down")
    key_down_match = re.match(r"^(shift|alt|control|ctrl|command|cmd|win)\s+down$", clean_text)
    if key_down_match:
        _focus_premiere()
        held_key = _hold_key(key_down_match.group(1))
        if held_key and ui:
            ui.add_command_history(clean_text, f"hold '{held_key}'")
        return

    # "release" alone or "release all" → release everything held (keys + mouse)
    if clean_text in ("release", "release all", "release all keys"):
        _release_all_keys()
        if ui:
            ui.add_command_history(clean_text, "released all")
        return

    # "release <key or mouse button>" → release only that one
    release_match = re.match(r"^release\s+(.+)$", clean_text)
    if release_match:
        release_name = release_match.group(1).strip()
        # Try mouse button first, then keyboard key
        released_btn = _release_mouse_button(release_name)
        if released_btn:
            if ui:
                ui.add_command_history(clean_text, f"release mouse '{released_btn}'")
            return
        released_key = _release_key(release_name)
        if released_key and ui:
            ui.add_command_history(clean_text, f"release '{released_key}'")
        return

    # "<modifier> up" → release that key  (e.g. "shift up", "alt up", "control up")
    key_up_match = re.match(r"^(shift|alt|control|ctrl|command|cmd|win)\s+up$", clean_text)
    if key_up_match:
        released_key = _release_key(key_up_match.group(1))
        if released_key and ui:
            ui.add_command_history(clean_text, f"release '{released_key}'")
        return

    # Mouse clicks
    if clean_text in _MOUSE_DOUBLE_ALIASES:
        btn = _MOUSE_DOUBLE_ALIASES[clean_text]
        result = _do_mouse_click(btn, double=True)
        if ui:
            ui.add_command_history(clean_text, result)
        return
    if clean_text in _MOUSE_CLICK_ALIASES:
        btn = _MOUSE_CLICK_ALIASES[clean_text]
        result = _do_mouse_click(btn, double=False)
        if ui:
            ui.add_command_history(clean_text, result)
        return

    # "click <name>" → open Effect Controls, then image-match and hold left mouse.
    # Restricted to ImageReference/Click/ so effects (Effects/) aren't picked up here.
    # Names ending in " y" (position y, anchor y) target the second blue value on the row.
    _SECOND_BLUE_TARGETS = {"position y", "anchor y", "anchor point y"}
    click_img_match = re.match(r"^click\s+(.+)$", clean_text)
    if click_img_match:
        import image_matcher
        target = click_img_match.group(1).strip()
        blue_idx = 1 if target in _SECOND_BLUE_TARGETS else 0
        pyautogui.hotkey("shift", "5")   # open Effect Controls before searching
        time.sleep(0.3)
        found, cx, cy = image_matcher.click_image(
            target, click_blue=True, subfolder=image_matcher.CLICK_SUBDIR,
            blue_index=blue_idx,
        )
        if found:
            # Register the held button so "release" / "release left click" can free it
            _held_mouse_buttons.add("left")
            logging.info(f"Image match hold: '{target}' at ({cx}, {cy})")
            if ui:
                ui.add_command_history(clean_text, f"holding '{target}' at ({cx},{cy})")
        else:
            if ui:
                ui.add_command_history(clean_text, f"'{target}' not found")
        return

    # Single character → press it directly (e.g. "v", "c", "1")
    if len(clean_text) == 1 and (clean_text.isalpha() or clean_text.isdigit()):
        print(f"Pressing key: '{clean_text}'")
        _focus_premiere()
        pyautogui.press(clean_text)
        logging.info(f"Key press: {clean_text}")
        if ui:
            ui.add_command_history(clean_text, f"press '{clean_text}'")
        return

    # Bare key name → press it (e.g. "backspace", "enter", "escape", "tab")
    bare_key = _resolve_key(clean_text)
    if bare_key:
        print(f"Pressing key: '{bare_key}'")
        _focus_premiere()
        pyautogui.press(bare_key)
        logging.info(f"Key press: {bare_key}")
        if ui:
            ui.add_command_history(clean_text, f"press '{bare_key}'")
        return

    # Correct STT misrecognitions.
    # Save the pre-correction version so param text (names, free-form phrases)
    # isn't mangled when we extract it below.
    pre_correction_clean = clean_text
    clean_text = correct_vocabulary(clean_text)

    # PARAMETERISED SCRIPT COMMANDS — checked before fast-match.
    # If clean_text starts with a keyword that has accepts_params=True, extract
    # everything after it as the parameter and run the script.
    try:
        with open("customCommands.json", encoding="utf-8") as _pf:
            _pcmds = json.load(_pf)
        # Longest keyword first so "search bar" is tried before "search"
        for _pkw in sorted(_pcmds, key=len, reverse=True):
            _pcmd = _pcmds[_pkw]
            if (
                isinstance(_pcmd, dict)
                and _pcmd.get("accepts_params")
                and _pcmd.get("type") == "script"
                and (clean_text == _pkw or clean_text.startswith(_pkw + " "))
            ):
                # Use pre-correction text for the param so names stay intact
                _param = pre_correction_clean[len(_pkw):].strip()
                print(f"[params] '{_pkw}' ← '{_param}'")
                logging.info(f"Params command: '{_pkw}' params='{_param}'")
                commandMethods.Command(_pkw)._run_script_with_params(_pcmd["path"], _param)
                if ui:
                    _plabel = f"{_param[:20]}…" if len(_param) > 20 else _param
                    ui.add_command_history(clean_text, f"{_pkw}({_plabel})")
                return
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        pass

    # FAST-MATCH (fuzzy matching against command list)
    command_list = allowedCommands.ALLOWED_COMMANDS
    found_matches = []
    consumed_ranges = []

    # Sort commands longest-first so "save as" is checked before "save"
    for cmd in sorted(command_list, key=len, reverse=True):
        if fuzz.partial_ratio(cmd, clean_text) > 95:
            idx = clean_text.find(cmd)
            if idx != -1:
                cmd_end = idx + len(cmd)
                overlaps = any(
                    idx < ex_end and cmd_end > ex_start
                    for ex_start, ex_end in consumed_ranges
                )
                if not overlaps:
                    found_matches.append((idx, cmd))
                    consumed_ranges.append((idx, cmd_end))

    found_matches.sort()  # Re-sort by position for execution order

    if _should_fast_match(clean_text, found_matches):
        cmd_names = [cmd for _, cmd in found_matches]
        print(f"Fast Multi-Match: {cmd_names}")
        logging.info(f"Fast-match: {cmd_names} (from: '{clean_text}')")
        # MERGE WINDOW: if it's a single command that starts a known compound,
        # hold it briefly in case the next Vosk result completes the compound.
        if len(cmd_names) == 1 and cmd_names[0] in _potential_prefixes:
            _hold_for_merge(cmd_names[0])
            return
        _focus_premiere()          # ensure Premiere has focus before any hotkey fires
        for cmd_name in cmd_names:
            commandMethods.Command(cmd_name).execute()
            time.sleep(0.2)
        if ui:
            ui.add_command_history(clean_text, ", ".join(cmd_names))
        return

    # FUZZY SNAP — catch mishearings like "frost dissolve" → "cross dissolve"
    from rapidfuzz import process as _fuzz_process
    _snap_match = _fuzz_process.extractOne(
        clean_text,
        command_list,
        scorer=fuzz.ratio,
        score_cutoff=82,
    )
    if _snap_match:
        _snap_cmd, _snap_score, _ = _snap_match
        _input_words = len(clean_text.split())
        _cmd_words = len(_snap_cmd.split())
        if abs(_input_words - _cmd_words) <= 1:
            # If fuzzy snap resolves to "go to sleep", handle it here rather
            # than dispatching to commandMethods (which has no sleep handler).
            if _snap_cmd == "go to sleep":
                print("Going to sleep. Say 'Hey Jarvis' to wake me.")
                awake_event.clear()
                if ui:
                    ui.set_sleeping()
                return
            print(f"Fuzzy snap: '{clean_text}' → '{_snap_cmd}' (score {_snap_score})")
            logging.info(f"Fuzzy-snap: '{_snap_cmd}' (score {_snap_score}, from: '{clean_text}')")
            _focus_premiere()
            commandMethods.Command(_snap_cmd).execute()
            if ui:
                ui.add_command_history(clean_text, f"~{_snap_cmd}")
            return

    # Before giving up, check if the spoken text matches an image in Effects/.
    # This lets any image dropped into ImageReference/Effects/ be called by
    # its filename without needing a hard-coded command entry.
    import image_matcher as _im
    if _im.has_effect_image(clean_text):
        print(f"[effects] '{clean_text}' matched Effects/ image — running effects search")
        logging.info(f"Effects-image: '{clean_text}'")
        _focus_premiere()          # effects search uses Premiere keyboard shortcuts
        commandMethods.Command(clean_text).execute()
        if ui:
            ui.add_command_history(clean_text, f"effect → {clean_text}")
        return

    # Same check for Click/ images — lets any image in ImageReference/Click/ be
    # triggered by just its filename, no "click" prefix needed.
    if _im.has_click_image(clean_text):
        print(f"[click] '{clean_text}' matched Click/ image — running click image")
        logging.info(f"Click-image: '{clean_text}'")
        pyautogui.hotkey("shift", "5")   # open Effect Controls before searching
        time.sleep(0.3)
        found, cx, cy = _im.click_image(clean_text, click_blue=True, subfolder=_im.CLICK_SUBDIR)
        if found:
            _held_mouse_buttons.add("left")
            if ui:
                ui.add_command_history(clean_text, f"clicking '{clean_text}' at ({cx},{cy})")
        else:
            if ui:
                ui.add_command_history(clean_text, f"'{clean_text}' not on screen")
        return

    # Image name fallback — route by folder: Effects/ → effects_search, Click/ → click_image
    _reload_image_names()

    def _best_match(name_set):
        best, score = None, 0
        for n in name_set:
            s = fuzz.ratio(clean_text, n)
            if s > score:
                score, best = s, n
        return best, score

    best_effect, effect_score = _best_match(_EFFECT_IMAGE_NAMES)
    if best_effect and effect_score >= 80:
        print(f"Effects image match: '{best_effect}' (score {effect_score})")
        logging.info(f"Effects image trigger: '{best_effect}' (from: '{clean_text}')")
        commandMethods.Command(best_effect)._effects_search(best_effect)
        if ui:
            ui.add_command_history(clean_text, f"effects search '{best_effect}'")
        return

    best_click, click_score = _best_match(_IMAGE_NAMES)
    if best_click and click_score >= 80:
        print(f"Click image match: '{best_click}' (score {click_score})")
        logging.info(f"Click image trigger: '{best_click}' (from: '{clean_text}')")
        found, cx, cy = _im.click_image(best_click, click_blue=True)
        if found:
            _held_mouse_buttons.add("left")
            if ui:
                ui.add_command_history(clean_text, f"clicking '{best_click}' at ({cx},{cy})")
        else:
            if ui:
                ui.add_command_history(clean_text, f"'{best_click}' not on screen")
        return

    # No match found
    print(f"No match for: '{clean_text}'")
    logging.info(f"No match: '{clean_text}'")
    if ui:
        ui.add_command_history(clean_text, "(no match)")


# --- Whisper initial_prompt builder ---
def _build_whisper_prompt() -> str:
    """Return a vocabulary-hint prompt for Whisper built from all known commands.

    Re-reads customCommands.json every call so changes made through the UI
    dialog are picked up without restarting.  The prompt is intentionally
    phrased as natural text so Whisper's language model biases toward these
    words rather than free-form speech.
    """
    words: set[str] = set()

    # Built-in command list
    for cmd in allowedCommands.ALLOWED_COMMANDS:
        for w in re.split(r"[\s_\-]+", cmd.lower()):
            if w:
                words.add(w)

    # Custom commands added via the UI
    try:
        with open("customCommands.json", encoding="utf-8") as _f:
            for keyword in json.load(_f):
                for w in re.split(r"[\s_\-]+", keyword.lower()):
                    if w:
                        words.add(w)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        pass

    # Format as a natural hint sentence Whisper handles well
    return "Commands: " + ", ".join(sorted(words)) + "."


# --- Vosk grammar + transcription ---
def _build_vosk_grammar() -> str:
    """Build the restricted Vosk grammar from all known command phrases."""
    phrases = list(allowedCommands.ALLOWED_COMMANDS)
    try:
        with open("customCommands.json", encoding="utf-8") as f:
            for kw in json.load(f):
                if kw not in phrases:
                    phrases.append(kw)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        pass
    # Add "press X" full phrases so Vosk has enough acoustic context to
    # distinguish e.g. "press b" from "fi blur dissolve impacts".
    # Bare letters are NOT added — the "press" prefix is the anchor.
    seen = set(phrases)
    press_targets = (
        list("abcdefghijklmnopqrstuvwxyz")
        + [str(d) for d in range(10)]
        + list(_KEY_ALIASES.keys())
        + list(_PRESS_PHONETIC.keys())
    )
    for target in press_targets:
        phrase = f"press {target}"
        if phrase not in seen:
            phrases.append(phrase)
            seen.add(phrase)

    # Add "click X" full phrases for all known image click targets so Vosk
    # can return the full phrase directly (same strategy as "press X").
    # Without these, "click position" makes Vosk output "[unk]", which falls
    # to Whisper where "click" is routinely misheard as "leak".
    _click_targets = set(_IMAGE_NAMES)
    # Include the common Effect-Controls blue-value targets even if images
    # haven't been added yet — users reference these by name frequently.
    _click_targets.update({
        "position", "scale", "rotation", "opacity",
        "position x", "position y",
        "anchor", "anchor point", "anchor x", "anchor y", "anchor point y",
    })
    for target in sorted(_click_targets):
        phrase = f"click {target}"
        if phrase not in seen:
            phrases.append(phrase)
            seen.add(phrase)

    phrases.append("[unk]")
    return json.dumps(phrases)


# Keywords whose commands should always be transcribed by Whisper, not Vosk.
# When Vosk hears one of these but can't complete the phrase (outputs
# "press [unk]"), we surface the bare keyword so audioListening can
# immediately re-run Whisper on the same already-captured audio buffer.
_WHISPER_RETRIGGER_PREFIXES: frozenset[str] = frozenset({"press"})


def _vosk_transcribe(audio_np: np.ndarray) -> str | None:
    """Match audio against the command grammar with Vosk.

    Returns the matched command string, or None if [unk] / model unavailable.
    Vosk physically cannot output a phrase outside the grammar, so this
    eliminates hallucinations like 'rust dissolve' for 'cross dissolve'.

    Special case: if the raw output is 'press [unk]', returns the bare
    keyword 'press' so the caller can re-run Whisper on the same audio.
    """
    if _vosk_model is None:
        return None
    rec = vosk.KaldiRecognizer(_vosk_model, SAMPLING_RATE, _build_vosk_grammar())
    audio_bytes = (np.clip(audio_np, -1.0, 1.0) * 32767).astype(np.int16).tobytes()
    rec.AcceptWaveform(audio_bytes)
    text = json.loads(rec.FinalResult()).get("text", "").strip()
    if not text or text == "[unk]":
        return None
    if "[unk]" not in text:
        return text
    # Partial match: text contains [unk] after a known keyword.
    # Salvage the prefix so the caller can route to Whisper on the same audio.
    # e.g. "press [unk]" → "press"
    prefix = text.replace("[unk]", "").strip()
    if prefix in _WHISPER_RETRIGGER_PREFIXES:
        return prefix
    return None


# Built-in hybrid trigger words — Vosk recognizes the keyword, then Whisper
# captures the freeform payload in a second pass.
_BUILTIN_HYBRID_TRIGGERS: frozenset[str] = frozenset({
    # Bare "marker" is intentionally excluded — it executes instantly (press M).
    # Only color-prefixed variants wait for a Whisper title payload.
    "red marker", "green marker", "blue marker",
    "violet marker", "orange marker", "yellow marker",
    "cyan marker", "white marker",
})


def _is_hybrid_command(text: str) -> bool:
    """Return True if this command accepts a freeform Whisper payload.

    Checks built-in marker triggers first, then customCommands.json entries
    that have "accepts_params": true.
    """
    if text.lower() in _BUILTIN_HYBRID_TRIGGERS:
        return True
    try:
        with open("customCommands.json", encoding="utf-8") as f:
            cmd = json.load(f).get(text.lower())
        return isinstance(cmd, dict) and bool(cmd.get("accepts_params"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return False


def _capture_whisper_payload(timeout: float = 6.0) -> str:
    """Record the next utterance after a Vosk trigger and transcribe it with Whisper.

    Drains any stale audio, waits up to timeout seconds for speech to start,
    then records until 1.5 s of silence and returns the Whisper transcript.
    """
    CHUNK = 1024
    SILENCE_THRESHOLD = 0.01
    SILENCE_FRAMES = int(1.5 * SAMPLING_RATE / CHUNK)
    MIN_SPEECH_CHUNKS = 3

    while not _audio_queue.empty():
        try:
            _audio_queue.get_nowait()
        except queue.Empty:
            break

    chunks = []
    silence_count = 0
    speaking = False
    deadline = time.time() + timeout

    while time.time() < deadline:
        try:
            chunk = _audio_queue.get(timeout=0.1)
        except queue.Empty:
            continue
        energy = float(np.sqrt(np.mean(chunk**2)))
        if energy > SILENCE_THRESHOLD:
            speaking = True
            silence_count = 0
            chunks.append(chunk)
        elif speaking:
            chunks.append(chunk)
            silence_count += 1
            if silence_count >= SILENCE_FRAMES:
                break

    if not chunks or len(chunks) < MIN_SPEECH_CHUNKS:
        return ""

    audio_np = np.concatenate(chunks).flatten()
    try:
        segments, _ = _whisper_model.transcribe(
            audio_np,
            beam_size=5,
            language="en",
            condition_on_previous_text=False,
            temperature=0.0,
            no_speech_threshold=0.8,
            max_new_tokens=96,
        )
        return " ".join(seg.text.strip() for seg in segments).strip()
    except Exception:
        return ""


def _whisper_transcribe_existing(audio_np: np.ndarray) -> str:
    """Transcribe already-captured audio with Whisper.

    Used when Vosk detects a keyword (e.g. 'press') but we need Whisper's
    accuracy for the full phrase — re-runs on the same recorded buffer
    instead of waiting for new audio like _capture_whisper_payload does.
    """
    try:
        segments, _ = _whisper_model.transcribe(
            audio_np,
            beam_size=5,
            language="en",
            condition_on_previous_text=False,
            temperature=0.0,
            no_speech_threshold=0.8,
            max_new_tokens=96,
        )
        return " ".join(seg.text.strip() for seg in segments).strip()
    except Exception:
        return ""


# --- Add custom command ---
def addCommand(trigger, keys):
    """
    trigger: string (e.g., "render")
    keys: list of strings (e.g., ["ctrl", "r"])
    """
    path = "customCommands.json"

    data = {}
    if os.path.exists(path):
        with open(path) as f:
            data = json.load(f)

    data[trigger.lower()] = [k.lower() for k in keys]

    with open(path, "w") as f:
        json.dump(data, f, indent=4)

    if trigger.lower() not in allowedCommands.ALLOWED_COMMANDS:
        allowedCommands.ALLOWED_COMMANDS.append(trigger.lower())

    for word in re.split(r"[\s_]+", trigger.lower()):
        if len(word) > 2:
            _COMMAND_VOCAB.add(word)

    print(f"Custom command added: '{trigger}' -> {keys} (Vosk grammar updated automatically)")


# --- Premiere focus check ---
def isPremiereFocused():
    app_name = "Adobe Premiere Pro"
    try:
        window_handle = win32gui.GetForegroundWindow()
        window_title = win32gui.GetWindowText(window_handle)
        return app_name.lower() in window_title.lower()
    except Exception:
        return False


# --- Audio callback ---
def _audio_callback(indata, frames, time_info, status):
    _audio_queue.put(indata.copy())


# --- Main audio listening loop ---
def audioListening():
    """Record utterances via energy-based VAD, then transcribe with Whisper."""
    global write_mode
    CHUNK = 1024
    SILENCE_THRESHOLD = 0.01
    SILENCE_FRAMES = int(1.0 * SAMPLING_RATE / CHUNK)
    MIN_SPEECH_CHUNKS = 3             # ignore bursts shorter than ~3 chunks (~0.2s)

    # ── PRE-ROLL BUFFER ── delete this block + the 3 marked lines below to remove
    # Keeps the last ~300 ms of audio in a rolling window so VAD onset clipping
    # doesn't eat the first phoneme of each command ("p-ress", "cl-ick", etc.).
    from collections import deque as _deque           # PRE-ROLL ①
    _PREROLL_CHUNKS = 5                               # PRE-ROLL ② (~300 ms @ 16 kHz/1024)
    _preroll = _deque(maxlen=_PREROLL_CHUNKS)         # PRE-ROLL ③
    # ── end PRE-ROLL setup ────────────────────────────────────────────────────

    print("Mic is LIVE. Speak now...")

    with sd.InputStream(
        samplerate=SAMPLING_RATE,
        channels=1,
        callback=_audio_callback,
        blocksize=CHUNK,
        dtype="float32",
    ):
        while awake_event.is_set():
            utterance_chunks = []
            silence_count = 0
            speaking = False
            _preroll.clear()                          # PRE-ROLL ④ — reset between utterances

            while awake_event.is_set():
                try:
                    chunk = _audio_queue.get(timeout=0.1)
                except queue.Empty:
                    continue

                _preroll.append(chunk)                # PRE-ROLL ⑤ — feed every frame
                energy = float(np.sqrt(np.mean(chunk**2)))

                if energy > SILENCE_THRESHOLD:
                    if not speaking:
                        # PRE-ROLL ⑥ — prepend onset window (includes current chunk)
                        utterance_chunks.extend(_preroll)
                    else:
                        utterance_chunks.append(chunk)
                    speaking = True
                    silence_count = 0
                elif speaking:
                    utterance_chunks.append(chunk)
                    silence_count += 1
                    if silence_count >= SILENCE_FRAMES:
                        break

            if not utterance_chunks or len(utterance_chunks) < MIN_SPEECH_CHUNKS:
                continue

            audio_np = np.concatenate(utterance_chunks).flatten()

            # --- Vosk fast-path: try the restricted grammar first ---
            if not write_mode:
                vosk_text = _vosk_transcribe(audio_np)
                if vosk_text:
                    # "click" and "leak" are acoustically similar, and "leak"
                    # exists in the vocabulary pool from effect names like
                    # "chroma leak" / "light leak". No valid command starts with
                    # a leading standalone "leak", so any Vosk output that begins
                    # with "leak" is a mishearing of "click".
                    # "chroma leak", "light leak" etc. are unaffected because
                    # they start with a different word.
                    if vosk_text == "leaks" or vosk_text.startswith("leaks "):
                        corrected = "click" + vosk_text[5:]
                        print(f"[Vosk] Corrected 'leaks' → 'click': '{vosk_text}' → '{corrected}'")
                        vosk_text = corrected
                    elif vosk_text == "leak" or vosk_text.startswith("leak "):
                        corrected = "click" + vosk_text[4:]
                        print(f"[Vosk] Corrected 'leak' → 'click': '{vosk_text}' → '{corrected}'")
                        vosk_text = corrected
                    if vosk_text in ("go to sleep", "sleep"):
                        print("Going to sleep. Say 'Hey Jarvis' to wake me.")
                        awake_event.clear()
                        if ui:
                            ui.set_sleeping()
                        return
                    if vosk_text == "writing mode":
                        write_mode = True
                        print("Write mode ON - everything you say will be typed.")
                        if ui:
                            ui.set_write_mode(True)
                            ui.add_command_history("writing mode", "write mode ON")
                        continue
                    if vosk_text == "press" or vosk_text.startswith("press "):
                        # Always use Whisper on the same already-captured audio
                        # for press commands. Vosk's constrained grammar force-
                        # fits key names and produces wrong results (e.g.
                        # "press 3" → "press five", "press 0" → "press z arrow").
                        print(f"[Press] Vosk detected 'press' — re-running Whisper on same audio...")
                        if ui:
                            ui.set_transcript("press…")
                        whisper_result = _whisper_transcribe_existing(audio_np)
                        if whisper_result:
                            whisper_clean = whisper_result.lower().strip().rstrip(".,!?")
                            print(f"[Press/Whisper] '{whisper_clean}'")
                            if ui:
                                ui.set_transcript(whisper_clean)
                            processVoiceInput(whisper_clean)
                        continue
                    # "search" — re-run Whisper on the same audio so a query
                    # spoken in the same breath is captured.
                    # e.g. "search wright chapel" → type that into the search bar.
                    # Fallback: "search" alone → CmdFind (Ctrl+F).
                    if vosk_text == "search" or vosk_text.startswith("search "):
                        print("[Search] Vosk detected 'search' — re-running Whisper for query...")
                        if ui:
                            ui.set_transcript("search…")
                        _sq_whisper = _whisper_transcribe_existing(audio_np)
                        if _sq_whisper:
                            _sq_clean = re.sub(r"[^\w\s]", "", _sq_whisper.lower()).strip().rstrip(".,!?")
                            print(f"[Search/Whisper] '{_sq_clean}'")
                            if ui:
                                ui.set_transcript(_sq_clean)
                            processVoiceInput(_sq_clean)
                        else:
                            processVoiceInput("search")
                        continue
                    # Bare color word — re-run Whisper on the same audio so a
                    # title said in the same breath is captured.
                    # e.g. "red chapter two" → labeled red marker "chapter two"
                    # Fallback: if Whisper finds nothing extra, executes bare
                    # color command (adds the colored marker with no title).
                    if vosk_text in _MARKER_COLOR_WORDS:
                        print(f"[Color marker] Vosk detected '{vosk_text}' — re-running Whisper for title...")
                        if ui:
                            ui.set_transcript(f"{vosk_text}…")
                        _cm_whisper = _whisper_transcribe_existing(audio_np)
                        if _cm_whisper:
                            _cm_clean = re.sub(r"[^\w\s]", "", _cm_whisper.lower()).strip().rstrip(".,!?")
                            print(f"[Color marker/Whisper] '{_cm_clean}'")
                            if ui:
                                ui.set_transcript(_cm_clean)
                            processVoiceInput(_cm_clean)
                        else:
                            processVoiceInput(vosk_text)
                        continue
                    if _is_hybrid_command(vosk_text):
                        print(f"[Vosk trigger] '{vosk_text}' — listening for payload...")
                        logging.info(f"Vosk hybrid trigger: '{vosk_text}'")
                        if ui:
                            ui.set_transcript(f"{vosk_text}…")
                        payload = _capture_whisper_payload()
                        if payload:
                            combined = f"{vosk_text} {payload}"
                            print(f"[Hybrid] '{combined}'")
                            logging.info(f"Hybrid command: '{combined}'")
                            if ui:
                                ui.set_transcript(combined)
                            processVoiceInput(combined)
                        else:
                            # No payload spoken — execute the trigger alone
                            processVoiceInput(vosk_text)
                    else:
                        print(f"[Vosk] '{vosk_text}'")
                        logging.info(f"Vosk command: '{vosk_text}'")
                        if ui:
                            ui.set_transcript(vosk_text)
                        processVoiceInput(vosk_text)
                    continue  # skip Whisper entirely

            try:
                _prompt = None if write_mode else _build_whisper_prompt()

                segments, _ = _whisper_model.transcribe(
                    audio_np,
                    beam_size=5,
                    language="en",
                    vad_filter=True,
                    vad_parameters=dict(
                        threshold=0.4,
                        min_speech_duration_ms=80,
                        min_silence_duration_ms=600,
                        speech_pad_ms=300,
                    ),
                    condition_on_previous_text=False,
                    temperature=0.0,
                    no_speech_threshold=0.8,
                    compression_ratio_threshold=1.8,
                    word_timestamps=False,
                    max_new_tokens=96,
                    initial_prompt=_prompt,
                )
                # Track the previous segment so Whisper's VAD doesn't fire the
                # same command twice — short standalone words (e.g. "backspace")
                # are often emitted as two identical padded segments in one pass.
                _last_seg_clean: str | None = None
                for segment in segments:
                    text = segment.text.strip()
                    if not text:
                        continue

                    if segment.avg_logprob < -1.0:
                        print(f"[VAD] Dropped low-confidence segment (logprob={segment.avg_logprob:.2f}): '{text[:50]}'")
                        continue

                    _HALLUCINATIONS = {
                        "thank you", "thank you very much", "thanks for watching",
                        "thanks for watching!", "thank you for watching",
                        "thank you.", "thank you very much.", "thanks.",
                        "you", "the", ".", ",", "...", "okay", "ok",
                    }
                    _text_stripped = text.lower().strip().rstrip(".!?,")
                    if _text_stripped in _HALLUCINATIONS or text.strip() in _HALLUCINATIONS:
                        print(f"[VAD] Dropped hallucination: '{text}'")
                        continue

                    _clean_words = re.sub(r"[^\w\s]", "", text.lower()).split()

                    if len(_clean_words) >= 4 and len(set(_clean_words)) <= 2:
                        print(f"[VAD] Dropped repetitive hallucination: '{text[:60]}...'")
                        continue

                    if len(_clean_words) >= 6:
                        _bigrams = [
                            (_clean_words[i], _clean_words[i + 1])
                            for i in range(len(_clean_words) - 1)
                        ]
                        _bigram_counts = {}
                        for _bg in _bigrams:
                            _bigram_counts[_bg] = _bigram_counts.get(_bg, 0) + 1
                        if _bigram_counts and max(_bigram_counts.values()) >= 3:
                            print(f"[VAD] Dropped bigram-repetitive hallucination: '{text[:60]}...'")
                            continue

                    if not write_mode and len(_clean_words) > 30:
                        _skip_gate = False
                        try:
                            with open("customCommands.json", encoding="utf-8") as _gf:
                                _gd = json.load(_gf)
                            _tl = text.lower()
                            for _gkw, _gc in _gd.items():
                                if (isinstance(_gc, dict) and _gc.get("accepts_params")
                                        and _tl.startswith(_gkw)):
                                    _skip_gate = True
                                    break
                        except Exception:
                            pass
                        if not _skip_gate:
                            print(f"[VAD] Dropped long input ({len(_clean_words)} words) in command mode: '{text[:60]}...'")
                            continue

                    # Drop a segment identical to the one just processed in this
                    # same transcription — guards against Whisper emitting a short
                    # command word (e.g. "backspace") as two padded segments,
                    # which would otherwise dispatch the keystroke twice.
                    _seg_clean = re.sub(r"[^\w\s]", "", text.lower()).strip()
                    if _seg_clean and _seg_clean == _last_seg_clean:
                        print(f"[VAD] Dropped duplicate segment: '{text}'")
                        continue
                    _last_seg_clean = _seg_clean

                    # Correct common Whisper mishearings before any further
                    # processing.  "leak" / "leek" is Whisper's near-universal
                    # substitute for "click" when there's no acoustic context
                    # from Vosk — fix it here so commands like "leak position"
                    # are correctly dispatched as "click position".
                    text = re.sub(r'\bleak\b', 'click', text, flags=re.IGNORECASE)
                    text = re.sub(r'\bleek\b', 'click', text, flags=re.IGNORECASE)

                    # Sleep trigger
                    _text_lower = text.lower()
                    _sleep_stripped = re.sub(r"[^\w\s]", "", _text_lower).strip()
                    if ("go to sleep" in _text_lower or "good to sleep" in _text_lower
                            or "to sleep" in _text_lower or "go sleep" in _text_lower
                            or _sleep_stripped == "sleep"):
                        print("Going to sleep. Say 'Hey Jarvis' to wake me.")
                        awake_event.clear()
                        if ui:
                            ui.set_sleeping()
                        return

                    print(f"You said: '{text}'")
                    if ui:
                        ui.set_transcript(text)

                    # --- Write mode handling ---
                    text_lower = text.lower().strip()
                    text_clean = re.sub(r"[^\w\s]", "", text_lower)

                    if text_clean == "writing mode":
                        write_mode = True
                        print("Write mode ON - everything you say will be typed.")
                        if ui:
                            ui.set_write_mode(True)
                            ui.add_command_history(text, "write mode ON")
                        continue

                    if write_mode:
                        if "stop writing" in text_clean:
                            write_mode = False
                            print("Write mode OFF - back to command mode.")
                            if ui:
                                ui.set_write_mode(False)
                                ui.add_command_history(text, "write mode OFF")
                            continue
                        # Type out via clipboard paste
                        print(f"Typing: '{text}'")
                        import pyperclip
                        old_clip = pyperclip.paste()
                        pyperclip.copy(text)
                        pyautogui.hotkey("ctrl", "v")
                        time.sleep(0.1)
                        pyperclip.copy(old_clip)
                        if ui:
                            ui.add_command_history(text, "(typed)")
                        continue

                    processVoiceInput(text)
            except Exception as e:
                print(f"Transcription error: {e}")


def _voice_loop():
    while True:
        if not awake_event.is_set():
            if ui:
                ui.set_sleeping()
            wakeListener()
            awake_event.set()
        else:
            print("\n--- Listening... (Press Ctrl+C to stop) ---\n")
            audioListening()


def main():
    global ui
    ui = VoiceCutterUI(wake_word=WakeUpWord)
    ui.run(_voice_loop)


if __name__ == "__main__":
    main()
