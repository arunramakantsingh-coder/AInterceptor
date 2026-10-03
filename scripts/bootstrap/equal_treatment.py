import pathlib, subprocess, sys, ast

ROOT = pathlib.Path.cwd()
BE   = ROOT / "backend" / "app"
LH   = BE / "runtime" / "login_helper.py"
BIN  = ROOT / "bin"
BIN.mkdir(exist_ok=True)

# ═══════════════════════════════════════════════════════════════
# 1. Add login markers for ALL 20 providers
# ═══════════════════════════════════════════════════════════════
src = LH.read_text(encoding="utf-8")

# Full set of 20
new_markers = '''LOGIN_MARKERS: dict[str, tuple[str, ...]] = {
    # Original 10
    "claude":      ("/login", "/auth", "/signin", "claude.ai/login"),
    "chatgpt":     ("/auth/login", "/auth/0", "/login"),
    "gemini":      ("/accounts/", "signin", "accounts.google.com"),
    "deepseek":    ("/login", "/auth", "/sign_in", "/signin"),
    "mistral":     ("/login", "/auth", "/signin", "/sign-in"),
    "qwen":        ("/login", "/auth", "/signin"),
    "huggingchat": ("/login", "/auth", "signin"),
    "perplexity":  ("/login", "/auth"),
    "grok":        ("/login", "/auth", "/signin"),
    "poe":         ("/login", "/auth", "/signin"),
    # New 10 (Tier A)
    "kimi":        ("/login", "/auth", "/signin"),
    "yi":          ("/login", "/signin", "/auth"),
    "lechat":      ("/login", "/auth", "/signin"),
    "glm":         ("/login", "/auth", "/signin"),
    "you":         ("/login", "/signin"),
    "phind":       ("/login", "/signin"),
    "doubao":      ("/login", "/signin", "/auth"),
    # New 3 (Tier B)
    "copilot":     ("/login", "/signin", "login.live.com"),
    "meta":        ("/login", "/signin", "facebook.com/login", "instagram.com/accounts/login"),
    "character":   ("/login", "/signin", "plus.character.ai"),
}'''

# Find and replace the LOGIN_MARKERS block
import re
pattern = re.compile(r"LOGIN_MARKERS:\s*dict\[str,\s*tuple\[str,\s*\.\.\.\]\]\s*=\s*\{.*?\n\}", re.S)
if pattern.search(src):
    src = pattern.sub(new_markers, src, count=1)
    LH.write_text(src, encoding="utf-8", newline="\n")
    print("  [OK] login_helper.py: LOGIN_MARKERS extended to all 20 providers")
else:
    print("  [!] LOGIN_MARKERS block not matched — inspect")
    sys.exit(1)

# Also ensure LOGIN_TIMEOUT_S is defined
if "LOGIN_TIMEOUT_S" not in src:
    src = src.replace(
        'LOGIN_MARKERS: dict[str, tuple[str, ...]] = {',
        'LOGIN_TIMEOUT_S = 300   # 5 min\n\n\nLOGIN_MARKERS: dict[str, tuple[str, ...]] = {',
        1,
    )
    LH.write_text(src, encoding="utf-8", newline="\n")
    print("  [OK] added LOGIN_TIMEOUT_S")

# Verify syntax
try:
    ast.parse(LH.read_text(encoding="utf-8"))
except SyntaxError as e:
    print(f"[FAIL] login_helper syntax: {e}"); sys.exit(1)
print("  [OK] login_helper.py syntax valid")

# ═══════════════════════════════════════════════════════════════
# 2. CLI activate / deactivate commands
# ═══════════════════════════════════════════════════════════════
(BIN / "activate.cmd").write_text(
    "@echo off\r\n"
    "set PYTHONUTF8=1\r\n"
    f'cd /d "{ROOT / "backend"}"\r\n'
    f'"{ROOT / ".venv-windows" / "Scripts" / "python.exe"}" -u -m scripts.manage_provider activate %*\r\n',
    encoding="utf-8", newline="",
)
print("  [NEW] bin/activate.cmd")

(BIN / "deactivate.cmd").write_text(
    "@echo off\r\n"
    "set PYTHONUTF8=1\r\n"
    f'cd /d "{ROOT / "backend"}"\r\n'
    f'"{ROOT / ".venv-windows" / "Scripts" / "python.exe"}" -u -m scripts.manage_provider deactivate %*\r\n',
    encoding="utf-8", newline="",
)
print("  [NEW] bin/deactivate.cmd")

(BIN / "providers.cmd").write_text(
    "@echo off\r\n"
    "set PYTHONUTF8=1\r\n"
    f'cd /d "{ROOT / "backend"}"\r\n'
    f'"{ROOT / ".venv-windows" / "Scripts" / "python.exe"}" -u -m scripts.manage_provider list %*\r\n',
    encoding="utf-8", newline="",
)
print("  [NEW] bin/providers.cmd")

# ═══════════════════════════════════════════════════════════════
# 3. manage_provider.py — CLI helper
# ═══════════════════════════════════════════════════════════════
(BE / "scripts" / "manage_provider.py").write_text('''"""CLI helper for provider active/inactive state.

Usage:
    python -m scripts.manage_provider list
    python -m scripts.manage_provider activate <provider>
    python -m scripts.manage_provider deactivate <provider>
    python -m scripts.manage_provider activate-all
    python -m scripts.manage_provider deactivate-all
"""
from __future__ import annotations
import sys

from app.control_plane.state import get_state, ALL_KNOWN


def _print_table(state) -> None:
    active = set(state.list_active())
    print()
    print(f"  {'PROVIDER':<14} {'STATUS':<10}")
    print("  " + "-" * 26)
    for p in sorted(ALL_KNOWN):
        status = "active" if p in active else "inactive"
        marker = "*" if p in active else " "
        print(f"  {marker} {p:<12} {status:<10}")
    print()
    print(f"  {len(active)} active / {len(ALL_KNOWN)} total")
    print()


def main() -> int:
    args = sys.argv[1:]
    if not args:
        _print_table(get_state())
        return 0

    cmd = args[0].lower()
    state = get_state()

    if cmd == "list":
        _print_table(state)
        return 0

    if cmd == "activate-all":
        state.set_active(ALL_KNOWN)
        print(f"activated all {len(ALL_KNOWN)} providers")
        _print_table(state)
        return 0

    if cmd == "deactivate-all":
        state.set_active([])
        print("deactivated all providers")
        _print_table(state)
        return 0

    if cmd in ("activate", "deactivate") and len(args) >= 2:
        provider = args[1].lower()
        if provider not in ALL_KNOWN:
            print(f"unknown provider: {provider}")
            print(f"known: {sorted(ALL_KNOWN)}")
            return 1
        if cmd == "activate":
            ok = state.activate(provider)
            print(f"activate {provider}: {'OK' if ok else 'already active'}")
        else:
            ok = state.deactivate(provider)
            print(f"deactivate {provider}: {'OK' if ok else 'already inactive'}")
        _print_table(state)
        return 0

    print("usage:")
    print("  manage_provider list")
    print("  manage_provider activate <provider>")
    print("  manage_provider deactivate <provider>")
    print("  manage_provider activate-all")
    print("  manage_provider deactivate-all")
    return 1


if __name__ == "__main__":
    sys.exit(main())
''', encoding="utf-8", newline="\n")
print("  [NEW] backend/app/scripts/manage_provider.py")

# Add __init__.py to scripts dir if missing
scripts_init = BE / "scripts" / "__init__.py"
if not scripts_init.exists():
    scripts_init.write_text('"""Backend scripts package."""\n', encoding="utf-8")
    print("  [NEW] backend/app/scripts/__init__.py")

# ═══════════════════════════════════════════════════════════════
# 4. Verify all 20 have a Runtime class
# ═══════════════════════════════════════════════════════════════
PY = ROOT / ".venv-windows" / "Scripts" / "python.exe"
if not PY.exists(): PY = sys.executable

probe = (
    "import sys, importlib\n"
    f"sys.path.insert(0, r'{ROOT / 'backend'}')\n"
    "from app.control_plane.state import ALL_KNOWN\n"
    "missing = []\n"
    "for p in ALL_KNOWN:\n"
    "    try:\n"
    "        m = importlib.import_module(f'app.interception.{p}')\n"
    "        cls = [n for n in dir(m) if n.endswith('Runtime') and not n.startswith('_')\n"
    "               and n not in ('NonClaudeWebRuntime','NonClaudeWebSocketRuntime')]\n"
    "        if not cls:\n"
    "            missing.append((p, 'no Runtime class'))\n"
    "    except Exception as e:\n"
    "        missing.append((p, str(e)[:60]))\n"
    "print(f'total: {len(ALL_KNOWN)}')\n"
    "print(f'missing: {len(missing)}')\n"
    "for p, why in missing:\n"
    "    print(f'  MISSING {p}: {why}')\n"
)
r = subprocess.run([str(PY), "-c", probe],
                   cwd=str(ROOT / "backend"), capture_output=True, text=True, encoding="utf-8")
print()
print("==> runtime class check")
print(r.stdout)
if r.stderr.strip(): print("STDERR:", r.stderr[-400:])

# ═══════════════════════════════════════════════════════════════
# 5. Commit
# ═══════════════════════════════════════════════════════════════
def git(a):
    return subprocess.run(["git"]+a, cwd=ROOT, capture_output=True, text=True)
git(["add","-A"])
r = git(["commit","-m",
         "feat(providers): login markers for all 20; activate/deactivate CLI; equal treatment"])
print((r.stdout.strip() or r.stderr.strip())[:250])

print()
print("=" * 66)
print("ALL 20 PROVIDERS NOW TREATED EQUAL")
print()
print("  • login markers      : all 20 have entries")
print("  • runtime classes    : verified above (missing count printed)")
print("  • activate/deactivate: API + CLI")
print()
print("CLI commands (run from anywhere in the repo):")
print("  providers                 → list all 20 with state")
print("  activate <provider>       → activate")
print("  deactivate <provider>     → deactivate")
print("  activate-all              → turn on all 20")
print("  deactivate-all            → turn off all")
print()
print("Example:")
print("  providers")
print("  activate mistral")
print("  providers")
print()
print("=" * 66)
