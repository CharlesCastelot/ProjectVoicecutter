import json
import os
import subprocess
import sys
import ctypes
import ctypes.wintypes

from pywinauto import Application
import pyautogui
import keyboard
import win32gui
import win32process
import time

# GUITHREADINFO — lets us find which child window has focus inside Premiere's thread
class _GUITHREADINFO(ctypes.Structure):
    _fields_ = [
        ("cbSize",       ctypes.c_uint),
        ("flags",        ctypes.c_uint),
        ("hwndActive",   ctypes.wintypes.HWND),
        ("hwndFocus",    ctypes.wintypes.HWND),
        ("hwndCapture",  ctypes.wintypes.HWND),
        ("hwndMenuOwner",ctypes.wintypes.HWND),
        ("hwndMoveSize", ctypes.wintypes.HWND),
        ("hwndCaret",    ctypes.wintypes.HWND),
        ("rcCaret",      ctypes.wintypes.RECT),
    ]

class Command:
    # We connect to Premiere once at the class level to avoid reconnecting every time
    try:
        app = Application(backend="uia").connect(path="Adobe Premiere Pro.exe")
        main_window = app.window(title_re=".*Adobe Premiere Pro.*")
    except Exception as e:
        print(f"Could not connect to Premiere Pro: {e}")
        main_window = None

    def find_and_click_uia(self, label):
        """Searches the Windows Accessibility Tree for a specific label."""
        if not self.main_window:
            return False

        print(f"Searching Accessibility Tree for: {label}...")
        try:
            # Look for elements where the 'Name' matches your label
            element = self.main_window.child_window(title_re=f".*{label}.*", control_type="ListItem", found_index=0)

            # If not found as a ListItem (Tabs), try a broader search
            if not element.exists():
                element = self.main_window.child_window(title_re=f".*{label}.*", found_index=0)

            if element.exists():
                rect = element.rectangle()
                center_x = (rect.left + rect.right) // 2
                center_y = (rect.top + rect.bottom) // 2

                print(f"UIA Found '{label}' at {center_x, center_y}. Clicking...")
                pyautogui.click(center_x, center_y)
                return True
        except Exception as e:
            print(f"UIA Search failed for {label}: {e}")

        return False

    def __init__(self, inputWord):
        self.inputWord = inputWord.lower().strip()
        # Mapping strings to the actual method references
        self.commands = {
            "control down":  self.CmdControlDown,
            "control up":    self.CmdControlUp,
            "shift down":    self.CmdShiftDown,
            "shift up":      self.CmdShiftUp,
            "alt down":      self.CmdAltDown,
            "alt up":        self.CmdAltUp,
            "heat": self.CmdTilde,
            "screenshot": self.CmdScreenshot,
            "new project": self.CmdNewProject,
            "new sequence": self.CmdNewSequence,
            "open project": self.CmdOpenProject,
            "close": self.CmdClose,
            "close project": self.CmdCloseProject,
            "save": self.CmdSave,
            "save as": self.CmdSaveAs,
            "save a copy": self.CmdSaveCopy,
            "import from media browser": self.CmdImportMediaBrowser,
            "import": self.CmdImport,
            "export": self.CmdExport,
            "encoder": self.CmdMediaEncoder,
            "properties": self.CmdProperties,
            "exit": self.CmdExit,
            "undo": self.CmdUndo,
            "redo": self.CmdRedo,
            "cut": self.CmdCut,
            "copy": self.CmdCopy,
            "copy comp": self.CmdCopyComp,
            "paste": self.CmdPaste,
            "attributes": self.CmdPasteAttrs,
            "remove attributes": self.CmdRemoveAttributes,
            "clear": self.CmdClear,
            "ripple": self.CmdRippleDelete,
            "duplicate": self.CmdDuplicate,
            "select all": self.CmdSelectAll,
            "deselect all": self.CmdDeselectAll,
            "search": self.CmdFind,
            "original": self.CmdEditOriginal,
            "shortcuts": self.CmdShortcuts,
            "production": self.CmdSwitchProduction,
            "play": self.CmdPlay,
            "pause": self.CmdPause,
            "transition": self.CmdAddTransition,
            # --- Editing ---
            "overwrite": self.CmdOverwrite,
            "insert": self.CmdInsert,
            "in": self.CmdMarkIn,
            "out": self.CmdMarkOut,
            "nest": self.CmdNest,
            "make subclip": self.CmdMakeSubclip,
            "subclip": self.CmdMakeSubclip,
            "add edit": self.CmdAddEdit,
            "add edit all": self.CmdAddEditAll,
            "rectangle": self.CmdRectangle,
            "extend": self.CmdExtend,
            "marker": self.CmdMarker,
            # --- Effects search ---
            "blur": self.CmdEffectsBlur,
            "cross dissolve": self.CmdEffectsCrossDissolve,
            "lumetri color": self.CmdEffectsLumetri,
            "noise": self.CmdEffectsNoise,
            "warp stabilizer": self.CmdEffectsWarpStabilizer,
            "wave warp": self.CmdEffectsWaveWarp,
            "cross": self.CmdEffectsCross,
            # --- Labels ---
            "no label": self.CmdLabelNone,
            "label violet": self.CmdLabelViolet,
            "label iris": self.CmdLabelIris,
            "label caribbean": self.CmdLabelCaribbean,
            "label lavender": self.CmdLabelLavender,
            "label cerulean": self.CmdLabelCerulean,
            "label forest": self.CmdLabelForest,
            "label rose": self.CmdLabelRose,
            "label mango": self.CmdLabelMango,
            "label purple": self.CmdLabelPurple,
            "label blue": self.CmdLabelBlue,
            "label teal": self.CmdLabelTeal,
            "label magenta": self.CmdLabelMagenta,
            "label tan":     self.CmdLabelTan,
            "label green":   self.CmdLabelGreen,
            "label yellow":  self.CmdLabelYellow,
            "label brown":   self.CmdLabelBrown,
            # --- Markers ---
            "green": self.CmdMarkerGreen,
            "next marker": self.CmdNextMarker,
            "previous marker": self.CmdPreviousMarker,
            "red": self.CmdMarkerRed,
            "violet": self.CmdMarkerViolet,
            "cyan": self.CmdMarkerCyan,
            "yellow": self.CmdMarkerYellow,
            "orange": self.CmdMarkerOrange,
            "marker blue": self.CmdMarkerBlue,
            "marker white": self.CmdMarkerWhite,
            "clear marker": self.CmdClearMarker,
            "clear all markers": self.CmdClearAllMarkers,
            "edit marker": self.CmdEditMarker,
            # --- Editing (new) ---
            "speed": self.CmdSpeed,
            "clip speed": self.CmdSpeed,
            "subclip": self.CmdSubclip,
            "make subclip": self.CmdSubclip,
            "subsequence": self.CmdSubsequence,
            "group": self.CmdGroup,
            "ungroup": self.CmdUngroup,
            "lift": self.CmdLift,
            "extract": self.CmdExtract,
            "match": self.CmdMatchFrame,
            "reverse match frame": self.CmdReverseMatchFrame,
            "select clip": self.CmdSelectClip,
            "extend edit": self.CmdExtendEdit,
            "ripple trim next": self.CmdRippleTrimNext,
            "trim next": self.CmdRippleTrimNext,
            "ripple trim previous": self.CmdRippleTrimPrevious,
            "trim previous": self.CmdRippleTrimPrevious,
            "export frame": self.CmdExportFrame,
            "apply audio transition": self.CmdApplyAudioTransition,
            "apply both transitions": self.CmdApplyBothTransitions,
            "enable": self.CmdEnableClip,
            "delete effects": self.CmdDeleteEffects,
            "fit frame": self.CmdFitToFrame,
            "fill frame": self.CmdFillFrame,
            "scale frame": self.CmdScaleToFrame,
            "clear in": self.CmdClearIn,
            "clear out": self.CmdClearOut,
            "paste insert": self.CmdPasteInsert,
            "volume up": self.CmdVolumeUp,
            "volume down": self.CmdVolumeDown,
            "boost": self.CmdBigVolumeUp,
            "lower": self.CmdBigVolumeDown,
            "next gap": self.CmdNextGap,
            "previous gap": self.CmdPreviousGap,
            "zoom to fit": self.CmdZoomToFit,
            "zoom to frame": self.CmdZoomToFrame,
            "zoom in": self.CmdZoomIn,
            "zoom out": self.CmdZoomOut,
            "next screen": self.CmdNextScreen,
            "previous screen": self.CmdPreviousScreen,
            "maximize": self.CmdMaximize,
            "nested": self.CmdRevealNested,
            # --- Panels / Windows ---
            "bin": self.CmdNewBin,
            "bin from selection": self.CmdBinFromSelection,
            "new smart bin": self.CmdNewSmartBin,
            "quick export": self.CmdQuickExport,
            "browser": self.CmdMediaBrowser,
            "audio clip mixer": self.CmdAudioClipMixer,
            "open text panel": self.CmdOpenTextPanel,
            "captions panel": self.CmdOpenTextPanel,
            # --- Panels / Tools ---
            "bin window": self.CmdBinWindow,
            "source": self.CmdSourceMonitor,
            "timeline": self.CmdTimeline,
            "preview window": self.CmdPreviewWindow,
            "controls": self.CmdEffectControls,
            "audio mixer": self.CmdAudioMixer,
            "effects": self.CmdEffectsPanel,
            "trim": self.CmdTrim,
            "trim edit": self.CmdTrimEdit,
            "rip": self.CmdRip,
            "pen": self.CmdPenTool,
            "selection": self.CmdSelectionTool,
            "text": self.CmdText,
            "slip": self.CmdSlipTool,
            "open in source monitor": self.CmdOpenInSourceMonitor,
            "clear in and out": self.CmdClearInAndOut,
            "roll": self.CmdRoll,
            "unlink selection": self.CmdUnlinkSelection,
            "link selection": self.CmdLinkSelection,
            "reveal in project": self.CmdRevealInProject,
            "snap": self.CmdToggleSnap,
            "rename": self.CmdRename,
            "multicam": self.CmdMulticamSequence,
            "create multicam": self.CmdMulticamSequence,
            "sync": self.CmdSync,
            "sync window": self.CmdSyncWindow,
            "enable multicam": self.CmdEnableMulticam,
            "link": self.CmdLink,
            # --- Tools ---
            "stretch": self.CmdRateStretch,
            "razor": self.CmdRazor,
            "razor all": self.CmdRazorAll,
            "slide": self.CmdSlide,
            "hand": self.CmdHand,
            "zoom": self.CmdZoomTool,
            "track select": self.CmdTrackSelect,
            # --- Track targeting ---
            "target video one":   self.CmdTargetVideo1,
            "target video two":   self.CmdTargetVideo2,
            "target video three": self.CmdTargetVideo3,
            "target video four":  self.CmdTargetVideo4,
            "target video five":  self.CmdTargetVideo5,
            "target audio one":   self.CmdTargetAudio1,
            "target audio two":   self.CmdTargetAudio2,
            "target audio three": self.CmdTargetAudio3,
            "target audio four":  self.CmdTargetAudio4,
            "target audio five":  self.CmdTargetAudio5,
            "target all video":   self.CmdTargetAllVideo,
            "target all audio":   self.CmdTargetAllAudio,
            "source all video":   self.CmdSourceAllVideo,
            "source all audio":   self.CmdSourceAllAudio,
            # --- Transport / Playback ---
            "reverse": self.CmdReverse,
            "slow reverse": self.CmdSlowReverse,
            "slow play": self.CmdSlowPlay,
            "play edit": self.CmdPlayEdit,
            "play in to out": self.CmdPlayInToOut,
            "play to out": self.CmdPlayToOut,
            "toggle play": self.CmdTogglePlay,
            "play around": self.CmdPlayAround,
            "step back": self.CmdStepBack,
            "step forward": self.CmdStepForward,
            "step back five": self.CmdStepBack5,
            "step forward five": self.CmdStepForward5,
            "go to sequence start": self.CmdGoToSequenceStart,
            "go to sequence end": self.CmdGoToSequenceEnd,
            "go to clip start": self.CmdGoToClipStart,
            "go to clip end": self.CmdGoToClipEnd,
            # --- Sequence editing (extended) ---
            "extend next": self.CmdExtendNext,
            "extend previous": self.CmdExtendPrevious,
            "join through edits": self.CmdJoinThroughEdits,
            "gaps": self.CmdCloseGaps,
            "add track": self.CmdAddTrack,
            "add video track": self.CmdAddVideoTrack,
            "rename audio track": self.CmdRenameAudioTrack,
            "rename video track": self.CmdRenameVideoTrack,
            "delete tracks": self.CmdDeleteTracks,
            "toggle trim type": self.CmdToggleTrimType,
            "selection follows playhead": self.CmdSelectionFollowsPlayhead,
            "flatten multicam": self.CmdFlattenMulticam,
            "toggle multicam": self.CmdToggleMulticam,
            "multicam audio": self.CmdMulticamAudioFollowsVideo,
            "add audio keyframe": self.CmdAddAudioKeyframe,
            "add video keyframe": self.CmdAddVideoKeyframe,
            "next keyframe": self.CmdNextKeyframe,
            "previous keyframe": self.CmdPreviousKeyframe,
            "ease in": self.CmdEaseIn,
            "ease out": self.CmdEaseOut,
            "linear keyframe": self.CmdLinearKeyframe,
            "hold keyframe": self.CmdHoldKeyframe,
            "increase audio keyframe": self.CmdIncreaseAudioKeyframe,
            "decrease audio keyframe": self.CmdDecreaseAudioKeyframe,
            "increase video keyframe": self.CmdIncreaseVideoKeyframe,
            "decrease video keyframe": self.CmdDecreaseVideoKeyframe,
            "trim in to playhead": self.CmdTrimInToPlayhead,
            "trim out to playhead": self.CmdTrimOutToPlayhead,
            # --- Markers (extended) ---
            "go to in": self.CmdGoToIn,
            "go to out": self.CmdGoToOut,
            "mark clip": self.CmdMarkClip,
            "range marker": self.CmdRangeMarker,
            "chapter marker": self.CmdChapterMarker,
            "show markers": self.CmdShowMarkers,
            # --- Audio ---
            "gain": self.CmdAudioGainDialog,
            "mono": self.CmdBreakOutMono,
            "speech": self.CmdEnhanceSpeech,
            "nudge volume down": self.CmdNudgeVolumeDown,
            "nudge volume up": self.CmdNudgeVolumeUp,
            "nudge volume down three": self.CmdNudgeVolumeDown3,
            "nudge volume up three": self.CmdNudgeVolumeUp3,
            "mappings": self.CmdChannelMappings,
            # --- Clip options ---
            "replace from bin": self.CmdReplaceFromBin,
            "replace from source": self.CmdReplaceFromSource,
            "replace": self.CmdReplaceFotage,
            "blend": self.CmdFrameBlend,
            "frame sampling": self.CmdFrameSampling,
            "optical flow": self.CmdOpticalFlow,
            "render": self.CmdRender,
            "render replace": self.CmdRenderReplace,
            "restore": self.CmdRestoreUnrendered,
            "freeze": self.CmdAddFrameHold,
            "frame hold options": self.CmdFrameHoldOptions,
            "proxies": self.CmdCreateProxies,
            "peaks": self.CmdGeneratePeaks,
            "interpret": self.CmdInterpretFotage,
            "synchronize": self.CmdSynchronizeClips,
            # --- Timeline display ---
            "expand": self.CmdExpandTracks,
            "minimize": self.CmdMinimizeTracks,
            "increase track height": self.CmdIncreaseVideoTrackHeight,
            "decrease track height": self.CmdDecreaseVideoTrackHeight,
            "increase audio height": self.CmdIncreaseAudioTrackHeight,
            "decrease audio height": self.CmdDecreaseAudioTrackHeight,
            "work area in": self.CmdWorkAreaIn,
            "work area out": self.CmdWorkAreaOut,
            "scrubbing": self.CmdToggleAudioScrubbing,
            "mutes": self.CmdToggleTrackMutes,
            "solos": self.CmdToggleTrackSolos,
            "sequence label color": self.CmdSequenceLabelColor,
            "units": self.CmdAudioUnits,
            # --- Track height presets (preset 1 = ctrl+F8 … preset 10 = ctrl+F17) ---
            "track height one":   self.CmdTrackHeight1,
            "track height two":   self.CmdTrackHeight2,
            "track height three": self.CmdTrackHeight3,
            "track height four":  self.CmdTrackHeight4,
            "track height five":  self.CmdTrackHeight5,
            "track height six":   self.CmdTrackHeight6,
            "track height seven": self.CmdTrackHeight7,
            "track height eight": self.CmdTrackHeight8,
            "track height nine":  self.CmdTrackHeight9,
            "track height ten":   self.CmdTrackHeight10,
            # --- Graphics ---
            "add text": self.CmdAddText,
            "ellipse": self.CmdAddEllipse,
            "enter text edit": self.CmdEnterTextEdit,
            "layer up": self.CmdLayerUp,
            "layer down": self.CmdLayerDown,
            "layer to top": self.CmdLayerToTop,
            "layer to bottom": self.CmdLayerToBottom,
            "center": self.CmdAlignCenter,
            # --- Captions ---
            "caption": self.CmdAddCaption,
            "split": self.CmdSplitCaption,
            "merge": self.CmdMergeCaptions,
            # --- File / Project ---
            "close sequence": self.CmdCloseSequence,
            "close tab": self.CmdCloseSequence,
            "color properties": self.CmdColorProperties,
            "refresh": self.CmdRefreshProject,
            "poster": self.CmdSetPosterFrame,
            # --- Monitor ---
            "fullscreen": self.CmdFullscreen,
            "full screen": self.CmdFullscreen,
            "maximize focused": self.CmdMaximizeFocused,
            "guides": self.CmdGuides,
            "overlays": self.CmdOverlays,
            "program zoom fit": self.CmdProgramZoomFit,
            "program zoom 100": self.CmdProgramZoom100,
            "source zoom fit": self.CmdSourceZoomFit,
            "source zoom 100": self.CmdSourceZoom100,
            # --- Workspaces ---
            "workspace one":    self.CmdWorkspace1,
            "workspace two":    self.CmdWorkspace2,
            "workspace three":  self.CmdWorkspace3,
            "workspace four":   self.CmdWorkspace4,
            "workspace five":   self.CmdWorkspace5,
            "workspace six":    self.CmdWorkspace6,
            "workspace seven":  self.CmdWorkspace7,
            "workspace eight":  self.CmdWorkspace8,
            "workspace nine":   self.CmdWorkspace9,
            "revert workspace": self.CmdRevertWorkspace,
            # --- Panels navigation ---
            "next panel": self.CmdNextPanel,
            "previous panel": self.CmdPreviousPanel,
            # --- Effects panel ---
            "find effects": self.CmdFindEffects,
            "save effect preset": self.CmdSaveEffectPreset,
            "delete all effects": self.CmdDeleteAllEffects,
            "recalibrate": self.CmdRecalibrate,
            "recalibrate search": self.CmdRecalibrateSearch,
            # --- Pan ---
            "pan center": self.CmdPanCenter,
            "pan left": self.CmdPanLeft,
            "pan right": self.CmdPanRight,
            # --- Multicam cameras ---
            "camera one":   self.CmdCamera1,
            "camera two":   self.CmdCamera2,
            "camera three": self.CmdCamera3,
            "camera four":  self.CmdCamera4,
            "camera five":  self.CmdCamera5,
            "camera six":   self.CmdCamera6,
            "camera seven": self.CmdCamera7,
            "camera eight": self.CmdCamera8,
            "camera nine":  self.CmdCamera9,
            # ── tvh commands ───────────────────────────────────────────────────
            "ease in out":       self.CmdEaseInOut,
            "ease keyframes":    self.CmdEaseInOut,
            "ease in and out":   self.CmdEaseInOut,
            "close titler":      self.CmdCloseTitler,
            "lock":              self.CmdLockTracks,
            "crop":              self.CmdCropHandles,
            "transform":         self.CmdTransformHandles,
            "mono left":         self.CmdMonoLeft,
            "mono right":        self.CmdMonoRight,
            # ── Effect Controls value clicks (opens panel first) ────────────────
            "position x":        self.CmdEcPositionX,
            "position y":        self.CmdEcPositionY,
            "scale":             self.CmdEcScale,
            "scale width":       self.CmdEcScaleWidth,
            "uniform scale":     self.CmdEcUniformScale,
            "rotation":          self.CmdEcRotation,
            "anchor x":          self.CmdEcAnchorX,
            "anchor y":          self.CmdEcAnchorY,
            "anti flicker filter": self.CmdEcAntiFlicker,
            "crop left":         self.CmdEcCropLeft,
            "crop top":          self.CmdEcCropTop,
            "crop right":        self.CmdEcCropRight,
            "crop bottom":       self.CmdEcCropBottom,
            "opacity":           self.CmdEcOpacity,
            "blend mode":        self.CmdEcBlendMode,
            "time remapping":    self.CmdEcTimeRemapping,
        }

    def execute(self):
        """Look up the method, then try effect images, then custom commands."""
        method = self.commands.get(self.inputWord)

        if method:
            method()
            return

        # Auto-route: any image in ImageReference/Effects/ behaves like a
        # hard-coded CmdEffects* method — no "click" prefix needed.
        try:
            import image_matcher
            if image_matcher.has_effect_image(self.inputWord):
                self._effects_search(self.inputWord)
                return
        except Exception as e:
            print(f"[execute] Effect-image lookup failed: {e}")

        self._try_custom_command()

    def _try_custom_command(self):
        """Try to execute a custom command from customCommands.json."""
        path = "customCommands.json"
        if not os.path.exists(path):
            print(f"Command '{self.inputWord}' not recognized.")
            return

        with open(path) as f:
            data = json.load(f)

        cmd = data.get(self.inputWord)
        if not cmd:
            print(f"Command '{self.inputWord}' not recognized.")
            return

        if isinstance(cmd, dict):
            if cmd.get("type") == "script":
                self._run_script(cmd["path"])
            elif cmd.get("type") == "hotkey":
                self._Success(*cmd["keys"])
            elif cmd.get("type") == "effect":
                # Keyword (inputWord) is typed into Premiere's search box.
                # The stored path is used directly for template matching so the
                # keyword takes priority over the image filename.
                self._effects_search(self.inputWord, image_path=cmd.get("path"))
            elif cmd.get("type") == "image":
                self._run_image_click(cmd["path"])
            elif cmd.get("type") == "image_effect":
                self._run_image_effect(cmd["path"])
        elif isinstance(cmd, list):
            # Backward compat: old format was just a list of keys
            self._Success(*cmd)

    def _run_script(self, script_path):
        """Execute a Python script in a subprocess."""
        print(f"Running script: {script_path}")
        try:
            subprocess.run([sys.executable, script_path], check=True)
        except subprocess.CalledProcessError as e:
            print(f"Script failed with exit code {e.returncode}")
        except FileNotFoundError:
            print(f"Script not found: {script_path}")

    def _run_script_with_params(self, script_path: str, params: str) -> None:
        """Execute a Python script, passing params as the first CLI argument."""
        print(f"Running script: {script_path!r}  params={params!r}")
        try:
            subprocess.run([sys.executable, script_path, params], check=True)
        except subprocess.CalledProcessError as e:
            print(f"Script failed with exit code {e.returncode}")
        except FileNotFoundError:
            print(f"Script not found: {script_path}")

    def _run_image_click(self, image_path: str):
        """Find an image on screen and hold left-click on its blue value field."""
        import image_matcher
        from pathlib import Path
        p = Path(image_path)
        name = p.stem.replace("_", " ").lower()

        # Use find_on_screen_from_path (direct path, scale-cached) when the
        # file exists; fall back to name-based lookup otherwise.
        if p.exists():
            result = image_matcher.find_on_screen_from_path(str(p))
        else:
            result = image_matcher.find_on_screen(name)

        if result is None:
            print(f"[image] '{name}' not found on screen.")
            return

        x, y, w, h = result
        screen_bgr = image_matcher._grab_screenshot()
        blue = image_matcher._find_blue_in_row(
            screen_bgr, y, h, x + w, image_matcher.BLUE_SCAN_WIDTH
        )
        cx, cy = blue if blue else (x + w // 2, y + h // 2)
        import pyautogui
        pyautogui.moveTo(cx, cy)
        pyautogui.mouseDown(button="left")
        print(f"[image] Clicked '{name}' at ({cx}, {cy})")

    def _run_image_effect(self, image_path: str):
        """Run _effects_search using the stem of the given image path as the effect name."""
        from pathlib import Path
        name = Path(image_path).stem.replace("_", " ").lower()
        self._effects_search(name)

    def _Success(self, *keys):
        """Helper to print status and fire the hotkey"""
        print(f"Command '{self.inputWord}' recognized!")
        pyautogui.hotkey(*keys)

    # --- Modifier key hold/release ---
    def CmdControlDown(self):
        print(f"Command '{self.inputWord}' recognized!")
        pyautogui.keyDown('ctrl')

    def CmdControlUp(self):
        print(f"Command '{self.inputWord}' recognized!")
        pyautogui.keyUp('ctrl')

    def CmdShiftDown(self):
        print(f"Command '{self.inputWord}' recognized!")
        pyautogui.keyDown('shift')

    def CmdShiftUp(self):
        print(f"Command '{self.inputWord}' recognized!")
        pyautogui.keyUp('shift')

    def CmdAltDown(self):
        print(f"Command '{self.inputWord}' recognized!")
        pyautogui.keyDown('alt')

    def CmdAltUp(self):
        print(f"Command '{self.inputWord}' recognized!")
        pyautogui.keyUp('alt')

    # --- Integrated Specialized Methods ---
    def CmdSwitchProduction(self, name="Production"):
        if self.main_window:
            self.main_window.type_keys('%w', with_spaces=True)
            time.sleep(0.2)
            self.main_window.type_keys('w' + name[0] + name[0] + '{ENTER}', with_spaces=True)
            print(f"Sent command to switch to {name}")

    # --- File Menu Methods ---
    def CmdTilde(self): self._Success("shift", "`")
    def CmdScreenshot(self): self._Success("win", "shift", "s")
    def CmdNewProject(self): self._Success("ctrl", "alt", "n")
    def CmdNewSequence(self): self._Success("ctrl", "n")
    def CmdOpenProject(self): self._Success("ctrl", "o")
    def CmdClose(self): self._Success("ctrl", "w")
    def CmdCloseProject(self): self._Success("ctrl", "shift", "w")
    def CmdSave(self): self._Success("ctrl", "s")
    def CmdSaveAs(self): self._Success("ctrl", "shift", "s")
    def CmdSaveCopy(self): self._Success("ctrl", "alt", "s")
    def CmdImportMediaBrowser(self): self._Success("ctrl", "alt", "i")
    def CmdImport(self): self._Success("ctrl", "i")
    def CmdExport(self): self._Success("ctrl", "m")
    def CmdMediaEncoder(self): self._Success("alt", "shift", "m")
    def CmdProperties(self): self._Success("ctrl", "shift", "h")
    def CmdExit(self): self._Success("ctrl", "q")

    # --- Edit Menu Methods ---
    def CmdUndo(self): self._Success("ctrl", "z")
    def CmdRedo(self): self._Success("ctrl", "shift", "z")
    def CmdCut(self): self._Success("ctrl", "k")   # Add Edit (razor at playhead) — matches Dragon "cut"
    def CmdCopy(self): self._Success("ctrl", "c")

    def CmdCopyComp(self):
        print(f"Command '{self.inputWord}' recognized!")
        pyautogui.hotkey("ctrl", "c")
        time.sleep(0.2)
        pyautogui.hotkey("ctrl", "n")
        time.sleep(0.5)
        pyautogui.press("enter")
        time.sleep(0.3)
        pyautogui.hotkey("ctrl", "v")
    def CmdPaste(self): self._Success("ctrl", "v")
    def CmdPasteAttrs(self):       self._Success("ctrl", "alt", "v")
    def CmdRemoveAttributes(self): self._Success("ctrl", "alt", "x")  # Remove Attributes = Ctrl+Alt+X
    def CmdClear(self): self._Success("delete")
    def CmdRippleDelete(self):
        print(f"Command '{self.inputWord}' recognized!")
        pyautogui.rightClick()
        time.sleep(0.4)
        pyautogui.press('r')
    def CmdDuplicate(self): self._Success("ctrl", "shift", "/")
    def CmdSelectAll(self): self._Success("ctrl", "a")
    def CmdDeselectAll(self): self._Success("ctrl", "shift", "a")
    def CmdFind(self): self._Success("ctrl", "f")
    def CmdEditOriginal(self): self._Success("ctrl", "e")
    def CmdShortcuts(self): self._Success("ctrl", "alt", "k")

    # --- Playback ---
    def CmdPlay(self): self._Success("l")     # L = play forward (JKL shuttle)
    def CmdPause(self): self._Success("k")    # K = stop/pause (JKL shuttle)

    # --- Editing ---
    def CmdOverwrite(self): self._Success(".")
    def CmdInsert(self): self._Success(",")
    def CmdMarkIn(self): self._Success("i")
    def CmdMarkOut(self): self._Success("o")
    def CmdNest(self): self._Success("ctrl", "alt", "shift", "y")
    def CmdMakeSubclip(self): self._Success("ctrl", "u")
    def CmdAddEdit(self):    self._Success("ctrl", "k")
    def CmdAddEditAll(self): self._Success("ctrl", "shift", "k")  # Add Edit to All Tracks
    def CmdTrimEdit(self):   self._Success("shift", "t")          # Trim Edit tool
    def CmdRectangle(self): self._Success("ctrl", "alt", "r")
    def CmdExtend(self): self._Success("e")
    def CmdMarker(self): self._Success("m")
    def CmdAddTransition(self): self._Success("ctrl", "d")  # Apply default video transition

    # --- Effects search ---
    def _effects_search(self, effect_name, image_path: str | None = None):
        import image_matcher
        import mouse_tracker
        import search_calibration

        print(f"Command '{self.inputWord}' recognized!")

        # 1. Use the last place the user clicked as the drop target.
        drop_x, drop_y = mouse_tracker.get_last_click()
        print(f"[effects] Drop target (last click) at ({drop_x}, {drop_y})")

        # 2. Open the Effects panel.
        pyautogui.hotkey("shift", "7")
        time.sleep(0.08)

        # 3. Click the calibrated search box position to focus it, then
        #    select-all so any existing text is cleared by the first typed letter.
        #    Suppress the click so mouse_tracker keeps the user's last position.
        _sx, _sy = search_calibration.get_or_calibrate()
        with mouse_tracker.suppress_clicks():
            pyautogui.click(_sx, _sy)
        time.sleep(0.1)
        pyautogui.hotkey("ctrl", "a")

        # 4. Type the spoken keyword — always the keyword so Premiere's search
        #    matches the right effect regardless of what the image file is named.
        pyautogui.typewrite(effect_name, interval=0.04)

        # 5. Wait for Premiere to populate the results list, then confirm search
        time.sleep(0.2)
        pyautogui.press("enter")
        time.sleep(0.1)

        # 6. Find the effect on screen.
        #    If an explicit image_path was stored (custom command), load that
        #    file directly so the keyword takes priority over the image filename.
        #    Otherwise fall back to name-based lookup inside Effects/.
        if image_path:
            result = image_matcher.find_on_screen_from_path(image_path)
        else:
            result = image_matcher.find_on_screen(
                effect_name, subfolder=image_matcher.EFFECTS_SUBDIR
            )
        if result is None:
            print(f"[effects] '{effect_name}' not found on screen — search left open.")
            return

        fx, fy, fw, fh = result
        effect_cx = fx + fw // 2
        effect_cy = fy + fh // 2
        print(f"[effects] Found '{effect_name}' at ({effect_cx}, {effect_cy}), dragging to ({drop_x}, {drop_y})")

        # 7. Drag from the effect in the panel to the drop target.
        #    Suppress the click tracker so the programmatic mouseDown doesn't
        #    overwrite the user's last-click position.
        with mouse_tracker.suppress_clicks():
            pyautogui.moveTo(effect_cx, effect_cy)
            time.sleep(0.1)
            pyautogui.mouseDown(button="left")
            time.sleep(0.15)
            pyautogui.moveTo(drop_x, drop_y, duration=0.1)
            pyautogui.mouseUp(button="left")



    def CmdEffectsBlur(self): self._effects_search("gaussian blur")
    def CmdEffectsCrossDissolve(self): self._effects_search("cross dissolve")
    def CmdEffectsLumetri(self): self._effects_search("lumetri color")
    def CmdEffectsNoise(self): self._effects_search("noise")
    def CmdEffectsWarpStabilizer(self): self._effects_search("warp stabilizer")
    def CmdEffectsWaveWarp(self): self._effects_search("wave warp")
    def CmdEffectsCross(self): self._effects_search("cross")

    # --- Labels ---
    # PostMessage sends directly to Premiere's focused child window without
    # touching focus, bypassing all keyboard hooks and panel-focus resets.
    _VK_FN = {7:0x76,8:0x77,9:0x78,10:0x79,11:0x7A,12:0x7B,
              13:0x7C,14:0x7D,15:0x7E,16:0x7F,17:0x80,18:0x81}

    def _label(self, fn_num, with_shift=False):
        print(f"Command '{self.inputWord}' recognized!")
        pymod = "shift" if with_shift else "alt"
        pyautogui.keyDown(pymod)
        time.sleep(0.05)
        pyautogui.press(f"f{fn_num}")
        time.sleep(0.05)
        pyautogui.keyUp(pymod)

    def CmdLabelNone(self):      print("label none: no shortcut assigned in Premiere")
    def CmdLabelViolet(self):    self._label(1)                   # Alt+F1 = Violet
    def CmdLabelIris(self):      self._label(2)                   # Alt+F2 = Iris
    def CmdLabelCaribbean(self): self._label(3)                   # Alt+F3 = Caribbean
    def CmdLabelLavender(self):  self._label(5)                   # Alt+F5 = Lavender
    def CmdLabelCerulean(self):  self._label(6)                   # Alt+F6 = Cerulean
    def CmdLabelForest(self):    self._label(7)                   # Alt+F7 = Forest
    def CmdLabelRose(self):      self._label(8)                   # Alt+F8 = Rose
    def CmdLabelMango(self):     self._label(9)                   # Alt+F9 = Mango
    def CmdLabelPurple(self):    self._label(10)                  # Alt+F10 = Purple
    def CmdLabelBlue(self):      self._label(11)                  # Alt+F11 = Blue
    def CmdLabelTeal(self):      self._label(12)                  # Alt+F12 = Teal
    def CmdLabelMagenta(self):   self._label(10, with_shift=True) # Shift+F10 = Magenta
    def CmdLabelTan(self):       self._label(11, with_shift=True) # Shift+F11 = Tan
    def CmdLabelGreen(self):     self._label(12, with_shift=True) # Shift+F12 = Green
    def CmdLabelYellow(self):                                      # Ctrl+Shift+F1 = Yellow
        print(f"Command '{self.inputWord}' recognized!")
        pyautogui.keyDown('ctrl'); pyautogui.keyDown('shift')
        pyautogui.press('f1')
        pyautogui.keyUp('shift'); pyautogui.keyUp('ctrl')
    def CmdLabelBrown(self):                                       # Ctrl+Alt+F1 = Brown
        print(f"Command '{self.inputWord}' recognized!")
        pyautogui.keyDown('ctrl'); pyautogui.keyDown('alt')
        pyautogui.press('f1')
        pyautogui.keyUp('alt'); pyautogui.keyUp('ctrl')

    # --- Markers ---
    def CmdMarkerGreen(self): self._Success("m")
    def CmdNextMarker(self): self._Success("shift", "m")
    def CmdPreviousMarker(self): self._Success("ctrl", "shift", "m")
    def CmdMarkerRed(self): self._Success("alt", "1")        # marker.add.1 = Red
    def CmdMarkerViolet(self): self._Success("alt", "6")    # marker.add.2 = Violet
    def CmdMarkerOrange(self): self._Success("alt", "2")    # marker.add.3 = Orange
    def CmdMarkerYellow(self): self._Success("alt", "3")    # marker.add.4 = Yellow
    def CmdMarkerBlue(self): self._Success("alt", "5")      # marker.add.6 = Blue
    def CmdMarkerWhite(self): self._Success("alt", "7")     # marker.add.5 = White
    def CmdMarkerCyan(self): self._Success("alt", "4")      # marker.add.7 = Cyan
    def CmdClearMarker(self): self._Success("ctrl", "alt", "m")
    def CmdClearAllMarkers(self): self._Success("ctrl", "shift", "alt", "m")
    def CmdEditMarker(self): self._Success("ctrl", "alt", "3")

    # --- Editing (new) ---
    def CmdSpeed(self):              self._Success("ctrl", "r")
    def CmdSubclip(self):            self._Success("ctrl", "u")
    def CmdSubsequence(self):        self._Success("shift", "u")
    def CmdGroup(self):              self._Success("ctrl", "g")
    def CmdUngroup(self):            self._Success("ctrl", "shift", "g")
    def CmdLift(self):               self._Success(";")
    def CmdExtract(self):            self._Success("'")
    def CmdMatchFrame(self):         self._Success("f")
    def CmdReverseMatchFrame(self):  self._Success("shift", "r")
    def CmdSelectClip(self):         self._Success("d")
    def CmdExtendEdit(self):         self._Success("e")
    def CmdRippleTrimNext(self):     self._Success("w")
    def CmdRippleTrimPrevious(self): self._Success("q")
    def CmdExportFrame(self):        self._Success("ctrl", "shift", "e")
    def CmdApplyAudioTransition(self): self._Success("ctrl", "shift", "d")
    def CmdApplyBothTransitions(self): self._Success("shift", "d")
    def CmdEnableClip(self):         self._Success("shift", "e")
    def CmdDeleteEffects(self):      self._Success("ctrl", "alt", ";")
    def CmdFitToFrame(self):         self._Success("ctrl", "shift", "f5")   # Fit to Frame = Ctrl+Shift+F5
    def CmdFillFrame(self):          self._Success("ctrl", "shift", "f6")   # Fill Frame = Ctrl+Shift+F6
    def CmdScaleToFrame(self):       self._Success("ctrl", "shift", "f4")   # Scale to Frame Size = Ctrl+Shift+F4
    def CmdClearIn(self):            self._Success("ctrl", "shift", "i")
    def CmdClearOut(self):           self._Success("ctrl", "shift", "o")
    def CmdPasteInsert(self):        self._Success("ctrl", "shift", "v")
    def CmdVolumeUp(self):           self._Success("]")
    def CmdVolumeDown(self):         self._Success("[")
    def CmdBigVolumeUp(self):        self._Success("shift", "]")
    def CmdBigVolumeDown(self):      self._Success("shift", "[")
    def CmdNextGap(self):            self._Success("shift", ";")
    def CmdPreviousGap(self):        self._Success("ctrl", "shift", ";")
    def CmdZoomToFit(self):          self._Success("\\")
    def CmdZoomToFrame(self):        self._Success("ctrl", "\\")
    def CmdZoomIn(self):             self._Success("=")              # Zoom In timeline = =
    def CmdZoomOut(self):            self._Success("-")              # Zoom Out timeline = -
    def CmdNextScreen(self):         self._Success("pagedown")       # Show Next Screen = Page Down
    def CmdPreviousScreen(self):     self._Success("pageup")        # Show Previous Screen = Page Up
    def CmdMaximize(self):           self._Success("`")
    def CmdRevealNested(self):       self._Success("ctrl", "alt", "f")

    # --- New Panels ---
    def CmdNewBin(self):             self._Success("ctrl", "/")
    def CmdQuickExport(self):        self._Success("ctrl", "shift", "q")
    def CmdMediaBrowser(self):       self._Success("shift", "8")
    def CmdAudioClipMixer(self):     self._Success("shift", "9")

    # --- Panels / Tools ---
    def CmdBinWindow(self): self._Success("shift", "1")
    def CmdSourceMonitor(self): self._Success("shift", "2")
    def CmdTimeline(self): self._Success("shift", "3")
    def CmdPreviewWindow(self): self._Success("shift", "4")
    def CmdEffectControls(self): self._Success("shift", "5")
    def CmdAudioMixer(self): self._Success("shift", "6")
    def CmdEffectsPanel(self):
        print(f"Command '{self.inputWord}' recognized!")
        pyautogui.hotkey("shift", "7")
        time.sleep(0.2)
        pyautogui.press("tab", presses=2)
    def CmdTrim(self): self._Success("v")
    def CmdRip(self): self._Success("b")
    def CmdPenTool(self): self._Success("p")
    def CmdSelectionTool(self): self._Success("v")
    def CmdText(self): self._Success("t")
    def CmdSlipTool(self): self._Success("y")
    def CmdOpenInSourceMonitor(self): self._Success("ctrl", "shift", "o")
    def CmdClearInAndOut(self): self._Success("ctrl", "shift", "x")
    def CmdRoll(self): self._Success("n")
    def CmdUnlinkSelection(self): self._Success("ctrl", "alt", "shift", "l")
    def CmdLinkSelection(self): self._Success("ctrl", "alt", "shift", "l")
    def CmdRevealInProject(self): self._Success("ctrl", "shift", "alt", "f")
    def CmdToggleSnap(self): self._Success("s")
    def CmdRename(self): self._Success("ctrl", "shift", "r")
    def CmdMulticamSequence(self): self._Success("ctrl", "alt", "f7")  # Create Multi-Camera Source Sequence — assign Ctrl+Alt+F7 in Premiere
    def CmdSync(self):
        print(f"Command '{self.inputWord}' recognized!")
        # Launches sync_clips.py in the background — voice recognition keeps running
        # while you click the two clips to synchronize.
        subprocess.Popen([sys.executable,
                          os.path.join(os.path.dirname(__file__),
                                       "customScripts", "sync_clips.py")])
    def CmdSyncWindow(self):
        print(f"Command '{self.inputWord}' recognized!")
        subprocess.Popen([sys.executable,
                          os.path.join(os.path.dirname(__file__),
                                       "customScripts", "sync_clips_manual.py")])
    def CmdEnableMulticam(self): self._Success("shift", "0")
    def CmdLink(self): self._Success("ctrl", "l")

    # --- Tools ---
    def CmdRateStretch(self):              self._Success("r")
    def CmdRazor(self):                    self._Success("c")
    def CmdRazorAll(self):                 self._Success("ctrl", "shift", "k")
    def CmdSlide(self):                    self._Success("u")
    def CmdHand(self):                     self._Success("h")
    def CmdZoomTool(self):                 self._Success("z")
    def CmdTrackSelect(self):              self._Success("shift", "a")

    # --- Track targeting ---
    def _press_fkey(self, fkey, shift=False):
        print(f"Command '{self.inputWord}' recognized!")
        if shift:
            pyautogui.keyDown('shift')
        pyautogui.keyDown(fkey)
        pyautogui.keyUp(fkey)
        if shift:
            pyautogui.keyUp('shift')

    def CmdTargetVideo1(self):   self._press_fkey("f2")
    def CmdTargetVideo2(self):   self._press_fkey("f3")
    def CmdTargetVideo3(self):   self._press_fkey("f4")
    def CmdTargetVideo4(self):   self._press_fkey("f5")
    def CmdTargetVideo5(self):   self._press_fkey("f6")
    def CmdTargetAudio1(self):   self._press_fkey("f2", shift=True)
    def CmdTargetAudio2(self):   self._press_fkey("f3", shift=True)
    def CmdTargetAudio3(self):   self._press_fkey("f4", shift=True)
    def CmdTargetAudio4(self):   self._press_fkey("f5", shift=True)
    def CmdTargetAudio5(self):   self._press_fkey("f6", shift=True)
    def CmdTargetAllVideo(self): self._Success("ctrl", "0")
    def CmdTargetAllAudio(self): self._Success("ctrl", "9")
    def CmdSourceAllVideo(self): self._Success("ctrl", "alt", "0")
    def CmdSourceAllAudio(self): self._Success("ctrl", "alt", "9")

    # --- Transport / Playback ---
    def CmdTogglePlay(self):               self._Success("space")
    def CmdPlayAround(self):               self._Success("shift", "k")
    def CmdStepBack(self):                 self._Success("left")
    def CmdStepForward(self):              self._Success("right")
    def CmdStepBack5(self):                self._Success("shift", "left")
    def CmdStepForward5(self):             self._Success("shift", "right")
    def CmdGoToSequenceStart(self):        self._Success("home")
    def CmdGoToSequenceEnd(self):          self._Success("end")
    def CmdGoToClipStart(self):            self._Success("shift", "home")
    def CmdGoToClipEnd(self):              self._Success("shift", "end")
    def CmdReverse(self):                  self._Success("j")
    def CmdSlowReverse(self):              self._Success("shift", "j")
    def CmdSlowPlay(self):                 self._Success("shift", "l")
    def CmdPlayEdit(self):                 self._Success("shift", "k")
    def CmdPlayInToOut(self):              self._Success("ctrl", "shift", "space")  # Play In to Out = Ctrl+Shift+Space
    def CmdPlayToOut(self):                self._Success("ctrl", "space")            # Play from Playhead to Out = Ctrl+Space

    # --- Sequence editing (extended) ---
    def CmdExtendNext(self):               self._Success("shift", "w")
    def CmdExtendPrevious(self):           self._Success("shift", "q")
    def CmdJoinThroughEdits(self):         self._Success("ctrl", "alt", "shift", "j")
    def CmdCloseGaps(self):                self._Success("ctrl", "alt", "g")
    def CmdAddTrack(self):                 self._Success("ctrl", "alt", "shift", "x")
    def CmdAddVideoTrack(self):            self._Success("ctrl", "alt", "shift", "end")
    def CmdRenameAudioTrack(self):         self._Success("ctrl", "alt", "shift", "u")
    def CmdRenameVideoTrack(self):         self._Success("ctrl", "alt", "shift", "w")
    def CmdDeleteTracks(self):             self._Success("ctrl", "shift", "alt", "z")
    def CmdToggleTrimType(self):           self._Success("ctrl", "shift", "t")
    def CmdSelectionFollowsPlayhead(self): self._Success("ctrl", "alt", "j")
    def CmdFlattenMulticam(self):              self._Success("ctrl", "shift", "=")
    def CmdToggleMulticam(self):               self._Success("ctrl", "shift", "-")
    def CmdMulticamAudioFollowsVideo(self):    self._Success("ctrl", "shift", "\\")
    def CmdIncreaseAudioKeyframe(self):    self._Success("shift", "alt", "f2")   # Increase Audio Keyframe Value = Alt+Shift+F2
    def CmdDecreaseAudioKeyframe(self):    self._Success("shift", "alt", "f3")   # Decrease Audio Keyframe Value = Alt+Shift+F3
    def CmdIncreaseVideoKeyframe(self):    self._Success("shift", "alt", "f5")   # Increase Video Keyframe Value = Alt+Shift+F5
    def CmdDecreaseVideoKeyframe(self):    self._Success("shift", "alt", "f6")   # Decrease Video Keyframe Value = Alt+Shift+F6
    def CmdAddAudioKeyframe(self):         self._Success("ctrl", "shift", "alt", "a")
    def CmdAddVideoKeyframe(self):         self._Success("ctrl", "shift", "alt", "v")
    def CmdNextKeyframe(self):             self._Success("ctrl", "alt", ",")
    def CmdPreviousKeyframe(self):         self._Success("ctrl", "alt", "/")
    def CmdEaseIn(self):                   self._Success("shift", "alt", "f11")  # Ease In = Alt+Shift+F11
    def CmdEaseOut(self):                  self._Success("shift", "alt", "f12")  # Ease Out = Alt+Shift+F12
    def CmdLinearKeyframe(self):           self._Success("ctrl", "alt", "home")
    def CmdHoldKeyframe(self):             self._Success("ctrl", "shift", "alt", '"')
    def CmdTrimInToPlayhead(self):         self._Success("ctrl", "alt", "q")
    def CmdTrimOutToPlayhead(self):        self._Success("ctrl", "alt", "w")

    # --- Markers (extended) ---
    def CmdGoToIn(self):                   self._Success("shift", "i")
    def CmdGoToOut(self):                  self._Success("shift", "o")
    def CmdMarkClip(self):                 self._Success("x")
    def CmdRangeMarker(self):              self._Success("ctrl", "shift", "alt", "n")
    def CmdChapterMarker(self):            self._Success("ctrl", "alt", "4")
    def CmdShowMarkers(self):              self._Success("ctrl", "alt", "7")

    # --- Audio clip options ---
    def CmdAudioGainDialog(self):          self._Success("g")
    def CmdBreakOutMono(self):             self._Success("shift", "alt", "a")
    def CmdEnhanceSpeech(self):            self._Success("shift", "alt", "h")    # Enable Enhance Speech = Alt+Shift+H
    def CmdNudgeVolumeDown(self):          self._Success("shift", "alt", "j")
    def CmdNudgeVolumeUp(self):            self._Success("shift", "alt", "u")
    def CmdNudgeVolumeDown3(self):         self._Success("shift", "alt", "l")
    def CmdNudgeVolumeUp3(self):           self._Success("shift", "alt", "k")
    def CmdChannelMappings(self):          self._Success("shift", "g")

    # --- Clip options ---
    def CmdReplaceFromBin(self):           self._Success("shift", "alt", "i")
    def CmdReplaceFromSource(self):        self._Success("shift", "alt", "o")
    def CmdReplaceFotage(self):            self._Success("shift", "alt", "f")
    def CmdFrameSampling(self):             self._Success("ctrl", "shift", "f7")          # Frame Sampling = Ctrl+Shift+F7
    def CmdFrameBlend(self):               self._Success("ctrl", "shift", "f8")          # Frame Blending = Ctrl+Shift+F8
    def CmdOpticalFlow(self):              self._Success("ctrl", "shift", "f9")          # Optical Flow = Ctrl+Shift+F9
    def CmdRender(self):                   self._Success("enter")                         # Render Effects in Work Area = Enter
    def CmdRenderReplace(self):            self._Success("ctrl", "shift", "f11")          # Render and Replace = Ctrl+Shift+F11
    def CmdRestoreUnrendered(self):        self._Success("ctrl", "shift", "alt", "d")
    def CmdAddFrameHold(self):             self._Success("ctrl", "shift", "f3")           # Add Frame Hold = Ctrl+Shift+F3
    def CmdFrameHoldOptions(self):         self._Success("ctrl", "shift", "f2")           # Frame Hold Options = Ctrl+Shift+F2
    def CmdCreateProxies(self):            self._Success("ctrl", "alt", "shift", "f2")    # Create Proxies = Ctrl+Alt+Shift+F2
    def CmdGeneratePeaks(self):            self._Success("shift", "alt", "x")
    def CmdInterpretFotage(self):          self._Success("ctrl", "shift", "alt", "i")
    def CmdSynchronizeClips(self):         self._Success("ctrl", "alt", "shift", "s")  # Synchronize = Ctrl+Alt+Shift+S

    # --- Timeline display ---
    def CmdExpandTracks(self):             self._Success("shift", "=")
    def CmdMinimizeTracks(self):           self._Success("shift", "-")
    def CmdIncreaseVideoTrackHeight(self): self._Success("ctrl", "=")
    def CmdDecreaseVideoTrackHeight(self): self._Success("ctrl", "-")
    def CmdIncreaseAudioTrackHeight(self): self._Success("alt", "=")
    def CmdDecreaseAudioTrackHeight(self): self._Success("alt", "-")
    def CmdWorkAreaIn(self):               self._Success("alt", "[")
    def CmdWorkAreaOut(self):              self._Success("alt", "]")
    def CmdToggleAudioScrubbing(self):     self._Success("shift", "s")
    def CmdToggleTrackMutes(self):         self._Success("ctrl", "shift", "alt", "o")
    def CmdToggleTrackSolos(self):         self._Success("ctrl", "shift", "alt", "q")
    def CmdSequenceLabelColor(self):       self._Success("ctrl", "shift", "alt", ".")
    def CmdAudioUnits(self):               self._Success("alt", "a")

    # --- Track height presets (Ctrl+F2 … Ctrl+F11) ---
    def CmdTrackHeight1(self):             self._Success("ctrl", "f2")
    def CmdTrackHeight2(self):             self._Success("ctrl", "f3")
    def CmdTrackHeight3(self):             self._Success("ctrl", "f4")
    def CmdTrackHeight4(self):             self._Success("ctrl", "f5")
    def CmdTrackHeight5(self):             self._Success("ctrl", "f6")
    def CmdTrackHeight6(self):             self._Success("ctrl", "f7")
    def CmdTrackHeight7(self):             self._Success("ctrl", "f8")
    def CmdTrackHeight8(self):             self._Success("ctrl", "f9")
    def CmdTrackHeight9(self):             self._Success("ctrl", "f10")
    def CmdTrackHeight10(self):            self._Success("ctrl", "f11")

    # --- Graphics ---
    def CmdAddText(self):                  self._Success("ctrl", "t")
    def CmdAddEllipse(self):               self._Success("ctrl", "alt", "e")
    def CmdEnterTextEdit(self):            self._Success("ctrl", "alt", "'")
    def CmdLayerUp(self):                  self._Success("ctrl", "]")
    def CmdLayerDown(self):                self._Success("ctrl", "[")
    def CmdLayerToTop(self):               self._Success("ctrl", "shift", "]")
    def CmdLayerToBottom(self):            self._Success("ctrl", "shift", "[")
    def CmdAlignCenter(self):              self._Success("ctrl", "shift", "c")

    # --- Captions ---
    def CmdAddCaption(self):               self._Success("ctrl", "alt", "c")
    def CmdSplitCaption(self):             self._Success("ctrl", "alt", "pagedown")  # Split Caption Segment Under Playhead = Ctrl+Alt+Page Down
    def CmdMergeCaptions(self):            self._Success("ctrl", "shift", "b")

    # --- File / Project ---
    def CmdCloseSequence(self):            self._Success("ctrl", "w")
    def CmdColorProperties(self):          self._Success("ctrl", "shift", "alt", "c")
    def CmdRefreshProject(self):           self._Success("shift", "alt", "r")
    def CmdSetPosterFrame(self):           self._Success("shift", "p")
    def CmdBinFromSelection(self):         self._Success("shift", "b")
    def CmdNewSmartBin(self):              self._Success("ctrl", "shift", "alt", "f17")

    # --- Monitor ---
    def CmdFullscreen(self):               self._Success("ctrl", "`")
    def CmdMaximizeFocused(self):          self._Success("shift", "`")
    def CmdGuides(self):                   self._Success("ctrl", ";")
    def CmdOverlays(self):                 self._Success("ctrl", "alt", "p")
    def CmdProgramZoomFit(self):           self._Success("ctrl", "shift", "0")
    def CmdProgramZoom100(self):           self._Success("ctrl", "shift", "1")
    def CmdSourceZoomFit(self):            self._Success("ctrl", "shift", "alt", "0")
    def CmdSourceZoom100(self):            self._Success("ctrl", "shift", "alt", "1")

    # --- Workspaces ---
    def CmdWorkspace1(self):               self._Success("shift", "alt", "1")
    def CmdWorkspace2(self):               self._Success("shift", "alt", "2")
    def CmdWorkspace3(self):               self._Success("shift", "alt", "3")
    def CmdWorkspace4(self):               self._Success("shift", "alt", "4")
    def CmdWorkspace5(self):               self._Success("shift", "alt", "5")
    def CmdWorkspace6(self):               self._Success("shift", "alt", "6")
    def CmdWorkspace7(self):               self._Success("shift", "alt", "7")
    def CmdWorkspace8(self):               self._Success("shift", "alt", "8")
    def CmdWorkspace9(self):               self._Success("shift", "alt", "9")
    def CmdRevertWorkspace(self):          self._Success("shift", "alt", "0")

    # --- Panel navigation ---
    def CmdNextPanel(self):                self._Success("ctrl", "shift", ".")
    def CmdPreviousPanel(self):            self._Success("ctrl", "shift", ",")
    def CmdOpenTextPanel(self):            self._Success("ctrl", "shift", "j")

    # --- Effects panel ---
    def CmdFindEffects(self):              self._Success("shift", "f")
    def CmdSaveEffectPreset(self):         self._Success("ctrl", "alt", ".")
    def CmdDeleteAllEffects(self):         self._Success("ctrl", "alt", ";")

    def CmdRecalibrate(self):
        """Re-run the Effects search-box calibration picker."""
        print("Command 'recalibrate' recognized!")
        import search_calibration
        search_calibration.run_effects_picker()

    def CmdRecalibrateSearch(self):
        """Re-run the search-bar calibration picker."""
        print("Command 'recalibrate search' recognized!")
        import search_calibration
        search_calibration.run_search_bar_picker()

    # --- Pan ---
    def CmdPanCenter(self):                self._Success("ctrl", "shift", "alt", "e")
    def CmdPanLeft(self):                  self._Success("ctrl", "shift", "alt", "g")
    def CmdPanRight(self):                 self._Success("ctrl", "shift", "alt", "k")

    # --- Multicam cameras ---
    def CmdCamera1(self):                  self._Success("1")
    def CmdCamera2(self):                  self._Success("2")
    def CmdCamera3(self):                  self._Success("3")
    def CmdCamera4(self):                  self._Success("4")
    def CmdCamera5(self):                  self._Success("5")
    def CmdCamera6(self):                  self._Success("6")
    def CmdCamera7(self):                  self._Success("7")
    def CmdCamera8(self):                  self._Success("8")
    def CmdCamera9(self):                  self._Success("9")

    # ── tvh commands ───────────────────────────────────────────────────────────

    def CmdEaseInOut(self):
        """Apply Ease In + Ease Out to selected keyframes.
        Requires EASE_IN / EASE_OUT shortcuts assigned in Premiere — see tvh/config.py."""
        print(f"Command '{self.inputWord}' recognized!")
        from tvh.playback import ease_in_and_out
        ease_in_and_out()

    def CmdCloseTitler(self):
        """Close the Legacy Titler window or a Marker dialog."""
        print(f"Command '{self.inputWord}' recognized!")
        from tvh.misc import close_titler
        close_titler()

    def CmdLockTracks(self):
        """Toggle V1 + A1 track lock state.
        Requires reference PNGs in WORKING_DIR — see tvh/config.py."""
        print(f"Command '{self.inputWord}' recognized!")
        from tvh.timeline import track_locker
        track_locker()

    def CmdCropHandles(self):
        """Click the Crop transform button in Effect Controls for drag handles.
        Requires CROP_transform_2020.png in WORKING_DIR — see tvh/config.py."""
        print(f"Command '{self.inputWord}' recognized!")
        from tvh.transform import crop_click
        crop_click()

    def CmdTransformHandles(self):
        """Click the Motion transform icon in Effect Controls.
        Requires ClassNN calibration — see tvh/transform.py."""
        print(f"Command '{self.inputWord}' recognized!")
        from tvh.transform import click_transform_icon2
        click_transform_icon2()

    def CmdMonoLeft(self):
        """Configure selected clip for mono (left channel)."""
        print(f"Command '{self.inputWord}' recognized!")
        from tvh.audio import audio_mono_maker
        audio_mono_maker('left')

    def CmdMonoRight(self):
        """Configure selected clip for mono (right channel)."""
        print(f"Command '{self.inputWord}' recognized!")
        from tvh.audio import audio_mono_maker
        audio_mono_maker('right')

    # ── Effect Controls value clicks ───────────────────────────────────────────

    def _ec_click(self, name: str, blue_index: int = 0) -> None:
        """Open Effect Controls, then click-hold the named parameter's blue value."""
        import image_matcher
        print(f"Command '{self.inputWord}' recognized!")
        pyautogui.hotkey("shift", "5")
        time.sleep(0.3)
        found, cx, cy = image_matcher.click_image(
            name, click_blue=True, subfolder=image_matcher.CLICK_SUBDIR, blue_index=blue_index
        )
        if not found:
            print(f"[ec_click] '{name}' not found on screen")

    def CmdEcPositionX(self):    self._ec_click("position x")
    def CmdEcPositionY(self):    self._ec_click("position y", blue_index=1)
    def CmdEcScale(self):        self._ec_click("scale")
    def CmdEcScaleWidth(self):   self._ec_click("scale width")
    def CmdEcUniformScale(self): self._ec_click("uniform scale")
    def CmdEcRotation(self):     self._ec_click("rotation")
    def CmdEcAnchorX(self):      self._ec_click("anchor x")
    def CmdEcAnchorY(self):      self._ec_click("anchor y", blue_index=1)
    def CmdEcAntiFlicker(self):  self._ec_click("anti flicker filter")
    def CmdEcCropLeft(self):     self._ec_click("crop left")
    def CmdEcCropTop(self):      self._ec_click("crop top")
    def CmdEcCropRight(self):    self._ec_click("crop right")
    def CmdEcCropBottom(self):   self._ec_click("crop bottom")
    def CmdEcOpacity(self):      self._ec_click("opacity")
    def CmdEcBlendMode(self):    self._ec_click("blend mode")
    def CmdEcTimeRemapping(self): self._ec_click("time remapping")
