import pathlib, subprocess, sys, ast, re

ROOT = pathlib.Path.cwd()
BS = ROOT / "backend" / "app" / "runtime" / "browser_supervisor.py"
src = BS.read_text(encoding="utf-8")

# If helpers already exist, just verify
if "def _find_chrome" in src and "def _port_open" in src:
    print("  [OK] helpers already present")
else:
    helpers = '''

def _find_chrome() -> str | None:
    for c in (r"C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
              r"C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe"):
        if pathlib.Path(c).exists():
            return c
    return None


def _port_open(port: int) -> bool:
    import socket as _sock
    s = _sock.socket(); s.settimeout(0.4)
    try:
        s.connect(("127.0.0.1", port)); return True
    except OSError:
        return False
    finally:
        s.close()


def _kill_port(port: int) -> None:
    if not sys.platform.startswith("win"):
        return
    try:
        subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             f"Get-NetTCPConnection -LocalPort {port} -State Listen -EA SilentlyContinue | "
             "ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -EA SilentlyContinue }"],
            capture_output=True, timeout=10,
        )
    except Exception:
        pass
'''

    # Insert right after the last top-level import
    lines = src.splitlines()
    insert_at = 0
    for i, ln in enumerate(lines):
        s = ln.strip()
        if s.startswith("import ") or s.startswith("from "):
            insert_at = i + 1
        elif s and not s.startswith("#") and not s.startswith('"""') and insert_at > 0:
            break
    lines = lines[:insert_at] + helpers.splitlines() + [""] + lines[insert_at:]
    src = "\n".join(lines) + "\n"
    BS.write_text(src, encoding="utf-8", newline="\n")
    print("  [OK] helpers inserted at line", insert_at + 1)

# Ensure `import sys` and `import subprocess` are at top
needs_sys = "\nimport sys\n" not in src
needs_sub = "\nimport subprocess\n" not in src
if needs_sys or needs_sub:
    first_import = re.search(r"^import ", src, re.M)
    if first_import:
        add = ""
        if needs_sys: add += "import sys\n"
        if needs_sub: add += "import subprocess\n"
        src = src[:first_import.start()] + add + src[first_import.start():]
        BS.write_text(src, encoding="utf-8", newline="\n")
        print("  [OK] added", add.strip().replace(chr(10), ", "))

# Syntax check
try:
    ast.parse(BS.read_text(encoding="utf-8"))
    print("  [OK] syntax valid")
except SyntaxError as e:
    print(f"[FAIL] {e}"); sys.exit(1)

# Verify helpers resolve
PY = ROOT / ".venv-windows" / "Scripts" / "python.exe"
if not PY.exists(): PY = sys.executable
probe = (
    "import sys\n"
    f"sys.path.insert(0, r'{ROOT / 'backend'}')\n"
    "from app.runtime.browser_supervisor import _find_chrome, _port_open, _kill_port\n"
    "print('chrome:', _find_chrome())\n"
    "print('9222 open:', _port_open(9222))\n"
)
r = subprocess.run([str(PY), "-c", probe],
                   cwd=str(ROOT / "backend"), capture_output=True, text=True, encoding="utf-8")
print()
print("==> helper test")
print(r.stdout)
if r.stderr.strip(): print("STDERR:", r.stderr[-400:])

def git(a):
    return subprocess.run(["git"]+a, cwd=ROOT, capture_output=True, text=True)
git(["add","-A"])
r = git(["commit","-m","fix(supervisor): ensure _find_chrome/_port_open/_kill_port are defined"])
print((r.stdout.strip() or r.stderr.strip())[:200])

print()
print("Now retry:")
print("  .\\run-windows.ps1")
