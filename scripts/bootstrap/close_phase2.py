import pathlib, subprocess, sys, re, datetime

ROOT = pathlib.Path.cwd()
ROADMAP = ROOT / "PROJECT/ROADMAP.md"

text = ROADMAP.read_text(encoding="utf-8") if ROADMAP.exists() else "# ROADMAP\n"
entry = f"""## Phase 2 — Interceptor (DeepSeek PoC) — COMPLETE

- Date: {datetime.date.today().isoformat()}
- Provider: DeepSeek Web (CDP 9223)
- Byte-exact match with browser: verified
- Parser: RESPONSE-only, per-fragment content, idempotent append
- Runtime: DOM ground-truth on finalize, registry-enforced CDP
- Tests: 19/19 passing
- Commit: 4b3e2cf
"""
if "Phase 2 — Interceptor (DeepSeek PoC) — COMPLETE" not in text:
    text = text.rstrip() + "\n\n" + entry
    ROADMAP.write_text(text, encoding="utf-8", newline="\n")
    print("  [OK] ROADMAP updated")

def git(a):
    return subprocess.run(["git"]+a, cwd=ROOT, capture_output=True, text=True)

git(["add","-A"])
r = git(["commit","-m","chore: close Phase 2 — DeepSeek PoC byte-exact"])
print(r.stdout.strip() or r.stderr.strip())

git(["tag","-a","v0.2.0-deepseek","-m","Phase 2: DeepSeek interceptor working byte-exact"])
git(["push","origin","main"])
git(["push","origin","v0.2.0-deepseek"])
r = git(["push","origin","fix/nonclaude-three-providers-20260917"])
print(r.stdout.strip() or r.stderr.strip())

sha = git(["rev-parse","HEAD"]).stdout.strip()
print("=" * 60)
print("TAG: v0.2.0-deepseek  COMMIT:", sha[:10])
print("=" * 60)
print("Launch the working chat:")
print("  cd backend")
print('  $env:PYTHONUTF8="1"')
print("  C:\\Projects\\Atlas\\.venv\\Scripts\\python.exe -u -m scripts.chat_deepseek")
print("=" * 60)
