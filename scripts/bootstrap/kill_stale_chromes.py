import pathlib, subprocess, sys, ast

ROOT = pathlib.Path.cwd()
BS = ROOT / "backend" / "app" / "runtime" / "browser_supervisor.py"
src = BS.read_text(encoding="utf-8")

# ── 1. Add a kill-our-chromes helper ──
if "_kill_our_chromes" not in src:
    helper = '''

def _kill_our_chromes() -> int:
    """Kill any Chrome process whose command line contains our profile marker.
    Returns count killed. Never touches user's regular Chrome windows.
    """
    if not sys.platform.startswith("win"):
        return 0
    try:
        ps = (
            "Get-CimInstance Win32_Process -Filter \\"Name = 'chrome.exe'\\" | "
            "Where-Object { $_.CommandLine -like '*chrome-profile*' -or "
            "$_.CommandLine -like '*ainterceptor*' } | "
            "ForEach-Object { Stop-Process -Id $_.ProcessId -Force -EA SilentlyContinue; $_.ProcessId }"
        )
        r = subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps],
            capture_output=True, text=True, timeout=15,
        )
        count = len([l for l in (r.stdout or "").splitlines() if l.strip()])
        return count
    except Exception:
        return 0
'''
    # Insert before "class Tab:"
    anchor = "@dataclass\nclass Tab:"
    if anchor in src:
        src = src.replace(anchor, helper + "\n\n" + anchor, 1)
        print("  [OK] added _kill_our_chromes helper")
    else:
        # fallback: after _kill_port
        anchor2 = "def _kill_port(port: int) -> None:"
        idx = src.find(anchor2)
        if idx == -1:
            print("[FAIL] no anchor for helper"); sys.exit(1)
        # insert after _kill_port's body — find next blank line after
        end = src.find("\n\n\n", idx)
        if end == -1:
            end = src.find("\n\n", idx + 100)
        src = src[:end] + helper + src[end:]
        print("  [OK] added helper (fallback position)")

# ── 2. Call the helper in _launch before spawning ──
old = '''        if _cdp_alive(CDP_PORT):
            # Reuse the existing Chrome — do not launch a second one.
            self.log(f"reusing existing Chrome on port {CDP_PORT}")
            self._chrome_proc = None
            ready = True
        else:
            # Kill any zombie listener (port open but not answering CDP)
            if _port_open(CDP_PORT):
                self.log(f"port {CDP_PORT} held by non-CDP process — killing")
                _kill_port(CDP_PORT)
                await asyncio.sleep(2.0)

            chrome = _find_chrome()'''

new = '''        if _cdp_alive(CDP_PORT):
            self.log(f"reusing existing Chrome on port {CDP_PORT}")
            self._chrome_proc = None
            ready = True
        else:
            # Kill any Chrome holding our profile (would otherwise make the
            # new launch silently delegate and never bind the debug port)
            killed = _kill_our_chromes()
            if killed:
                self.log(f"killed {killed} stale Chrome(s) using our profile")
                await asyncio.sleep(2.5)

            # Also clear any zombie listener on 9222
            if _port_open(CDP_PORT):
                self.log(f"port {CDP_PORT} held by non-CDP process — killing")
                _kill_port(CDP_PORT)
                await asyncio.sleep(2.0)

            chrome = _find_chrome()'''

if old in src:
    src = src.replace(old, new, 1)
    print("  [OK] _launch now kills our stale Chromes before launching")
else:
    print("  [!] _launch preamble not matched")
    # print current preamble
    idx = src.find("        if _cdp_alive(CDP_PORT):")
    if idx != -1:
        print(src[idx:idx+900])

# ── 3. Ensure log redirect is really in place ──
if "chrome_launch.log" not in src:
    old_popen = '''            self._chrome_proc = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                creationflags=getattr(subprocess, "DETACHED_PROCESS", 0)
                | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0),
            )'''
    new_popen = '''            log_dir = pathlib.Path(".ainterceptor")
            log_dir.mkdir(parents=True, exist_ok=True)
            chrome_log = open(log_dir / "chrome_launch.log", "ab")
            self._chrome_proc = subprocess.Popen(
                cmd,
                stdout=chrome_log, stderr=chrome_log,
                creationflags=getattr(subprocess, "DETACHED_PROCESS", 0)
                | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0),
            )
            self.log(f"Chrome PID: {self._chrome_proc.pid}")'''
    if old_popen in src:
        src = src.replace(old_popen, new_popen, 1)
        print("  [OK] log redirect added (Chrome output -> .ainterceptor/chrome_launch.log)")
    else:
        print("  [!] Popen pattern not found — inspect manually")

BS.write_text(src, encoding="utf-8", newline="\n")

try:
    ast.parse(src)
    print("  [OK] syntax valid")
except SyntaxError as e:
    print(f"[FAIL] {e}"); sys.exit(1)

def git(a):
    return subprocess.run(["git"]+a, cwd=ROOT, capture_output=True, text=True)
git(["add","-A"])
r = git(["commit","-m","fix(supervisor): kill stale Chromes holding our profile before launching"])
print((r.stdout.strip() or r.stderr.strip())[:250])

print()
print("=" * 60)
print("NEXT — clean start")
print()
print("  1. Kill the stale Chrome processes from earlier manually:")
print("     Get-CimInstance Win32_Process -Filter \\"Name='chrome.exe'\\" |")
print("       Where-Object { $_.CommandLine -like '*chrome-profile*' } |")
print("       ForEach-Object { Stop-Process -Id $_.ProcessId -Force }")
print()
print("  2. Verify 9222 is free:")
print("     Get-NetTCPConnection -LocalPort 9222 -State Listen -EA SilentlyContinue")
print()
print("  3. Start daemon:")
print("     .\\run-windows.ps1")
print()
print("  Expected: '[browser] killed N stale Chrome(s)' then a fresh launch.")
print("=" * 60)
