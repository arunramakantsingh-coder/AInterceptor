"""Chrome window watchdog.

While the API runs, this thread periodically moves every Chrome window
off-screen so the user never sees a browser pop up during chat.

Windows-only. No-op on other platforms.
"""
from __future__ import annotations
import os, sys, threading, time


CHROME_TITLES = ("claude", "chatgpt", "gemini", "deepseek", "chrome")


def _off_screen_windows():
    if not sys.platform.startswith("win"):
        return
    import ctypes
    from ctypes import wintypes
    u = ctypes.windll.user32

    WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)

    def cb(hwnd, lp):
        try:
            n = u.GetWindowTextLengthW(hwnd)
            if not n:
                return True
            buf = ctypes.create_unicode_buffer(n + 1)
            u.GetWindowTextW(hwnd, buf, n + 1)
            title = buf.value.lower()
            if not any(k in title for k in CHROME_TITLES):
                return True
            # Only hide if window is currently visible
            if not u.IsWindowVisible(hwnd):
                return True
            u.MoveWindow(hwnd, -32000, -32000, 1400, 900, True)
        except Exception:
            pass
        return True

    u.EnumWindows(WNDENUMPROC(cb), 0)


def _loop(interval: float = 3.0):
    while True:
        try:
            _off_screen_windows()
        except Exception:
            pass
        time.sleep(interval)


_started = False


def start():
    """Start the watchdog thread (idempotent)."""
    global _started
    if _started:
        return
    if not sys.platform.startswith("win"):
        return
    _started = True
    t = threading.Thread(target=_loop, daemon=True, name="chrome-watchdog")
    t.start()
    print("[watchdog] Chrome window watchdog active (3s interval)", flush=True)
