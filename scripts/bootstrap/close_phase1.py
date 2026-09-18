import pathlib, subprocess, datetime

ROOT = pathlib.Path.cwd()

# ROADMAP update
rm = ROOT / "PROJECT" / "ROADMAP.md"
txt = rm.read_text(encoding="utf-8")
entry = f"""
## Phase 1 — API Product + Agent — COMPLETE ({datetime.date.today().isoformat()})

- Docker Compose stack (api + postgres) running
- Auth: signup, login, JWT
- API keys: generate, list, revoke
- Sessions: encrypted upload (HKDF + AES-GCM), list, delete
- OpenAI-compatible POST /v1/chat/completions with SSE stream + [DONE]
- Agent: airouter-agent login <provider> using real Chrome, uploads storage_state
- Verified end-to-end: signup → API key → agent upload → curl chat

Next: Phase 2 — DeepSeek/Claude/Gemini real streaming (Path A/B).
"""
if "Phase 1 — API Product + Agent — COMPLETE" not in txt:
    txt = txt.rstrip() + "\n" + entry
    rm.write_text(txt, encoding="utf-8", newline="\n")
    print("  [OK] ROADMAP updated")

# KNOWN_ISSUES: mark Phase 1 items resolved
ki = ROOT / ".ai" / "KNOWN_ISSUES.md"
kt = ki.read_text(encoding="utf-8")
if "K004" in kt and "Resolved" not in kt.split("K004")[1][:200]:
    kt = kt.replace("| K004 | Med | Runtime | Claude CDP attach hangs if Chrome dead | Open |",
                    "| K004 | Med | Runtime | Claude CDP attach hangs if Chrome dead | Phase 2 |")
    ki.write_text(kt, encoding="utf-8", newline="\n")
    print("  [OK] KNOWN_ISSUES updated")

def git(a):
    return subprocess.run(["git"]+a, cwd=ROOT, capture_output=True, text=True)

git(["add","-A"])
r = git(["commit","-m","chore: close Phase 1 — API product + agent verified"])
print((r.stdout.strip() or r.stderr.strip())[:300])

git(["tag","-a","v0.2.0-phase1-api","-m","Phase 1: API product + agent complete"])
print("  [OK] tag v0.2.0-phase1-api")

sha = git(["rev-parse","HEAD"]).stdout.strip()
print()
print("=" * 66)
print("PHASE 1 COMPLETE")
print("  HEAD:", sha[:10])
print("  Tag :  v0.2.0-phase1-api")
print()
print("  What works today:")
print("    curl -X POST http://localhost:8000/v1/chat/completions \\\\")
print("      -H 'Authorization: Bearer sk-aint-...' \\\\")
print("      -d '{\"model\":\"deepseek\",\"messages\":[...],\"stream\":true}'")
print()
print("  Provider content streaming is Phase 2 (Path A/B decoders).")
print("=" * 66)
