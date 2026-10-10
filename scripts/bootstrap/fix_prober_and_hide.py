import pathlib, subprocess, sys, ast, re

ROOT = pathlib.Path.cwd()
BE = ROOT / "backend" / "app"

# ═══════════════════════════════════════════════════════════════
# 1. Force prober OFF in .env.windows
# ═══════════════════════════════════════════════════════════════
env = ROOT / ".env.windows"
txt = env.read_text(encoding="utf-8")
# Ensure the flag is 0
if "AINTERCEPTOR_PROBER_ENABLED" in txt:
    txt = re.sub(r"^AINTERCEPTOR_PROBER_ENABLED=.*$",
                 "AINTERCEPTOR_PROBER_ENABLED=0",
                 txt, flags=re.M)
else:
    txt = txt.rstrip() + "\nAINTERCEPTOR_PROBER_ENABLED=0\n"
env.write_text(txt, encoding="utf-8", newline="\n")
print("  [OK] .env.windows: AINTERCEPTOR_PROBER_ENABLED=0")

# ═══════════════════════════════════════════════════════════════
# 2. Hard-disable the prober in the daemon — belt and suspenders
# ═══════════════════════════════════════════════════════════════
daemon = BE / "runtime" / "daemon.py"
dt = daemon.read_text(encoding="utf-8")

# Find the prober block and neutralise it
old_probe = re.search(
    r"(\n\s*prober\s*=\s*HealthProber\(.*?\)\s*\n"
    r"(?:\s*\S.*\n)*?)"
    r"(\s*if prober is not None:\s*\n\s*prober\.start\(\)\s*\n\s*sr\.set_prober\(prober\)\s*\n\s*print\(\"\[daemon\] prober started\", flush=True\)\s*\n)",
    dt, re.S
)

if old_probe:
    replacement = (
        "\n    # PROBER DISABLED — it writes ping/pong into real provider chats.\n"
        "    # Re-enable only after implementing a non-invasive probe.\n"
        "    prober = None\n"
        "    print('[daemon] prober disabled (invasive — sends real chat messages)', flush=True)\n"
    )
    dt = dt[:old_probe.start()] + replacement + dt[old_probe.end():]
    daemon.write_text(dt, encoding="utf-8", newline="\n")
    print("  [OK] daemon.py: prober block neutralised")
else:
    # Fallback: check for the older pattern
    if "prober.start()" in dt:
        # crude: comment out
        dt = dt.replace("prober.start()", "pass  # prober.start() disabled")
        dt = dt.replace("sr.set_prober(prober)", "pass  # sr.set_prober(prober) disabled")
        daemon.write_text(dt, encoding="utf-8", newline="\n")
        print("  [OK] daemon.py: prober.start() commented out (fallback)")
    else:
        print("  [i] daemon.py: prober already disabled")

try:
    ast.parse(dt)
    print("  [OK] daemon.py syntax valid")
except SyntaxError as e:
    print(f"[FAIL] daemon.py: {e}"); sys.exit(1)

# ═══════════════════════════════════════════════════════════════
# 3. Narrow the off-screen enforcement — only OUR Chrome windows
# ═══════════════════════════════════════════════════════════════
BS = BE / "runtime" / "browser_supervisor.py"
src = BS.read_text(encoding="utf-8")

old_fn_start = src.find("def push_chrome_off_screen()")
if old_fn_start == -1:
    print("[FAIL] push_chrome_off_screen not found"); sys.exit(1)
old_fn_end = src.find("\ndef ", old_fn_start + 10)
if old_fn_end == -1:
    old_fn_end = len(src)

new_fn = '''def _our_chrome_pids() -> set[int]:
    """Return the PIDs of Chrome processes launched with OUR profile path.
    This deliberately does NOT match the user's normal Chrome windows.
    """
    if not sys.platform.startswith("win"):
        return set()
    try:
        r = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             "Get-CimInstance Win32_Process -Filter \\"Name='chrome.exe'\\" | "
             "Where-Object { $_.CommandLine -like '*ainterceptor*' -or "
             "$_.CommandLine -like '*chrome-profile*' -or "
             "$_.CommandLine -like '*remote-debugging-port=9222*' } | "
             "Select-Object -ExpandProperty ProcessId"],
            capture_output=True, text=True, timeout=8,
        )
        pids = set()
        for ln in (r.stdout or "").splitlines():
            ln = ln.strip()
            if ln.isdigit():
                pids.add(int(ln))
        return pids
    except Exception:
        return set()


def push_chrome_off_screen() -> int:
    """Hide only Chrome windows that belong to our supervised profile.

    Never touches the user's regular Chrome windows. Match is done via
    window->PID mapping, not window title.
    """
    if not sys.platform.startswith("win"):
        return 0

    pids = _our_chrome_pids()
    if not pids:
        return 0

    try:
        import ctypes
        from ctypes import wintypes
        u = ctypes.windll.user32
        CB = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
        SW_HIDE = 0
        hidden = 0

        def cb(hwnd, lp):
            nonlocal hidden
            try:
                # Get the PID that owns this window
                pid = wintypes.DWORD()
                u.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
                if pid.value not in pids:
                    return True
                if not u.IsWindowVisible(hwnd):
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
print("  [OK] push_chrome_off_screen: now matches by PID, not title")

try:
    ast.parse(src)
    print("  [OK] browser_supervisor.py syntax valid")
except SyntaxError as e:
    print(f"[FAIL] browser_supervisor.py: {e}")
    lines = src.splitlines()
    for i in range(max(0, e.lineno - 5), min(len(lines), e.lineno + 3)):
        m = ">>>" if i + 1 == e.lineno else "   "
        print(f"  {m} {i+1:4d}  {lines[i]}")
    sys.exit(1)

# ═══════════════════════════════════════════════════════════════
# 4. Commit
# ═══════════════════════════════════════════════════════════════
def git(a):
    return subprocess.run(["git"]+a, cwd=ROOT, capture_output=True, text=True)
git(["add","-A"])
r = git(["commit","-m",
         "fix(daemon): disable invasive prober; hide Chrome by PID, never by title"])
print((r.stdout.strip() or r.stderr.strip())[:250])

print()
print("=" * 66)
print("FIXES APPLIED")
print()
print("  1. Prober disabled via env flag + hard-coded daemon override")
print("     → will no longer write 'ping/pong' into your real chats")
print()
print("  2. push_chrome_off_screen now matches Chrome by PID")
print("     → will hide ONLY Chrome launched with our profile")
print("     → will NEVER hide your personal Chrome")
print()
print("NEXT:")
print()
print("  1. Ctrl+C in the daemon window")
print("  2. .\\run-windows.ps1")
print("  3. Look for: [daemon] prober disabled (invasive — sends real chat messages)")
print("  4. Open a normal Chrome window (your personal one). It should stay visible.")
print("  5. Open a second window, run: chatgpt")
print("  6. Your personal Chrome should NOT disappear.")
print("=" * 66)
