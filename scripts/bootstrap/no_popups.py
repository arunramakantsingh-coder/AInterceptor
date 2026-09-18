import pathlib, subprocess, sys

ROOT = pathlib.Path.cwd()
BE = ROOT / "backend" / "app"

# ═══════════════════════════════════════════════════════════════
# 1. Remove bring_to_front from path_b.py
# ═══════════════════════════════════════════════════════════════
pb = BE / "runtime" / "path_b.py"
src = pb.read_text(encoding="utf-8")

before = src
src = src.replace("            await page.bring_to_front()\n", "")
src = src.replace("        await page.bring_to_front()\n", "")
src = src.replace("    await page.bring_to_front()\n", "")
src = src.replace("await page.bring_to_front()", "")

if src != before:
    print("  [OK] removed bring_to_front calls")
else:
    print("  [i] no bring_to_front found")

pb.write_text(src, encoding="utf-8", newline="\n")

import ast
try:
    ast.parse(src)
except SyntaxError as e:
    print(f"  [FAIL] syntax: {e}"); sys.exit(1)
print("  [OK] path_b.py syntax valid")

# ═══════════════════════════════════════════════════════════════
# 2. Watchdog — pushes Chrome windows off-screen every 3 s
# ═══════════════════════════════════════════════════════════════
watchdog = '''"""Chrome window watchdog.

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
'''

(BE / "runtime" / "watchdog.py").write_text(watchdog, encoding="utf-8", newline="\n")
print("  [OK] backend/app/runtime/watchdog.py")

# ═══════════════════════════════════════════════════════════════
# 3. Wire watchdog into FastAPI startup
# ═══════════════════════════════════════════════════════════════
main = BE / "main.py"
txt = main.read_text(encoding="utf-8")

if "watchdog" not in txt:
    txt = txt.replace(
        'app = FastAPI(title="AInterceptor", version="0.1.0")',
        'app = FastAPI(title="AInterceptor", version="0.1.0")\n\n'
        '@app.on_event("startup")\n'
        'def _start_watchdog():\n'
        '    from app.runtime import watchdog\n'
        '    watchdog.start()'
    )
    main.write_text(txt, encoding="utf-8", newline="\n")
    print("  [OK] main.py: watchdog starts on API startup")

# ═══════════════════════════════════════════════════════════════
# 4. Commit
# ═══════════════════════════════════════════════════════════════
def git(a):
    return subprocess.run(["git"]+a, cwd=ROOT, capture_output=True, text=True)
git(["add","-A"])
r = git(["commit","-m","fix(ui): no Chrome popups — remove bring_to_front; add 3s off-screen watchdog"])
print((r.stdout.strip() or r.stderr.strip())[:300])

print()
print("=" * 66)
print("NEXT — restart API to load the watchdog:")
print()
print("  1. In the uvicorn window: Ctrl+C")
print("  2. Bring all Chromes back on-screen once, then off-screen:")
print("       $sig = @'")
print("       using System;")
print("       using System.Runtime.InteropServices;")
print("       public class W {")
print("         [DllImport(\\\"user32.dll\\\")] public static extern bool MoveWindow(IntPtr h,int x,int y,int w,int t,bool r);")
print("       }")
print("       '@")
print("       Add-Type $sig")
print("       Get-Process chrome | ForEach-Object {")
print("         [W]::MoveWindow($_.MainWindowHandle, -32000, -32000, 1400, 900, $true) | Out-Null")
print("       }")
print("  3. Start API again:")
print("       .\\run-windows.ps1")
print()
print("  4. Watchdog will keep them off-screen from that point on.")
print("=" * 66)
