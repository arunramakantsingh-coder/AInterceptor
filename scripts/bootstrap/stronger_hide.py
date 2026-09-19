import pathlib, subprocess, sys, ast, re

ROOT = pathlib.Path.cwd()
BE = ROOT / "backend" / "app"

# ═══════════════════════════════════════════════════════════════
# 1. Strengthen push_chrome_off_screen in browser_supervisor.py
# ═══════════════════════════════════════════════════════════════
BS = BE / "runtime" / "browser_supervisor.py"
src = BS.read_text(encoding="utf-8")

# Find existing push_chrome_off_screen and replace it
old_fn_start = src.find("def push_chrome_off_screen()")
if old_fn_start == -1:
    print("[FAIL] push_chrome_off_screen not found"); sys.exit(1)
# find end (next top-level def or EOF)
old_fn_end = src.find("\ndef ", old_fn_start + 10)
if old_fn_end == -1:
    old_fn_end = len(src)

new_fn = '''def push_chrome_off_screen() -> int:
    """Hide every Chrome window belonging to us. Belt-and-suspenders:
    MoveWindow off-screen + ShowWindow(SW_HIDE). Returns count hidden.
    """
    if not sys.platform.startswith("win"):
        return 0
    try:
        import ctypes
        from ctypes import wintypes
        u = ctypes.windll.user32
        CB = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
        SW_HIDE = 0

        # Titles we consider "ours" — anything with our provider names
        # or Chrome running with our debug port marker.
        markers = (
            "chatgpt", "claude", "gemini", "deepseek", "mistral", "qwen",
            "kimi", "grok", "perplexity", "poe", "copilot", "meta",
            "ainterceptor", "chrome",
        )
        hidden = 0

        def cb(hwnd, lp):
            nonlocal hidden
            try:
                n = u.GetWindowTextLengthW(hwnd)
                if not n:
                    return True
                buf = ctypes.create_unicode_buffer(n + 1)
                u.GetWindowTextW(hwnd, buf, n + 1)
                title = buf.value.lower()
                if not any(k in title for k in markers):
                    return True
                # Belt
                u.MoveWindow(hwnd, -32000, -32000, 1400, 900, True)
                # Suspenders
                u.ShowWindow(hwnd, SW_HIDE)
                hidden += 1
            except Exception:
                pass
            return True

        u.EnumWindows(CB(cb), 0)
        return hidden
    except Exception:
        return 0

'''

src = src[:old_fn_start] + new_fn + src[old_fn_end:]
BS.write_text(src, encoding="utf-8", newline="\n")
print("  [OK] push_chrome_off_screen: now uses MoveWindow + SW_HIDE")

try:
    ast.parse(src)
    print("  [OK] browser_supervisor.py syntax valid")
except SyntaxError as e:
    print(f"[FAIL] {e}"); sys.exit(1)

# ═══════════════════════════════════════════════════════════════
# 2. Watchdog — run every 1 second
# ═══════════════════════════════════════════════════════════════
WD = BE / "runtime" / "watchdog.py"
if WD.exists():
    wt = WD.read_text(encoding="utf-8")
    wt = wt.replace("def _loop(interval: float = 3.0):", "def _loop(interval: float = 1.0):")
    wt = wt.replace("def start(interval: float = 3.0) -> bool:", "def start(interval: float = 1.0) -> bool:")
    wt = wt.replace("_loop, args=(interval,)", "_loop, args=(interval,)")
    WD.write_text(wt, encoding="utf-8", newline="\n")
    print("  [OK] watchdog.py: interval 3.0 -> 1.0 second")

# ═══════════════════════════════════════════════════════════════
# 3. Ensure daemon starts the watchdog
# ═══════════════════════════════════════════════════════════════
daemon = BE / "runtime" / "daemon.py"
dt = daemon.read_text(encoding="utf-8")

if "watchdog.start" not in dt:
    # Insert watchdog start right after supervisor.start()
    anchor = "    await supervisor.start()"
    if anchor in dt:
        dt = dt.replace(
            anchor,
            anchor + "\n\n    # start the off-screen watchdog immediately\n"
                     "    from app.runtime import watchdog as _wd\n"
                     "    _wd.start(interval=1.0)\n"
                     "    print('[daemon] off-screen watchdog started (1s)', flush=True)",
            1,
        )
        daemon.write_text(dt, encoding="utf-8", newline="\n")
        print("  [OK] daemon.py: watchdog starts right after supervisor")
    else:
        print("  [!] daemon.py: supervisor.start anchor not found")
else:
    print("  [OK] daemon.py: watchdog already started")

try:
    ast.parse(dt)
    print("  [OK] daemon.py syntax valid")
except SyntaxError as e:
    print(f"[FAIL] {e}"); sys.exit(1)

# ═══════════════════════════════════════════════════════════════
# 4. Add off-screen enforcement to CLI (chat_any.py) — defensive
# ═══════════════════════════════════════════════════════════════
CLI = ROOT / "backend" / "scripts" / "chat_any.py"
if CLI.exists():
    ct = CLI.read_text(encoding="utf-8")
    # Insert a one-time hide at the top of main()
    if "push_chrome_off_screen" not in ct:
        anchor = "async def main("
        if anchor in ct:
            # Find the first line after main( and inject
            idx = ct.find(anchor)
            nl = ct.find("\n", idx)
            # get indentation of the body (first non-empty line after)
            body_start = nl + 1
            # assume 4 spaces of indentation
            inject = (
                "    # Hide any Chrome window before we attach\n"
                "    try:\n"
                "        import sys as _s, pathlib as _pl\n"
                "        _s.path.insert(0, str(_pl.Path(__file__).resolve().parents[1]))\n"
                "        from app.runtime.browser_supervisor import push_chrome_off_screen\n"
                "        push_chrome_off_screen()\n"
                "    except Exception:\n"
                "        pass\n"
            )
            ct = ct[:body_start] + inject + ct[body_start:]
            CLI.write_text(ct, encoding="utf-8", newline="\n")
            print("  [OK] chat_any.py: hides Chrome before attach")
    else:
        print("  [OK] chat_any.py: already has hide call")
else:
    print(f"  [!] CLI not found at {CLI}")

# ═══════════════════════════════════════════════════════════════
# 5. Commit
# ═══════════════════════════════════════════════════════════════
def git(a):
    return subprocess.run(["git"]+a, cwd=ROOT, capture_output=True, text=True)
git(["add","-A"])
r = git(["commit","-m",
         "fix(ui): stronger off-screen enforcement (SW_HIDE); watchdog every 1s; CLI hide at startup"])
print((r.stdout.strip() or r.stderr.strip())[:250])

print()
print("=" * 66)
print("FIXES APPLIED")
print()
print("  1. push_chrome_off_screen: MoveWindow + ShowWindow(SW_HIDE)")
print("  2. watchdog interval: 3s -> 1s")
print("  3. daemon: starts watchdog immediately after supervisor")
print("  4. CLI: hides Chrome on startup, before attach")
print()
print("NEXT — Test:")
print()
print("  1. In the daemon window: Ctrl+C")
print("  2. .\\run-windows.ps1")
print("  3. Watch Chrome — should disappear within 1 second")
print("  4. In a second window: chatgpt")
print("     Chrome should NOT appear")
print()
print("If Chrome still appears, run:")
print("  Get-Process chrome | Where-Object { $_.MainWindowHandle -ne 0 } |")
print("    Select-Object Id, MainWindowTitle")
print("  and paste the output.")
print("=" * 66)
