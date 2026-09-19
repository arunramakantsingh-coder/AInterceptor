import pathlib, subprocess, sys, ast, re

ROOT = pathlib.Path.cwd()
BE = ROOT / "backend" / "app"
BS = BE / "runtime" / "browser_supervisor.py"
src = BS.read_text(encoding="utf-8")

# ── 1. Add CDP_PORT and PROVIDER_URLS at module top ──
if "CDP_PORT = 9222" not in src:
    # Insert after the imports, before `def _chrome_args`
    anchor = "def _chrome_args("
    if anchor not in src:
        print("[FAIL] _chrome_args anchor missing"); sys.exit(1)

    header = '''CDP_PORT = 9222


PROVIDER_URLS: dict[str, str] = {
    "chatgpt":     "https://chatgpt.com/",
    "claude":      "https://claude.ai/",
    "gemini":      "https://gemini.google.com/",
    "deepseek":    "https://chat.deepseek.com/",
    "mistral":     "https://chat.mistral.ai/",
    "lechat":      "https://chat.mistral.ai/chat",
    "qwen":        "https://chat.qwen.ai/",
    "kimi":        "https://www.kimi.com/",
    "yi":          "https://platform.lingyiwanwu.com/",
    "glm":         "https://chat.z.ai/",
    "doubao":      "https://www.dola.com/",
    "huggingchat": "https://huggingface.co/chat/",
    "perplexity":  "https://www.perplexity.ai/",
    "you":         "https://you.com/",
    "phind":       "https://www.phind.com/",
    "grok":        "https://grok.com/",
    "meta":        "https://www.meta.ai/",
    "copilot":     "https://copilot.microsoft.com/",
    "character":   "https://character.ai/",
    "poe":         "https://poe.com/",
}


'''
    src = src.replace(anchor, header + anchor, 1)
    print("  [OK] added CDP_PORT and PROVIDER_URLS (20 providers)")
else:
    print("  [OK] CDP_PORT already defined")

# ── 2. Remove nested _cdp_alive inside _launch ──
old_nested = '''        def _cdp_alive(port: int) -> bool:
            import urllib.request as _u
            try:
                with _u.urlopen(f"http://127.0.0.1:{port}/json/version",
                                timeout=1.0) as r:
                    return "Browser" in r.read().decode("utf-8", "replace")
            except Exception:
                return False

'''
if old_nested in src:
    src = src.replace(old_nested, "", 1)
    print("  [OK] removed duplicate nested _cdp_alive")

# ── 3. Syntax check ──
try:
    ast.parse(src)
    print("  [OK] browser_supervisor.py syntax valid")
except SyntaxError as e:
    print(f"[FAIL] {e}")
    lines = src.splitlines()
    for i in range(max(0, e.lineno - 5), min(len(lines), e.lineno + 3)):
        m = ">>>" if i + 1 == e.lineno else "   "
        print(f"  {m} {i+1:4d}  {lines[i]}")
    sys.exit(1)

BS.write_text(src, encoding="utf-8", newline="\n")

# ── 4. Import test ──
PY = ROOT / ".venv-windows" / "Scripts" / "python.exe"
if not PY.exists(): PY = sys.executable

probe = (
    "import sys\n"
    f"sys.path.insert(0, r'{ROOT / 'backend'}')\n"
    "from app.runtime.browser_supervisor import BrowserSupervisor, CDP_PORT, PROVIDER_URLS\n"
    "print('CDP_PORT:', CDP_PORT)\n"
    "print('providers:', len(PROVIDER_URLS))\n"
    "print('sample:', sorted(PROVIDER_URLS)[:5])\n"
)
r = subprocess.run([str(PY), "-c", probe],
                   cwd=str(ROOT / "backend"), capture_output=True, text=True, encoding="utf-8")
print()
print("==> import test")
print(r.stdout)
if r.stderr.strip(): print("STDERR:", r.stderr[-500:])

# ── 5. Fix bin/*.cmd to use correct venv ──
print()
print("==> fixing bin/*.cmd")
BIN = ROOT / "bin"
correct_py = r"C:\Projects\AInterceptor-M1.5\.venv-windows\Scripts\python.exe"
BE_STR = str(ROOT / "backend")
if not pathlib.Path(correct_py).exists():
    # fall back to whatever venv is active
    correct_py = str(PY)

fixed = 0
for cmd_file in sorted(BIN.glob("*.cmd")):
    txt = cmd_file.read_text(encoding="utf-8", errors="replace")
    # Replace any python path with our known-good one
    new_txt = re.sub(
        r'"C:\\Projects\\[^"]+\\Scripts\\python\.exe"',
        f'"{correct_py}"',
        txt,
    )
    if new_txt != txt:
        cmd_file.write_text(new_txt, encoding="utf-8", newline="")
        fixed += 1
        print(f"  [FIX] {cmd_file.name}")

print(f"  fixed {fixed} cmd files")

# ── 6. Commit ──
def git(a):
    return subprocess.run(["git"]+a, cwd=ROOT, capture_output=True, text=True)
git(["add","-A"])
r = git(["commit","-m",
         "fix(supervisor): define CDP_PORT + PROVIDER_URLS; correct venv path in bin/*.cmd"])
print((r.stdout.strip() or r.stderr.strip())[:250])

print()
print("=" * 66)
print("FIXES APPLIED")
print()
print("  1. CDP_PORT = 9222             (was missing → caused NameError)")
print("  2. PROVIDER_URLS with 20 entries (was missing → would crash)")
print("  3. Removed duplicate nested _cdp_alive")
print("  4. bin/*.cmd now uses .venv-windows (was using Atlas venv)")
print()
print("CLEANUP BEFORE TESTING:")
print()
print("  # Kill every Chrome so the profile is clean")
print("  Get-Process chrome -EA SilentlyContinue | Stop-Process -Force")
print("  Start-Sleep -Seconds 3")
print()
print("  # Verify nothing on 9222")
print("  Get-NetTCPConnection -LocalPort 9222 -State Listen -EA SilentlyContinue")
print()
print("  # Start the daemon")
print("  .\\run-windows.ps1")
print()
print("  # In another window, test CLI for chatgpt")
print("  chatgpt")
print("=" * 66)
