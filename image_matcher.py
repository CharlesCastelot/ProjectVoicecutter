# ABOUTME: Screen image matching — finds UI elements by template and clicks target color regions.
import ctypes
import json
import os
from pathlib import Path

import cv2
import numpy as np
import pyautogui

# Request per-monitor DPI awareness so screenshots and coordinates are
# always in physical pixels regardless of Windows display scaling.
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)  # PER_MONITOR_DPI_AWARE
except Exception:
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)  # SYSTEM_DPI_AWARE
    except Exception:
        pass

# Detect the primary monitor's physical DPI.  We use GetDpiForMonitor on the
# primary monitor when available (gives per-monitor accuracy); otherwise fall
# back to GetDpiForSystem.
def _get_primary_dpi() -> float:
    try:
        # MonitorFromPoint(0,0) → primary monitor handle
        pt = ctypes.wintypes.POINT(0, 0)
        hmon = ctypes.windll.user32.MonitorFromPoint(pt, 1)  # MONITOR_DEFAULTTOPRIMARY
        dpi_x = ctypes.c_uint(0)
        dpi_y = ctypes.c_uint(0)
        # GetDpiForMonitor(hmon, MDT_EFFECTIVE_DPI=0, &dpi_x, &dpi_y)
        ctypes.windll.shcore.GetDpiForMonitor(hmon, 0, ctypes.byref(dpi_x), ctypes.byref(dpi_y))
        return float(dpi_x.value)
    except Exception:
        try:
            return float(ctypes.windll.user32.GetDpiForSystem())
        except Exception:
            return 96.0

_dpi = _get_primary_dpi()
_DPI_SCALE = _dpi / 96.0

# ---------------------------------------------------------------------------
# Scale cache — persists the best-match scale for each (DPI, template) pair.
# First run on a new device does a full 0.4×–2.5× sweep to find the right
# scale; every run after that loads it directly.  Templates captured on any
# machine therefore work everywhere without recapturing.
# ---------------------------------------------------------------------------
_SCALE_CACHE_FILE = Path("ImageReference") / ".scale_cache.json"
_scale_cache: dict[str, float] = {}

# In-memory position cache — stores the last known screen location of each
# matched image so subsequent calls can skip the full-screen sweep entirely.
# On a repeated call, a 40px-padded ROI crop + 1 matchTemplate is used instead
# of the full 22-call multiscale sweep.  Invalidates automatically if the ROI
# verify fails (e.g. panel scrolled / effect list changed).
_position_cache: dict[str, tuple[int, int, int, int, str, float]] = {}
# key: image_name → (screen_x, screen_y, match_w, match_h, ref_path_str, found_scale)

# Default search ROI — restricts full-screen sweeps to a known panel region on
# the first call.  Loaded from ImageReference/.default_roi.json at startup.
# Once _position_cache has a real hit for the image, this is bypassed entirely.
_DEFAULT_ROI_FILE = Path("ImageReference") / ".default_roi.json"
_global_default_roi: tuple[int, int, int, int] | None = None  # (x1, y1, x2, y2)


def _load_scale_cache() -> None:
    global _scale_cache
    try:
        with open(_SCALE_CACHE_FILE) as f:
            _scale_cache = json.load(f)
    except Exception:
        _scale_cache = {}


def _save_scale(cache_key: str, scale: float) -> None:
    """Persist a discovered scale so future runs skip the wide search."""
    _scale_cache[cache_key] = round(scale, 4)
    try:
        _SCALE_CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(_SCALE_CACHE_FILE, "w") as f:
            json.dump(_scale_cache, f, indent=2)
    except Exception:
        pass


def _cache_key(template_path: Path | str) -> str:
    """Key includes DPI so each device stores its own scale per template."""
    return f"{_dpi:.0f}:{Path(template_path).as_posix()}"


def _load_default_roi() -> None:
    """Load the default search ROI from disk into _global_default_roi."""
    global _global_default_roi
    try:
        with open(_DEFAULT_ROI_FILE) as f:
            d = json.load(f)
        x1, y1, x2, y2 = int(d["x1"]), int(d["y1"]), int(d["x2"]), int(d["y2"])
        _global_default_roi = (x1, y1, x2, y2)
        print(f"[image_matcher] Default ROI loaded: ({x1},{y1}) → ({x2},{y2})")
    except Exception:
        _global_default_roi = None


_load_scale_cache()
_load_default_roi()

# ---------------------------------------------------------------------------
# Premiere DPI scale detection — detects which monitor Premiere is on and
# reads that monitor's DPI.  Result is cached on disk so the expensive window
# enumeration only runs once per session (or when the cache is cleared).
#
# Folder naming: pre-captured images for a given DPI live in subfolders named
#   ImageReference/DPI_100/   (96 DPI  → 1.0×)
#   ImageReference/DPI_125/   (120 DPI → 1.25×)
#   ImageReference/DPI_150/   (144 DPI → 1.5×)
#   ImageReference/DPI_175/   (168 DPI → 1.75×)
#   ImageReference/DPI_200/   (192 DPI → 2.0×)
#   ImageReference/DPI_225/   (216 DPI → 2.25×)
#
# When a DPI-specific image is found for the detected scale, the matcher uses
# it at hint_scale=1.0 (no dynamic rescaling needed → faster and more accurate).
# ---------------------------------------------------------------------------
_PREMIERE_DPI_FILE = Path("ImageReference") / ".premiere_dpi.json"
_DPI_SCALE_FOLDERS = ["DPI_100", "DPI_125", "DPI_150", "DPI_175", "DPI_200", "DPI_225"]
_premiere_dpi_scale: float | None = None  # None = not yet detected this session

# ---------------------------------------------------------------------------
# In-memory reference image index — built once at startup by
# build_reference_index().  Replaces per-call rglob scans (O(N) filesystem
# walk) with O(1) dict lookups.
#
# When duplicate names exist — e.g. both "Iris Box.png" and "Iris_Box.png"
# normalise to "iris_box" — sorted iteration lets the underscore variant
# overwrite the space variant, so the canonical name always wins.
# ---------------------------------------------------------------------------
_base_index: dict[str, dict[str, Path]] = {}
# {subfolder_lower: {norm_name: path}}
# e.g. {"effects": {"cross_dissolve": Path("ImageReference/Effects/Cross_Dissolve.png")}}

_dpi_folder_index: dict[str, dict[str, dict[str, Path]]] = {}
# {dpi_folder: {subfolder_lower: {norm_name: path}}}


def _dpi_folder_name(scale: float) -> str:
    """Map a DPI scale factor to the nearest standard folder name."""
    candidates = [1.0, 1.25, 1.5, 1.75, 2.0, 2.25]
    best = min(candidates, key=lambda c: abs(c - scale))
    return f"DPI_{int(round(best * 100))}"


def detect_premiere_dpi_scale() -> float:
    """Find Premiere Pro's window, identify its monitor, and return that monitor's DPI scale.

    Falls back to the process-level DPI scale if Premiere is not found or the
    Win32 DPI APIs are unavailable.
    """
    try:
        import win32gui
        target_hwnd = None

        def _find_premiere(hwnd, _):
            nonlocal target_hwnd
            if win32gui.IsWindowVisible(hwnd) and "Adobe Premiere Pro" in win32gui.GetWindowText(hwnd):
                target_hwnd = hwnd

        win32gui.EnumWindows(_find_premiere, None)
        if target_hwnd:
            hmon = ctypes.windll.user32.MonitorFromWindow(target_hwnd, 2)  # MONITOR_DEFAULTTONEAREST
            dpi_x = ctypes.c_uint(0)
            dpi_y = ctypes.c_uint(0)
            ctypes.windll.shcore.GetDpiForMonitor(hmon, 0, ctypes.byref(dpi_x), ctypes.byref(dpi_y))
            if dpi_x.value > 0:
                scale = float(dpi_x.value) / 96.0
                print(f"[dpi] Premiere is on a {dpi_x.value} DPI monitor → scale {scale:.2f} ({_dpi_folder_name(scale)})")
                return scale
    except Exception as e:
        print(f"[dpi] Could not detect Premiere DPI: {e}")
    print(f"[dpi] Falling back to system DPI scale: {_DPI_SCALE:.2f}")
    return _DPI_SCALE


def get_premiere_dpi_scale() -> float:
    """Return Premiere's DPI scale, detecting and caching it on first call."""
    global _premiere_dpi_scale

    # Already detected this session
    if _premiere_dpi_scale is not None:
        return _premiere_dpi_scale

    # Try loading from the on-disk cache
    try:
        with open(_PREMIERE_DPI_FILE) as f:
            data = json.load(f)
        cached = float(data.get("scale", 0))
        if cached > 0:
            _premiere_dpi_scale = cached
            print(f"[dpi] Loaded cached Premiere DPI scale: {_premiere_dpi_scale:.2f}")
            return _premiere_dpi_scale
    except Exception:
        pass

    # Detect live and persist
    _premiere_dpi_scale = detect_premiere_dpi_scale()
    try:
        _PREMIERE_DPI_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(_PREMIERE_DPI_FILE, "w") as f:
            json.dump({"scale": round(_premiere_dpi_scale, 4)}, f)
    except Exception:
        pass
    return _premiere_dpi_scale


def invalidate_premiere_dpi_cache() -> None:
    """Force re-detection of Premiere's DPI on the next command (e.g. after moving the window)."""
    global _premiere_dpi_scale
    _premiere_dpi_scale = None
    try:
        _PREMIERE_DPI_FILE.unlink(missing_ok=True)
    except Exception:
        pass
    print("[dpi] Premiere DPI cache cleared — will re-detect on next image match.")


def _find_reference_path_for_scale(
    image_name: str,
    premiere_scale: float,
    subfolder: str | None = None,
) -> Path | None:
    """Look for a DPI-matched image using the in-memory index (O(1) lookup).

    Falls back to a filesystem rglob only if the index hasn't been built yet.
    """
    folder   = _dpi_folder_name(premiere_scale)
    spoken_key         = image_name.lower().replace(" ", "_")
    spoken_key_nospace = image_name.lower().replace(" ", "")

    if _dpi_folder_index:
        if subfolder:
            idx = _dpi_folder_index.get(folder, {}).get(subfolder.lower(), {})
        else:
            idx = {}
            for sub_idx in _dpi_folder_index.get(folder, {}).values():
                idx.update(sub_idx)
        return idx.get(spoken_key) or idx.get(spoken_key_nospace)

    # --- Fallback: index not built yet (first call before build_reference_index) ---
    if subfolder:
        search_root = Path(REFERENCE_DIR) / folder / subfolder
    else:
        search_root = Path(REFERENCE_DIR) / folder
    if not search_root.is_dir():
        return None
    image_exts = {".png", ".jpg", ".jpeg", ".bmp"}
    for path in search_root.rglob("*"):
        if path.suffix.lower() not in image_exts:
            continue
        file_key = path.stem.lower().replace(" ", "_")
        if file_key == spoken_key or file_key == spoken_key_nospace:
            return path
    return None


def _grab_screenshot() -> np.ndarray:
    """Capture the primary screen in BGR.

    Uses win32 GDI directly to guarantee physical-pixel capture regardless of
    how the Python process's DPI awareness was set before this module loaded.
    Falls back to pyautogui if win32 is unavailable.
    """
    try:
        import win32gui, win32ui, win32con
        hdc = win32gui.GetDC(0)
        dc = win32ui.CreateDCFromHandle(hdc)
        memdc = dc.CreateCompatibleDC()
        # GetSystemMetrics(SM_CXSCREEN/SM_CYSCREEN) returns physical pixels
        # when the process is DPI-aware.
        w = ctypes.windll.user32.GetSystemMetrics(0)  # SM_CXSCREEN
        h = ctypes.windll.user32.GetSystemMetrics(1)  # SM_CYSCREEN
        bmp = win32ui.CreateBitmap()
        bmp.CreateCompatibleBitmap(dc, w, h)
        memdc.SelectObject(bmp)
        memdc.BitBlt((0, 0), (w, h), dc, (0, 0), win32con.SRCCOPY)
        bmp_info = bmp.GetInfo()
        bmp_data = bmp.GetBitmapBits(True)
        img = np.frombuffer(bmp_data, dtype=np.uint8).reshape(
            bmp_info["bmHeight"], bmp_info["bmWidth"], 4
        )
        memdc.DeleteDC()
        win32gui.DeleteObject(bmp.GetHandle())
        win32gui.ReleaseDC(0, hdc)
        return cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)
    except Exception:
        screenshot = pyautogui.screenshot()
        return cv2.cvtColor(np.array(screenshot), cv2.COLOR_RGB2BGR)


def _exact_match(
    screen_bgr: np.ndarray,
    template: np.ndarray,
) -> tuple[float, tuple[int, int], int, int, np.ndarray, float]:
    """Single-pass match at scale 1.0 — used when the template is already DPI-matched.

    Runs exactly 2 matchTemplate calls (color + grayscale) instead of the
    11-step × 2-channel sweep in _multiscale_match.  Same return signature:
    (best_val, best_loc, best_w, best_h, template, best_scale).
    """
    base_h, base_w = template.shape[:2]
    screen_gray = cv2.cvtColor(screen_bgr, cv2.COLOR_BGR2GRAY)
    tmpl_gray   = cv2.cvtColor(template,   cv2.COLOR_BGR2GRAY)

    _, val_c, _, loc_c = cv2.minMaxLoc(
        cv2.matchTemplate(screen_bgr,  template,  cv2.TM_CCOEFF_NORMED))
    _, val_g, _, loc_g = cv2.minMaxLoc(
        cv2.matchTemplate(screen_gray, tmpl_gray, cv2.TM_CCOEFF_NORMED))

    if val_c >= val_g:
        return val_c, loc_c, base_w, base_h, template, 1.0
    return val_g, loc_g, base_w, base_h, template, 1.0


def _multiscale_match(
    screen_bgr: np.ndarray,
    template: np.ndarray,
    hint_scale: float | None = None,
):
    """Try scales in both color and grayscale; use cached hint when available.

    Strategy:
      1. If hint_scale is given (from the scale cache), try a tight band around
         it first.  If that scores ≥ 0.82 we return immediately — no full sweep.
      2. Otherwise do the full 0.4×–2.5× sweep so templates captured at any
         DPI are found on any device.

    Returns (best_val, best_loc, best_w, best_h, best_scaled_template, best_scale).
    The caller receives best_scale so it can persist it to the cache.
    """
    base_h, base_w = template.shape[:2]
    screen_h, screen_w = screen_bgr.shape[:2]
    best_val, best_loc, best_scale = 0.0, (0, 0), _DPI_SCALE

    screen_gray = cv2.cvtColor(screen_bgr, cv2.COLOR_BGR2GRAY)
    tmpl_gray   = cv2.cvtColor(template,   cv2.COLOR_BGR2GRAY)

    def _try(scales):
        nonlocal best_val, best_loc, best_scale
        for scale in scales:
            w = int(base_w * scale)
            h = int(base_h * scale)
            if w >= screen_w or h >= screen_h or w < 4 or h < 4:
                continue
            interp = cv2.INTER_AREA if scale < 1.0 else cv2.INTER_LINEAR
            scaled_c = cv2.resize(template,  (w, h), interpolation=interp)
            scaled_g = cv2.resize(tmpl_gray, (w, h), interpolation=interp)
            _, val_c, _, loc_c = cv2.minMaxLoc(
                cv2.matchTemplate(screen_bgr,  scaled_c, cv2.TM_CCOEFF_NORMED))
            _, val_g, _, loc_g = cv2.minMaxLoc(
                cv2.matchTemplate(screen_gray, scaled_g, cv2.TM_CCOEFF_NORMED))
            val, loc = (val_c, loc_c) if val_c >= val_g else (val_g, loc_g)
            if val > best_val:
                best_val, best_loc, best_scale = val, loc, scale

    # --- Pass 1: narrow search around cached hint (fast path) ---
    # Accept any match at or above MATCH_THRESHOLD (0.70) from the cached scale —
    # the old 0.82 guard was causing full sweeps on every call even after the
    # scale was learned, adding 2-3 seconds of extra matchTemplate work.
    if hint_scale is not None:
        _try(np.linspace(max(0.3, hint_scale - 0.15), hint_scale + 0.15, 11))
        if best_val >= 0.70:  # same as MATCH_THRESHOLD
            best_w = int(base_w * best_scale)
            best_h = int(base_h * best_scale)
            tmpl_out = cv2.resize(template, (best_w, best_h), interpolation=cv2.INTER_LINEAR)
            return best_val, best_loc, best_w, best_h, tmpl_out, best_scale

    # --- Pass 2: full wide search (first run on a new device) ---
    # Reduced from 30→18 coarse steps; fine search around native DPI fills gaps.
    coarse = np.linspace(0.4, 2.5, 18)
    fine   = np.linspace(max(0.4, _DPI_SCALE - 0.25), _DPI_SCALE + 0.25, 12)
    _try(np.unique(np.concatenate([coarse, fine])))

    best_w = int(base_w * best_scale)
    best_h = int(base_h * best_scale)
    tmpl_out = cv2.resize(template, (best_w, best_h), interpolation=cv2.INTER_LINEAR)
    return best_val, best_loc, best_w, best_h, tmpl_out, best_scale

REFERENCE_DIR = "ImageReference"
# Sub-folders that split images by behaviour:
#   Effects/ → drag-into-timeline flow (called by name only, no "click" prefix)
#   Click/   → click-and-hold-blue-number flow (called via "click <name>")
EFFECTS_SUBDIR = "Effects"
CLICK_SUBDIR   = "Click"
MATCH_THRESHOLD = 0.70  # Minimum confidence to accept a template match

# How far to the right of the template match we scan for the blue number (pixels).
# The Effect Controls panel can be any width, so we scan generously.  The noise
# filters (MIN_BLUE_AREA / MIN_BLUE_HEIGHT) keep false positives out.
BLUE_SCAN_WIDTH = 500

# Extra pixels added above and below the matched template row when scanning for
# blue numbers.  Accounts for sub-pixel shifts at non-native DPI scales.
BLUE_ROW_PADDING = 4

# Blue clusters smaller than this area (px²) or shorter than this height (px) are
# treated as noise / panel borders and ignored.  Editable number characters are
# typically ≥8 px tall; border highlights are usually 1-3 px.
MIN_BLUE_AREA   = 40
MIN_BLUE_HEIGHT = 6


def _find_reference_path(
    image_name: str,
    subfolder: str | None = None,
) -> Path | None:
    """Locate a reference image using the in-memory index (O(1) lookup).

    Falls back to a filesystem rglob only if the index hasn't been built yet.
    """
    spoken_key         = image_name.lower().replace(" ", "_")
    spoken_key_nospace = image_name.lower().replace(" ", "")

    if _base_index:
        if subfolder:
            idx = _base_index.get(subfolder.lower(), {})
        else:
            idx = {}
            for sub_idx in _base_index.values():
                idx.update(sub_idx)
        return idx.get(spoken_key) or idx.get(spoken_key_nospace)

    # --- Fallback: index not built yet ---
    if subfolder:
        ref_root = Path(REFERENCE_DIR) / subfolder
    else:
        ref_root = Path(REFERENCE_DIR)
    if not ref_root.is_dir():
        return None
    image_exts = {".png", ".jpg", ".jpeg", ".bmp"}
    for path in ref_root.rglob("*"):
        if path.suffix.lower() not in image_exts:
            continue
        file_key = path.stem.lower().replace(" ", "_")
        if file_key == spoken_key or file_key == spoken_key_nospace:
            return path
    return None


def has_effect_image(name: str) -> bool:
    """True if an image matching `name` exists in ImageReference/Effects/."""
    idx = _base_index.get(EFFECTS_SUBDIR.lower(), {})
    if idx:
        k = name.lower().replace(" ", "_")
        return k in idx or name.lower().replace(" ", "") in idx
    return _find_reference_path(name, subfolder=EFFECTS_SUBDIR) is not None


def has_click_image(name: str) -> bool:
    """True if an image matching `name` exists in ImageReference/Click/."""
    idx = _base_index.get(CLICK_SUBDIR.lower(), {})
    if idx:
        k = name.lower().replace(" ", "_")
        return k in idx or name.lower().replace(" ", "") in idx
    return _find_reference_path(name, subfolder=CLICK_SUBDIR) is not None


def find_on_screen(
    image_name: str,
    subfolder: str | None = None,
) -> tuple[int, int, int, int] | None:
    """Find a reference image on screen via template matching.

    DPI-aware search order:
      1. Position cache verify — 1 matchTemplate call on a small ROI (fast path).
      2. ImageReference/DPI_xxx/[subfolder]/ — pre-captured at Premiere's scale.
      3. ImageReference/[subfolder]/         — existing fallback with scale cache.

    Returns (x, y, w, h) of the best match in screen coordinates, or None if
    no match exceeds MATCH_THRESHOLD.
    """
    # Screenshot is taken first so the position cache verify can use it
    # without a second capture.
    screen_bgr = _grab_screenshot()

    # --- Fast path: position cache verify ---
    # After the first match, we remember the exact screen coordinates.
    # On repeated calls, crop a small ROI around the cached location and run
    # a single matchTemplate instead of the full 22-call multiscale sweep.
    # Cost: ~1 ms vs ~2800 ms.  Falls through if the image has moved / scrolled.
    if image_name in _position_cache:
        _cx, _cy, _cw, _ch, _cref, _cscale = _position_cache[image_name]
        _ctmpl_raw = cv2.imread(_cref)
        if _ctmpl_raw is not None and _cw > 0 and _ch > 0:
            _pad = 40
            _ry1 = max(0, _cy - _pad)
            _ry2 = min(screen_bgr.shape[0], _cy + _ch + _pad)
            _rx1 = max(0, _cx - _pad)
            _rx2 = min(screen_bgr.shape[1], _cx + _cw + _pad)
            _roi = screen_bgr[_ry1:_ry2, _rx1:_rx2]
            _ctmpl_s = cv2.resize(_ctmpl_raw, (_cw, _ch), interpolation=cv2.INTER_LINEAR)
            if _ctmpl_s.shape[0] <= _roi.shape[0] and _ctmpl_s.shape[1] <= _roi.shape[1]:
                _, _cv, _, _cl = cv2.minMaxLoc(
                    cv2.matchTemplate(_roi, _ctmpl_s, cv2.TM_CCOEFF_NORMED))
                if _cv >= MATCH_THRESHOLD:
                    _nx, _ny = _rx1 + _cl[0], _ry1 + _cl[1]
                    _position_cache[image_name] = (_nx, _ny, _cw, _ch, _cref, _cscale)
                    print(f"[image_matcher] Cache hit: '{image_name}' at ({_nx},{_ny}) conf={_cv:.2f}")
                    return (_nx, _ny, _cw, _ch)

    # --- Default ROI restriction ---
    # On the first call for a given image (no position cache entry yet), crop
    # the screen to the pre-defined panel region so the sweep runs on a small
    # fraction of the screen instead of the full 4K surface.
    # After a successful match the exact coordinates go into _position_cache,
    # so this block is bypassed on every subsequent call automatically.
    _roi_offset_x = _roi_offset_y = 0
    search_bgr = screen_bgr
    if _global_default_roi is not None:
        _drx1, _dry1, _drx2, _dry2 = _global_default_roi
        _drx1 = max(0, _drx1)
        _dry1 = max(0, _dry1)
        _drx2 = min(screen_bgr.shape[1], _drx2)
        _dry2 = min(screen_bgr.shape[0], _dry2)
        if _drx2 > _drx1 and _dry2 > _dry1:
            search_bgr = screen_bgr[_dry1:_dry2, _drx1:_drx2]
            _roi_offset_x, _roi_offset_y = _drx1, _dry1

    # --- DPI-specific lookup (full search) ---
    premiere_scale = get_premiere_dpi_scale()
    dpi_path = _find_reference_path_for_scale(image_name, premiere_scale, subfolder)
    if dpi_path:
        hint = 1.0
        source = "dpi"
        ref_path = dpi_path
    else:
        ref_path = _find_reference_path(image_name, subfolder=subfolder)
        hint = None
        source = "generic"

    if not ref_path:
        loc = f"{REFERENCE_DIR}/{subfolder}/" if subfolder else f"{REFERENCE_DIR}/"
        print(f"[image_matcher] No reference image found for '{image_name}' in {loc}")
        return None

    template = cv2.imread(str(ref_path))
    if template is None:
        print(f"[image_matcher] Could not read image: {ref_path}")
        return None

    # Track which ref path was actually used for the match (for position cache).
    _cache_ref = str(ref_path)

    if source == "dpi":
        # Before running _exact_match, check whether the scale cache already
        # recorded a scale that's far from 1.0 — if so, the DPI image was
        # generated at the wrong size and _exact_match will always fail.
        # Skip it to save ~245 ms on every call.
        base_path = _find_reference_path(image_name, subfolder=subfolder)
        _skip_exact = False
        if base_path:
            _cached_s = _scale_cache.get(_cache_key(base_path))
            if _cached_s is not None and abs(_cached_s - 1.0) > 0.05:
                _skip_exact = True

        max_val = 0.0
        if not _skip_exact:
            max_val, max_loc, w, h, _, found_scale = _exact_match(search_bgr, template)

        if max_val < MATCH_THRESHOLD:
            if base_path and base_path != ref_path:
                base_tmpl = cv2.imread(str(base_path))
                if base_tmpl is not None:
                    ckey = _cache_key(base_path)
                    hint = _scale_cache.get(ckey)
                    max_val, max_loc, w, h, _, found_scale = _multiscale_match(
                        search_bgr, base_tmpl, hint_scale=hint
                    )
                    if max_val >= MATCH_THRESHOLD:
                        _save_scale(ckey, found_scale)
                    source = "dpi_fallback"
                    _cache_ref = str(base_path)  # cache uses base image for future verify
    else:
        ckey = _cache_key(ref_path)
        hint_scale = _scale_cache.get(ckey)
        max_val, max_loc, w, h, _, found_scale = _multiscale_match(
            search_bgr, template, hint_scale=hint_scale
        )
        if max_val >= MATCH_THRESHOLD:
            _save_scale(ckey, found_scale)

    if max_val < MATCH_THRESHOLD:
        print(f"[image_matcher] '{image_name}' not found (best confidence: {max_val:.2f})")
        return None

    x, y = max_loc
    x += _roi_offset_x
    y += _roi_offset_y
    print(f"[image_matcher] Found '{image_name}' [{source}] at ({x}, {y}) size=({w}x{h}) confidence={max_val:.2f} scale={found_scale:.3f}")

    # Save position so the next call can verify with a fast ROI crop
    _position_cache[image_name] = (x, y, w, h, _cache_ref, found_scale)
    return (x, y, w, h)


def find_on_screen_from_path(
    image_path: str,
) -> tuple[int, int, int, int] | None:
    """Like find_on_screen but takes a direct file path instead of a name lookup.

    If the path lives inside a DPI_xxx subfolder that matches Premiere's detected
    scale, the match runs at hint_scale=1.0 (no interpolation needed).

    Returns (x, y, w, h) or None.
    """
    ref = Path(image_path)
    if not ref.exists():
        print(f"[image_matcher] Image file not found: {image_path}")
        return None

    premiere_scale = get_premiere_dpi_scale()
    expected_folder = _dpi_folder_name(premiere_scale)

    # If the stored path is in the base ImageReference folder (not already DPI-specific),
    # check whether a DPI-matched version was generated and prefer it for hint_scale=1.0.
    is_dpi_matched = False
    try:
        ref_root = Path(REFERENCE_DIR).resolve()
        rel = ref.resolve().relative_to(ref_root)
        if rel.parts[0].upper().startswith("DPI_"):
            # Already a DPI-specific path — check if it matches current scale
            is_dpi_matched = rel.parts[0].upper() == expected_folder.upper()
        else:
            # Base-folder path — look for a generated DPI version alongside it
            dpi_candidate = Path(REFERENCE_DIR) / expected_folder / rel
            if dpi_candidate.exists():
                ref = dpi_candidate
                is_dpi_matched = True
    except (ValueError, IndexError):
        # Path outside REFERENCE_DIR or no parts — fall back to old check
        path_parts = [p.lower() for p in ref.parts]
        is_dpi_matched = expected_folder.lower() in path_parts

    template = cv2.imread(str(ref))
    if template is None:
        print(f"[image_matcher] Could not read image: {ref}")
        return None

    screen_bgr = _grab_screenshot()

    if is_dpi_matched:
        max_val, max_loc, w, h, _, found_scale = _exact_match(screen_bgr, template)
    else:
        ckey = _cache_key(ref)
        hint_scale = _scale_cache.get(ckey)
        max_val, max_loc, w, h, _, found_scale = _multiscale_match(
            screen_bgr, template, hint_scale=hint_scale
        )

    if max_val < MATCH_THRESHOLD:
        print(f"[image_matcher] '{ref.stem}' not found via direct path (confidence: {max_val:.2f})")
        return None

    if not is_dpi_matched:
        ckey = _cache_key(ref)
        _save_scale(ckey, found_scale)
    x, y = max_loc
    source = "dpi" if is_dpi_matched else "generic"
    print(f"[image_matcher] Found '{ref.stem}' [{source}] at ({x}, {y}) size=({w}x{h}) confidence={max_val:.2f} scale={found_scale:.3f}")
    return (x, y, w, h)



def _find_blue_in_row(screen_bgr: np.ndarray, row_y: int, row_h: int,
                      scan_x: int, scan_w: int,
                      blue_index: int = 0) -> tuple[int, int] | None:
    """Scan a horizontal strip of the screen for a blue cluster by position order.

    Searches from scan_x rightward up to scan_w pixels wide.
    blue_index=0 returns the leftmost blue cluster (first number on the row),
    blue_index=1 returns the second-leftmost (e.g. Y when a row has X and Y).
    Returns absolute (screen_x, screen_y) of the cluster centroid, or None.
    """
    screen_h, screen_w = screen_bgr.shape[:2]

    # Clamp the search region to screen bounds
    x1 = max(0, scan_x)
    x2 = min(screen_w, scan_x + scan_w)
    y1 = max(0, row_y)
    y2 = min(screen_h, row_y + row_h)

    if x2 <= x1 or y2 <= y1:
        return None

    region = screen_bgr[y1:y2, x1:x2]

    hsv = cv2.cvtColor(region, cv2.COLOR_BGR2HSV)

    # Premiere Pro editable values use a bright blue around hue 205-220° RGB
    # → HSV hue 100-115 (OpenCV uses 0-180 scale)
    lower = np.array([95, 80, 80], dtype=np.uint8)
    upper = np.array([125, 255, 255], dtype=np.uint8)
    mask = cv2.inRange(hsv, lower, upper)

    if not mask.any():
        return None

    # Find connected blue clusters, sort left→right, pick the Nth one.
    num_labels, labels, stats, _ = cv2.connectedComponentsWithStats(mask)
    if num_labels < 2:  # 0 is background
        return None

    valid = sorted(
        (
            stats[i] for i in range(1, num_labels)
            if stats[i, cv2.CC_STAT_AREA]   >= MIN_BLUE_AREA
            and stats[i, cv2.CC_STAT_HEIGHT] >= MIN_BLUE_HEIGHT
        ),
        key=lambda s: s[cv2.CC_STAT_LEFT],
    )
    if not valid or blue_index >= len(valid):
        return None

    best = valid[blue_index]

    # Center of the chosen component in screen coordinates
    cx = x1 + best[cv2.CC_STAT_LEFT] + best[cv2.CC_STAT_WIDTH] // 2
    cy = y1 + best[cv2.CC_STAT_TOP] + best[cv2.CC_STAT_HEIGHT] // 2
    return (cx, cy)


def click_image(
    image_name: str,
    click_blue: bool = True,
    subfolder: str | None = None,
    blue_index: int = 0,
) -> tuple[bool, int, int]:
    """Find a reference image on screen, move to the blue value, and hold left mouse down.

    Strategy when click_blue=True:
      1. Template-match to get the row's Y position and height.
      2. Scan rightward from the right edge of the template across BLUE_SCAN_WIDTH
         pixels to find the Nth blue number on that row (blue_index=0 → leftmost/X,
         blue_index=1 → second/Y for two-value rows like Position and Anchor Point).
      3. Fall back to the center of the template if no blue is found.

    Args:
        image_name:  Spoken name to resolve to an image file.
        click_blue:  When True, click the blue value to the right of the label.
        subfolder:   Restrict the lookup to REFERENCE_DIR/<subfolder> if given.
        blue_index:  Which blue cluster to click (0=leftmost/X, 1=second/Y).

    The caller is responsible for releasing the button (e.g. via pyautogui.mouseUp).

    Returns:
        (success, click_x, click_y) — coordinates where the mouse was pressed,
        or (False, 0, 0) if the image was not found.
    """
    screen_bgr = _grab_screenshot()

    # DPI-specific lookup first
    premiere_scale = get_premiere_dpi_scale()
    dpi_path = _find_reference_path_for_scale(image_name, premiere_scale, subfolder)
    if dpi_path:
        ref_path = dpi_path
        hint_scale = 1.0
        source = "dpi"
    else:
        ref_path = _find_reference_path(image_name, subfolder=subfolder)
        hint_scale = None
        source = "generic"

    if not ref_path:
        loc = f"{REFERENCE_DIR}/{subfolder}/" if subfolder else f"{REFERENCE_DIR}/"
        print(f"[image_matcher] No reference image found for '{image_name}' in {loc}")
        return False, 0, 0

    template = cv2.imread(str(ref_path))
    if template is None:
        print(f"[image_matcher] Could not read image: {ref_path}")
        return False, 0, 0

    if source == "dpi":
        max_val, max_loc, tw, th, _, found_scale = _exact_match(screen_bgr, template)
        if max_val < MATCH_THRESHOLD:
            base_path = _find_reference_path(image_name, subfolder=subfolder)
            if base_path and base_path != ref_path:
                base_tmpl = cv2.imread(str(base_path))
                if base_tmpl is not None:
                    ckey = _cache_key(base_path)
                    hint = _scale_cache.get(ckey)
                    max_val, max_loc, tw, th, _, found_scale = _multiscale_match(
                        screen_bgr, base_tmpl, hint_scale=hint
                    )
                    if max_val >= MATCH_THRESHOLD:
                        _save_scale(ckey, found_scale)
                    source = "dpi_fallback"
    else:
        ckey = _cache_key(ref_path)
        hint_scale = _scale_cache.get(ckey)
        max_val, max_loc, tw, th, _, found_scale = _multiscale_match(
            screen_bgr, template, hint_scale=hint_scale
        )
        if max_val >= MATCH_THRESHOLD:
            ckey = _cache_key(ref_path)
            _save_scale(ckey, found_scale)

    if max_val < MATCH_THRESHOLD:
        print(f"[image_matcher] '{image_name}' not found (best confidence: {max_val:.2f})")
        return False, 0, 0
    match_x, match_y = max_loc
    print(f"[image_matcher] Found '{image_name}' [{source}] at ({match_x}, {match_y}) confidence={max_val:.2f} scale={found_scale:.3f}")

    # Default click target: center of the matched template
    click_x, click_y = match_x + tw // 2, match_y + th // 2

    if click_blue:
        # Scan starting from the centre of the template so narrow labels don't
        # push the search window past the value field.  BLUE_ROW_PADDING expands
        # the row vertically to catch numbers at sub-pixel DPI offsets.
        blue_pos = _find_blue_in_row(
            screen_bgr,
            row_y=match_y - BLUE_ROW_PADDING,
            row_h=th + BLUE_ROW_PADDING * 2,
            scan_x=match_x + tw // 2,
            scan_w=BLUE_SCAN_WIDTH,
            blue_index=blue_index,
        )

        if blue_pos:
            click_x, click_y = blue_pos
            print(f"[image_matcher] Blue number found at ({click_x}, {click_y})")
        else:
            print("[image_matcher] No blue number found to the right — clicking template center")

    pyautogui.moveTo(click_x, click_y)
    pyautogui.mouseDown(button="left")
    return True, click_x, click_y


_DPI_GEN_META_FILE = Path("ImageReference") / ".dpi_gen_meta.json"


def _detect_capture_scale() -> float:
    """Estimate the DPI scale at which reference images were originally captured.

    Reads scale_cache entries for base (non-DPI-folder) images and computes:
        capture_scale = system_dpi_at_cache_time / match_scale_at_cache_time

    Returns the median estimate, or 1.0 if the cache is empty.
    """
    estimates: list[float] = []
    for key, match_scale in _scale_cache.items():
        try:
            dpi_str, path_str = key.split(":", 1)
            # Skip DPI-folder entries (they aren't base captures)
            if "/DPI_" in path_str or "\\DPI_" in path_str:
                continue
            if match_scale <= 0:
                continue
            cached_dpi_scale = float(dpi_str) / 96.0
            estimates.append(cached_dpi_scale / match_scale)
        except (ValueError, ZeroDivisionError):
            continue

    if not estimates:
        return 1.0

    estimates.sort()
    mid = len(estimates) // 2
    return estimates[mid] if len(estimates) % 2 else (estimates[mid - 1] + estimates[mid]) / 2


def generate_dpi_versions(capture_scale: float | None = None, force: bool = False) -> None:
    """Generate pre-scaled DPI copies for every image in Effects/ and Click/.

    Called automatically at startup.  Scans both subfolders and writes a scaled
    copy into ImageReference/DPI_xxx/<subfolder>/ for each of the six standard
    DPI tiers.  Existing files are skipped unless force=True, so subsequent
    startups are nearly instant (just a filesystem stat per file).

    Args:
        capture_scale: DPI scale at which the source images were captured.
                       Auto-detected from scale_cache if not provided.
        force:         Re-generate even if the file already exists.
    """
    if capture_scale is None:
        capture_scale = _detect_capture_scale()
        print(f"[dpi_gen] Detected capture scale: {capture_scale:.4f}")

    # If the capture_scale changed since last generation, force a full rebuild.
    try:
        with open(_DPI_GEN_META_FILE) as f:
            meta = json.load(f)
        stored = float(meta.get("capture_scale", 0))
        if stored > 0 and abs(stored - capture_scale) > 0.01:
            print(f"[dpi_gen] Capture scale changed ({stored:.4f} → {capture_scale:.4f}) — rebuilding DPI images.")
            force = True
    except Exception:
        force = True  # No metadata yet — generate everything

    DPI_TIERS = {
        "DPI_100": 1.00,
        "DPI_125": 1.25,
        "DPI_150": 1.50,
        "DPI_175": 1.75,
        "DPI_200": 2.00,
        "DPI_225": 2.25,
    }

    source_subdirs = [EFFECTS_SUBDIR, CLICK_SUBDIR]
    image_exts = {".png", ".jpg", ".jpeg", ".bmp"}

    generated = 0
    skipped   = 0
    errors    = 0

    for subdir in source_subdirs:
        src_root = Path(REFERENCE_DIR) / subdir
        if not src_root.is_dir():
            continue

        for src_path in sorted(src_root.rglob("*")):
            if src_path.suffix.lower() not in image_exts:
                continue

            # Relative path inside REFERENCE_DIR, e.g. "Effects/Amplify.png"
            rel = src_path.relative_to(Path(REFERENCE_DIR))

            template = None  # lazy-load: only read once if any tier is missing

            for folder_name, target_scale in DPI_TIERS.items():
                dst_path = Path(REFERENCE_DIR) / folder_name / rel

                if dst_path.exists() and not force:
                    skipped += 1
                    continue

                # Load source image on first tier that needs it
                if template is None:
                    template = cv2.imread(str(src_path))
                    if template is None:
                        print(f"[dpi_gen] Cannot read: {src_path}")
                        errors += 1
                        break  # skip all tiers for this file

                factor = target_scale / capture_scale
                h, w   = template.shape[:2]
                new_w  = max(1, int(round(w * factor)))
                new_h  = max(1, int(round(h * factor)))

                interp = cv2.INTER_AREA if factor < 1.0 else cv2.INTER_LANCZOS4
                scaled = cv2.resize(template, (new_w, new_h), interpolation=interp)

                dst_path.parent.mkdir(parents=True, exist_ok=True)
                cv2.imwrite(str(dst_path), scaled)
                generated += 1

    print(f"[dpi_gen] Done — generated: {generated}, skipped (exist): {skipped}, errors: {errors}")

    # Persist metadata so future startups know which capture_scale was used.
    try:
        _DPI_GEN_META_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(_DPI_GEN_META_FILE, "w") as f:
            json.dump({"capture_scale": round(capture_scale, 4)}, f)
    except Exception:
        pass


def build_reference_index() -> None:
    """Build in-memory O(1) lookup indices for base and DPI reference images.

    Call this after generate_dpi_versions() at startup, and again whenever
    new images are added to Effects/ or Click/ during a session.

    Duplicate name resolution: both "Iris Box.png" and "Iris_Box.png" normalise
    to "iris_box".  sorted() iteration means the underscore variant is processed
    last and overwrites the space variant — canonical names always win.
    """
    global _base_index, _dpi_folder_index
    image_exts = {".png", ".jpg", ".jpeg", ".bmp"}

    def _scan(root: Path) -> dict[str, Path]:
        idx: dict[str, Path] = {}
        for p in sorted(root.rglob("*")):  # sorted → underscore wins over space
            if p.suffix.lower() not in image_exts:
                continue
            key_u = p.stem.lower().replace(" ", "_")
            key_n = p.stem.lower().replace(" ", "")
            idx[key_u] = p
            if key_n != key_u:
                idx[key_n] = p
        return idx

    # Base folders (Effects/, Click/)
    _base_index = {}
    for subdir in (EFFECTS_SUBDIR, CLICK_SUBDIR):
        root = Path(REFERENCE_DIR) / subdir
        if root.is_dir():
            _base_index[subdir.lower()] = _scan(root)

    # DPI folders (DPI_xxx/Effects/, DPI_xxx/Click/)
    _dpi_folder_index = {}
    for folder in _DPI_SCALE_FOLDERS:
        folder_root = Path(REFERENCE_DIR) / folder
        if not folder_root.is_dir():
            continue
        folder_idx: dict[str, dict[str, Path]] = {}
        for subdir in (EFFECTS_SUBDIR, CLICK_SUBDIR):
            sub_root = folder_root / subdir
            if sub_root.is_dir():
                folder_idx[subdir.lower()] = _scan(sub_root)
        if folder_idx:
            _dpi_folder_index[folder] = folder_idx

    base_counts = {k: len(v) for k, v in _base_index.items()}
    dpi_counts  = {f: sum(len(v) for v in d.values()) for f, d in _dpi_folder_index.items()}
    print(f"[index] Built — base: {base_counts}, DPI folders: {dpi_counts}")


def list_references() -> list[str]:
    """Return all available reference image names (without extension), searching recursively."""
    ref_root = Path(REFERENCE_DIR)
    if not ref_root.is_dir():
        return []
    image_exts = {".png", ".jpg", ".jpeg", ".bmp"}
    return [
        p.stem.replace("_", " ").lower()
        for p in ref_root.rglob("*")
        if p.suffix.lower() in image_exts
    ]


def list_references_by_type() -> tuple[set[str], set[str]]:
    """Return (click_names, effect_names) split by subfolder.

    Images under ImageReference/Click/   → click_names  (use click_image)
    Images under ImageReference/Effects/ → effect_names (use _effects_search)
    Images at the root level             → click_names  (default)
    """
    ref_root = Path(REFERENCE_DIR)
    if not ref_root.is_dir():
        return set(), set()

    image_exts = {".png", ".jpg", ".jpeg", ".bmp"}
    click_names: set[str] = set()
    effect_names: set[str] = set()

    for p in ref_root.rglob("*"):
        if p.suffix.lower() not in image_exts:
            continue
        name = p.stem.replace("_", " ").lower()
        parts_lower = [part.lower() for part in p.relative_to(ref_root).parts]
        if any(part == "effects" for part in parts_lower[:-1]):
            effect_names.add(name)
        else:
            click_names.add(name)

    return click_names, effect_names
