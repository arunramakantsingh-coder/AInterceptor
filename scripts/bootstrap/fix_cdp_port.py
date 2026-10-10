import pathlib, subprocess, sys

ROOT = pathlib.Path.cwd()
BE = ROOT / "backend" / "app"

# ── Add CDP port to the supervisor's Chrome args ──
bs = BE / "runtime" / "browser_supervisor.py"
src = bs.read_text(encoding="utf-8")

old = '''def _chrome_args(profile_dir: pathlib.Path, off_screen: bool = True) -> list[str]:
    pos = "-32000,-32000" if off_screen else "100,100"
    return [
        f"--user-data-dir={profile_dir}",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-blink-features=AutomationControlled",
        "--remote-allow-origins=*",
        f"--window-position={pos}",
        "--window-size=1400,900",
        "--disable-features=ChromeWhatsNewUI",
    ]'''

new = '''CDP_PORT = 9222   # ClaudeRuntime attaches here


def _chrome_args(profile_dir: pathlib.Path, off_screen: bool = True) -> list[str]:
    pos = "-32000,-32000" if off_screen else "100,100"
    return [
        f"--user-data-dir={profile_dir}",
        f"--remote-debugging-port={CDP_PORT}",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-blink-features=AutomationControlled",
        "--remote-allow-origins=*",
        f"--window-position={pos}",
        "--window-size=1400,900",
        "--disable-features=ChromeWhatsNewUI",
    ]'''

if old in src:
    src = src.replace(old, new, 1)
    bs.write_text(src, encoding="utf-8", newline="\n")
    print("  [OK] supervisor: Chrome launched with --remote-debugging-port=9222")
else:
    print("  [!] _chrome_args pattern not matched")

# ── Make the running ports stable across reboots (drop the portproxy) ──
# (informational — not touched)

import ast
try: ast.parse(bs.read_text(encoding="utf-8"))
except SyntaxError as e:
    print("[FAIL]", e); sys.exit(1)
print("  [OK] syntax valid")

def git(a):
    return subprocess.run(["git"]+a, cwd=ROOT, capture_output=True, text=True)
git(["add","-A"])
r = git(["commit","-m","fix(supervisor): launch Chrome with CDP port 9222 so ClaudeRuntime can attach"])
print((r.stdout.strip() or r.stderr.strip())[:200])
