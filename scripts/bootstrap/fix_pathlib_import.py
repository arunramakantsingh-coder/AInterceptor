import pathlib, subprocess, sys, ast

ROOT = pathlib.Path.cwd()
BE   = ROOT / "backend"
PY   = r"C:\Projects\Atlas\.venv\Scripts\python.exe"
if not pathlib.Path(PY).exists():
    PY = sys.executable

def show_head(p, n=35):
    print(f"\n==> {p.relative_to(ROOT)} — first {n} lines")
    txt = p.read_text(encoding="utf-8")
    for i, ln in enumerate(txt.splitlines()[:n], 1):
        print(f"  {i:3d}  {ln}")

def ensure_import(p, name):
    """Ensure `import <name>` is present at module top (after __future__)."""
    txt = p.read_text(encoding="utf-8")
    if f"\nimport {name}\n" in txt or txt.startswith(f"import {name}\n"):
        print(f"  [OK] {p.name}: 'import {name}' already present")
        return False
    lines = txt.splitlines()
    # Find position right after `from __future__ import annotations` if present
    future_idx = None
    for i, ln in enumerate(lines):
        if ln.strip() == "from __future__ import annotations":
            future_idx = i
            break
    insert_at = (future_idx + 1) if future_idx is not None else 0
    # Skip blank lines right after future
    while insert_at < len(lines) and lines[insert_at].strip() == "":
        insert_at += 1
    lines.insert(insert_at, f"import {name}")
    new_txt = "\n".join(lines) + "\n"
    # Verify syntax
    try:
        ast.parse(new_txt)
    except SyntaxError as e:
        print(f"  [FAIL] {p.name}: syntax error after insert: {e}")
        return False
    p.write_text(new_txt, encoding="utf-8", newline="\n")
    print(f"  [OK] {p.name}: inserted 'import {name}' at line {insert_at+1}")
    return True

# ── Show the actual files ──
show_head(BE / "app/interception/nonclaude_runtime.py", 30)
show_head(BE / "app/interception/deepseek.py", 30)

# ── Fix missing imports ──
changed = False
changed |= ensure_import(BE / "app/interception/nonclaude_runtime.py", "pathlib")
changed |= ensure_import(BE / "app/interception/nonclaude_runtime.py", "os")
changed |= ensure_import(BE / "app/interception/deepseek.py", "pathlib")
changed |= ensure_import(BE / "app/interception/deepseek.py", "os")

# ── Verify all modules import cleanly ──
probe = (
    "import sys, pathlib\n"
    "sys.path.insert(0, r'" + str(BE) + "')\n"
    "import app.interception.nonclaude_runtime as n\n"
    "import app.interception.deepseek as d\n"
    "from app.interception.registry import cdp_url\n"
    "print('nonclaude:', n.NonClaudeNetworkCapture.__name__)\n"
    "print('deepseek :', d.DeepSeekRuntime.__name__)\n"
    "print('deepseek CDP ->', cdp_url('deepseek'))\n"
    "print('claude   CDP ->', cdp_url('claude'))\n"
    "# Simulate _raw_capture_path\n"
    "import os\n"
    "os.environ['AINTERCEPTOR_RAW_CAPTURE_DIR'] = '.evidence/raw'\n"
    "cls = n.NonClaudeNetworkCapture\n"
    "print('has _raw_capture_path:', hasattr(cls, '_raw_capture_path'))\n"
)
r = subprocess.run([PY, "-c", probe], capture_output=True, text=True)
print("\n==> Import probe")
print(r.stdout)
if r.stderr.strip(): print("STDERR:", r.stderr)
if r.returncode != 0:
    print("  [FAIL] imports still broken"); sys.exit(1)

# ── Verify CLI imports ──
probe2 = (
    "import sys\n"
    "sys.path.insert(0, r'" + str(ROOT) + "')\n"
    "sys.path.insert(0, r'" + str(BE) + "')\n"
    "import cli.main, cli.shell, cli.chat\n"
    "print('CLI OK')\n"
)
r = subprocess.run([PY, "-c", probe2], capture_output=True, text=True)
print("\n==> CLI probe")
print(r.stdout, r.stderr or "", sep="")
if r.returncode != 0:
    print("  [FAIL] CLI still broken"); sys.exit(1)

# ── Commit ──
if changed:
    def git(args):
        return subprocess.run(["git"]+args, cwd=ROOT, capture_output=True, text=True)
    git(["add", "-A"])
    r = git(["commit", "-m", "fix(interception): restore pathlib/os imports lost during reorder"])
    print("\n" + (r.stdout.strip() or r.stderr.strip()))
else:
    print("\n  [OK] no changes needed")

print("=" * 60)
print("RESULT: PASS")
print("NEXT: relaunch the CLI and try again:")
print("  bootai")
print("  AIRouter> c d")
print("  AIRouter(chat)> hi")
print("=" * 60)
