import pathlib, subprocess, sys, ast

ROOT = pathlib.Path.cwd()
BE = ROOT / "backend" / "app"

# ═══════════════════════════════════════════════════════════════
# 1. New helper module — clean, no nested escaping
# ═══════════════════════════════════════════════════════════════
(BE / "runtime" / "_chrome_helpers.py").write_text('''"""Chrome process helpers for the browser supervisor."""
from __future__ import annotations
import pathlib
import socket
import subprocess
import sys


def find_chrome() -> str | None:
    for c in (r"C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
              r"C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe"):
        if pathlib.Path(c).exists():
            return c
    return None


def port_open(port: int) -> bool:
    s = socket.socket()
    s.settimeout(0.4)
    try:
        s.connect(("127.0.0.1", port))
        return True
    except OSError:
        return False
    finally:
        s.close()


def cdp_alive(port: int) -> bool:
    import urllib.request
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/json/version",
                                    timeout=1.0) as r:
            return "Browser" in r.read().decode("utf-8", "replace")
    except Exception:
        return False


def kill_port(port: int) -> None:
    if not sys.platform.startswith("win"):
        return
    cmd = (
        "Get-NetTCPConnection -LocalPort " + str(port) +
        " -State Listen -EA SilentlyContinue | "
        "ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -EA SilentlyContinue }"
    )
    try:
        subprocess.run(["powershell", "-NoProfile", "-Command", cmd],
                       capture_output=True, timeout=10)
    except Exception:
        pass


def kill_our_chromes() -> int:
    """Kill Chrome processes whose command line mentions our profile path.
    Never touches the user's normal Chrome windows.
    """
    if not sys.platform.startswith("win"):
        return 0
    cmd = (
        "Get-CimInstance Win32_Process -Filter \\"Name='chrome.exe'\\" | "
        "Where-Object { $_.CommandLine -like '*ainterceptor*' -or "
        "$_.CommandLine -like '*chrome-profile*' } | "
        "ForEach-Object { Stop-Process -Id $_.ProcessId -Force -EA SilentlyContinue; "
        "Write-Output $_.ProcessId }"
    )
    try:
        r = subprocess.run(["powershell", "-NoProfile", "-Command", cmd],
                           capture_output=True, text=True, timeout=15)
        ids = [ln.strip() for ln in (r.stdout or "").splitlines() if ln.strip()]
        return len(ids)
    except Exception:
        return 0
''', encoding="utf-8", newline="\n")
print("  [OK] _chrome_helpers.py created")

# ═══════════════════════════════════════════════════════════════
# 2. Patch browser_supervisor — import helpers, remove local defs
# ═══════════════════════════════════════════════════════════════
BS = BE / "runtime" / "browser_supervisor.py"
src = BS.read_text(encoding="utf-8")

# Add the import near the top
if "from app.runtime._chrome_helpers import" not in src:
    anchor = "from typing import Any"
    if anchor in src:
        src = src.replace(
            anchor,
            anchor + "\n\nfrom app.runtime._chrome_helpers import (\n"
                     "    find_chrome as _find_chrome,\n"
                     "    port_open as _port_open,\n"
                     "    cdp_alive as _cdp_alive,\n"
                     "    kill_port as _kill_port,\n"
                     "    kill_our_chromes as _kill_our_chromes,\n"
                     ")",
            1,
        )
        print("  [OK] helper import added")

# Remove inline duplicate definitions if they exist
import re
for name in ("_find_chrome", "_port_open", "_kill_port", "_cdp_alive"):
    pattern = re.compile(r"\ndef " + re.escape(name) + r"\([^)]*\)[^:]*:\n(?:    .*\n|\n)*?(?=\n\S|\Z)")
    if pattern.search(src):
        # Only remove if it's a simple def, not the imported alias
        pass

# Simpler: check if inline defs exist and remove them
for block_start in ["\ndef _find_chrome(", "\ndef _port_open(", "\ndef _kill_port(", "\ndef _kill_our_chromes("]:
    if block_start in src:
        idx = src.find(block_start)
        # find the next top-level \n\ndef or \n\nclass after idx
        nxt_def = src.find("\n\n\ndef ", idx + 1)
        nxt_class = src.find("\n\nclass ", idx + 1)
        nxt_deco = src.find("\n\n@dataclass", idx + 1)
        candidates = [x for x in (nxt_def, nxt_class, nxt_deco) if x != -1]
        if candidates:
            end = min(candidates)
            src = src[:idx] + src[end:]
            print(f"  [OK] removed inline {block_start.strip()}")

# ═══════════════════════════════════════════════════════════════
# 3. Ensure _launch uses _kill_our_chromes
# ═══════════════════════════════════════════════════════════════
if "_kill_our_chromes()" not in src:
    old = '''        else:
            # Kill any zombie listener (port open but not answering CDP)
            if _port_open(CDP_PORT):
                self.log(f"port {CDP_PORT} held by non-CDP process — killing")
                _kill_port(CDP_PORT)
                await asyncio.sleep(2.0)

            chrome = _find_chrome()'''
    new = '''        else:
            # Kill any Chrome holding our profile — otherwise a new launch
            # silently delegates to the running one and never binds CDP.
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
        print("  [OK] _launch uses _kill_our_chromes")
    else:
        print("  [!] _launch preamble not matched")

# ═══════════════════════════════════════════════════════════════
# 4. Ensure log redirect + reduce wait diagnostics
# ═══════════════════════════════════════════════════════════════
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
        print("  [OK] Chrome log redirect added")

# ═══════════════════════════════════════════════════════════════
# 5. Syntax + import check
# ═══════════════════════════════════════════════════════════════
try:
    ast.parse(src)
    print("  [OK] browser_supervisor.py syntax valid")
except SyntaxError as e:
    print(f"[FAIL] {e}")
    lines = src.splitlines()
    for i in range(max(0, e.lineno-5), min(len(lines), e.lineno+3)):
        m = ">>>" if i+1 == e.lineno else "   "
        print(f"  {m} {i+1:4d}  {lines[i]}")
    sys.exit(1)

BS.write_text(src, encoding="utf-8", newline="\n")

PY = ROOT / ".venv-windows" / "Scripts" / "python.exe"
if not PY.exists(): PY = sys.executable

probe = (
    "import sys\n"
    f"sys.path.insert(0, r'{ROOT / 'backend'}')\n"
    "from app.runtime._chrome_helpers import find_chrome, port_open, cdp_alive, kill_our_chromes\n"
    "from app.runtime.browser_supervisor import BrowserSupervisor\n"
    "print('chrome:', find_chrome())\n"
    "print('9222 open:', port_open(9222))\n"
    "print('9222 CDP :', cdp_alive(9222))\n"
    "print('killed  :', kill_our_chromes())\n"
)
r = subprocess.run([str(PY), "-c", probe],
                   cwd=str(ROOT / "backend"), capture_output=True, text=True, encoding="utf-8")
print()
print("==> helper + supervisor import test")
print(r.stdout)
if r.stderr.strip(): print("STDERR:", r.stderr[-600:])

def git(a):
    return subprocess.run(["git"]+a, cwd=ROOT, capture_output=True, text=True)
git(["add","-A"])
r = git(["commit","-m","fix(supervisor): use _chrome_helpers; kill stale Chromes; log to file"])
print((r.stdout.strip() or r.stderr.strip())[:250])

print()
print("=" * 60)
print("NEXT")
print()
print("  1. In the daemon window: Ctrl+C")
print("  2. .\\run-windows.ps1")
print()
print("  Expected new lines:")
print("    [browser] killed N stale Chrome(s) using our profile")
print("    [browser] launching Chrome: ...")
print("    [browser] Chrome PID: XXXX")
print("    [browser] attached: N contexts")
print("    [browser] open tab: chatgpt -> ...")
print()
print("  If still stuck at 'launching Chrome':")
print("    Get-Content .ainterceptor\\chrome_launch.log -Tail 40")
print("=" * 60)
