"""Off-screen watchdog.

Every 3s, if any Chrome window is visible, push it back off-screen.
Runs as a daemon thread started by the FastAPI startup hook.
"""
from __future__ import annotations
import os
import sys
import threading
import time


_started = False
_stop = threading.Event()


def _tick():
    from app.runtime.browser_supervisor import push_chrome_off_screen
    try:
        n = push_chrome_off_screen()
        return n
    except Exception:
        return 0


def _loop(interval: float = 3.0):
    while not _stop.is_set():
        _tick()
        _stop.wait(interval)


def start(interval: float = 3.0) -> bool:
    """Start the watchdog thread. Idempotent. No-op on non-Windows."""
    global _started
    if _started:
        return False
    if not sys.platform.startswith("win"):
        return False
    _started = True
    t = threading.Thread(target=_loop, args=(interval,),
                         daemon=True, name="offscreen-watchdog")
    t.start()
    print(f"[watchdog] off-screen enforcement active (every {interval}s)", flush=True)
    return True


def stop() -> None:
    _stop.set()
