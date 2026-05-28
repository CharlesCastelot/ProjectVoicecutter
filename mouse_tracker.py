# ABOUTME: Global mouse-click tracker — records the last position where the
# user clicked so _effects_search() can drag effects to that spot.
import contextlib
import threading
from pynput import mouse

_last_click: tuple[int, int] = (0, 0)
_lock = threading.Lock()
_listener: mouse.Listener | None = None
_suppressed: bool = False   # when True, programmatic clicks are ignored


def _on_click(x: int, y: int, button: mouse.Button, pressed: bool) -> None:
    """Called by pynput on every mouse press/release anywhere on the screen."""
    if pressed:  # only record the down-press, not the release
        global _last_click
        with _lock:
            if not _suppressed:
                _last_click = (int(x), int(y))


@contextlib.contextmanager
def suppress_clicks():
    """Context manager — clicks recorded by pynput are ignored inside this block.

    Use this to wrap any programmatic mouse operations (pyautogui drags, etc.)
    so Jarvis's own clicks don't overwrite the user's last-click position.
    """
    global _suppressed
    with _lock:
        _suppressed = True
    try:
        yield
    finally:
        with _lock:
            _suppressed = False


def start() -> None:
    """Start the background listener (call once at app startup)."""
    global _listener
    if _listener is not None:
        return  # already running
    _listener = mouse.Listener(on_click=_on_click)
    _listener.daemon = True
    _listener.start()


def get_last_click() -> tuple[int, int]:
    """Return the (x, y) of the most recent mouse click."""
    with _lock:
        return _last_click
