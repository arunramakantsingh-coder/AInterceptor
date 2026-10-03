import pathlib, subprocess, sys, datetime

ROOT = pathlib.Path.cwd()

# ── 1. ROADMAP entry ──
rm = ROOT / "PROJECT/ROADMAP.md"
text = rm.read_text(encoding="utf-8") if rm.exists() else "# ROADMAP\n"
entry = f"""
## Phase 2 — Interceptor (DeepSeek PoC) — COMPLETE

- Date: {datetime.date.today().isoformat()}
- Provider: DeepSeek Web (CDP 9223)
- Reply matches browser byte-for-byte (verified with two prompts)
- DeepThink disabled to prevent THINK fragment interference
- Transport: CDP network capture, DOM as authoritative text source
- Registry-enforced per-provider CDP (Claude 9222, DeepSeek 9223)
- Tests: 19/19 passing
- Tag: v0.2.0-deepseek
"""
if "Phase 2 — Interceptor (DeepSeek PoC) — COMPLETE" not in text:
    rm.write_text(text.rstrip() + "\n" + entry, encoding="utf-8", newline="\n")
    print("  [OK] ROADMAP updated")

# ── 2. git commit, tag, push ──
def git(a):
    return subprocess.run(["git"]+a, cwd=ROOT, capture_output=True, text=True)

git(["add","-A"])
r = git(["commit","-m","chore: close Phase 2 — DeepSeek PoC working"])
print(r.stdout.strip() or r.stderr.strip())

subprocess.run(["git","tag","-a","v0.2.0-deepseek",
                "-m","Phase 2: DeepSeek interceptor working"],
               cwd=ROOT, capture_output=True)

branch = git(["rev-parse","--abbrev-ref","HEAD"]).stdout.strip()
sha = git(["rev-parse","HEAD"]).stdout.strip()

for ref in ["origin", branch, "v0.2.0-deepseek"]:
    r = git(["push"] + (["origin"] if ref != "origin" else []) + ([ref] if ref != "origin" else []))
    print(r.stdout.strip() or r.stderr.strip())

print("=" * 60)
print("PHASE 2 CLOSED")
print(f"  Branch: {branch}")
print(f"  Commit: {sha[:10]}")
print(f"  Tag:    v0.2.0-deepseek")
print("=" * 60)
print()
print("LAUNCH:")
print("  bootai.exe")
print("  AInterceptor-BOOT> airouter")
print("  AIRouter> c d")
print("  AIRouter(chat)> <your prompt>")
print("=" * 60)
