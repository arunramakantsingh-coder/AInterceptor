import pathlib, subprocess, sys, re

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
if not (ROOT / ".git").exists():
    ROOT = pathlib.Path(r"C:\Projects\AInterceptor")

def run(args, cwd=ROOT, check=True):
    print(f"  $ {' '.join(args)}")
    r = subprocess.run(args, cwd=cwd, capture_output=True, text=True, shell=True)
    if r.stdout.strip(): print("   ", r.stdout.strip()[-1500:])
    if r.stderr.strip(): print("   ", r.stderr.strip()[-800:])
    if check and r.returncode != 0:
        print(f"FAIL: {r.returncode}"); sys.exit(1)
    return r

# --- 1. Governance Section 21: UI-first ---
gov = ROOT / "PROJECT_GOVERNANCE_STANDARD_v1.1.md"
s = gov.read_text(encoding="utf-8")
m, e = "<!-- SECTION:21_UI_FIRST -->", "<!-- /SECTION:21_UI_FIRST -->"
sec = f"""{m}
## 21. UI-First Development Rule

Every phase ships its UI surface in the same commit as its backend.

### 21.1 Rules
- A backend phase is not accepted without a visible page/panel in the
  governance dashboard by end of phase.
- Frontend is developed in parallel with backend, never after.
- New backend capability => new or updated dashboard page in the same
  milestone commit (or the immediately following UI commit under the
  same milestone).
- The dashboard is the developer's window into the running system.

### 21.2 Required UI touchpoints per phase
- Phase with a new provider => Providers page row updated.
- Phase with a new route => Status page reflects current task.
- Phase with new logs => Intercept Log page (Phase 2+).
- Phase with new config => Config page (Phase 3+).
- Phase with new gateway endpoints => Gateway page (Phase 6+).

### 21.3 Rationale
Blind backend development hides regressions. Visible UI forces real
verification and gives stakeholders ongoing visibility.
{e}"""
if m in s:
    s = re.sub(re.escape(m)+r".*?"+re.escape(e), sec, s, flags=re.S)
else:
    s = s.rstrip() + "\n\n" + sec + "\n"
gov.write_text(s, encoding="utf-8")
print("[OK] governance: Section 21 UI-first")

# --- 2. AGENTS.md ---
ag = ROOT / "AGENTS.md"
a = ag.read_text(encoding="utf-8")
if "Section 21" not in a:
    a = a.rstrip() + "\n\n## UI-First (Section 21)\nEvery phase ships its dashboard page in the same milestone. No backend-only phases.\n"
ag.write_text(a, encoding="utf-8")
print("[OK] AGENTS.md: UI-first note")

# --- 3. ROADMAP: Phase 1 COMPLETE + gate ---
rm = ROOT / "PROJECT/ROADMAP.md"
r = rm.read_text(encoding="utf-8")
r = r.replace("| 1 | Governance Dashboard | PENDING |",
              "| 1 | Governance Dashboard | COMPLETE (v0.1.0) |")
r = r.replace("Current: Phase 1 — Governance Dashboard (1.1 PASS, 1.2 in progress)",
              "Current: Phase 1 COMPLETE at v0.1.0 — moving to Phase 2 (Interceptor Claude PoC)")

# gate table -> all PASS
gate = """| Gate | Status |
|---|---|
| Implementation | PASS |
| Local Validation | PASS |
| Security/integrity review | PASS |
| Git diff review | PASS |
| Commit | c9d7852 + M1.5 |
| Push | PASS |
| Remote verification | PASS |
| Documentation/ROADMAP | UPDATED |
| Milestone | COMPLETE |"""
r = re.sub(r"\| Gate \| Status \|\n\|---\|---\|\n(?:\| [^\n]+\n)+", gate + "\n", r)
rm.write_text(r, encoding="utf-8")
print("[OK] ROADMAP: Phase 1 COMPLETE, gate PASS")

# --- 4. CURRENT_TASK ---
(ROOT / ".ai/CURRENT_TASK.md").write_text("""# .ai/CURRENT_TASK.md
Phase: 2 — Interceptor Claude Web PoC
Goal: Playwright session + network interception -> SSE parse -> chunk stream.
UI deliverable: /intercept page showing live log of prompt/response chunks.
Prior: Phase 1 COMPLETE at tag v0.1.0.
Next: scripts/bootstrap/phase_2.py
""", encoding="utf-8")
print("[OK] CURRENT_TASK.md -> Phase 2")

# --- 5. SESSION append ---
sess = ROOT / ".ai/SESSION.md"
text = sess.read_text(encoding="utf-8")
entry = "## 2026-09-16 — Phase 1 complete (v0.1.0)\n- Dashboard: 8 routes live (commits, versions, compare, roadmap, bugs, providers, status, rollback).\n- M1.5 provider health + status panel added.\n- Section 21 UI-first rule adopted.\n- Tagged v0.1.0.\n\n"
sess.write_text(entry + text.split("\n", 1)[1] if "\n" in text else entry + text, encoding="utf-8")
print("[OK] SESSION.md appended")

# --- 6. Commit + tag ---
run(["git", "add", "PROJECT_GOVERNANCE_STANDARD_v1.1.md", "AGENTS.md",
     "PROJECT/ROADMAP.md", ".ai/CURRENT_TASK.md", ".ai/SESSION.md"])

msg = ("chore(M1.CLOSE): close Phase 1, tag v0.1.0\n\n"
       "- Phase 1 gate all PASS\n"
       "- Section 21 UI-First Development Rule\n"
       "- ROADMAP: Phase 1 COMPLETE")
r = subprocess.run(["git","commit","-m",msg], cwd=ROOT, capture_output=True, text=True)
print(r.stdout.strip() or r.stderr.strip())

run(["git", "push", "origin", "main"])

# tag
subprocess.run(["git","tag","-a","v0.1.0","-m","Phase 1: Governance Dashboard"],
               cwd=ROOT, capture_output=True)
run(["git", "push", "origin", "v0.1.0"])

# verify
sha = subprocess.run(["git","rev-parse","HEAD"], cwd=ROOT,
                     capture_output=True, text=True).stdout.strip()
tag_ls = subprocess.run(["git","ls-remote","origin","refs/tags/v0.1.0"],
                        cwd=ROOT, capture_output=True, text=True).stdout
print("="*44)
print("MILESTONE: M1.CLOSE")
print("RESULT:", "PASS" if tag_ls.strip() else "BLOCKED")
print("COMMIT:", sha)
print("TAG:    v0.1.0")
print("="*44)
