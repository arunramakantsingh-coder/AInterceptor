import pathlib, subprocess, sys, datetime, re

ROOT = pathlib.Path(__file__).resolve().parent

# ---------- 1. Governance standard: add Section 19 ----------
gov = ROOT / "PROJECT_GOVERNANCE_STANDARD_v1.1.md"
s = gov.read_text(encoding="utf-8")
marker = "<!-- SECTION:19_SCRIPT_DELIVERY -->"
end    = "<!-- /SECTION:19_SCRIPT_DELIVERY -->"
sec19 = f"""{marker}
## 19. Script Delivery Rule (Hardened)

**Every instruction that changes the repository MUST be delivered as one
self-contained script that BOTH creates/modifies the file(s) AND runs any
resulting commands (validation, tests, git operations).**

This rule supersedes any interpretation of Section 18 that allowed
"create this file" and "now run this command" to be separate steps.

### 19.1 Non-negotiable
- One paste. One execution. No follow-up "now run this".
- The script writes the file(s) AND invokes them.
- Applies to: creating files, editing sections, running tests, git
  commits, pushes, remote verification, and rollbacks.
- Applies to every AI agent (Claude, DeepSeek, GPT, Gemini, Copilot,
  Cursor, Codex, and any future agent).

### 19.2 Required script shape

### 19.3 Prohibited
- Delivering a file's content alone without the command to run it.
- Delivering a command alone without the file it needs.
- Multi-turn "next run this" for a single logical change.
- Relying on the human to assemble the pieces.

### 19.4 Rationale
The developer must never translate instructions into code. The agent
produces a single artifact the developer pastes and executes.
{end}"""
if marker in s:
    s = re.sub(re.escape(marker)+r".*?"+re.escape(end), sec19, s, flags=re.S)
else:
    s = s.rstrip() + "\n\n" + sec19 + "\n"
gov.write_text(s, encoding="utf-8")
print("[OK] governance: Section 19 added")

# ---------- 2. AGENTS.md: add iron rule ----------
ag = ROOT / "AGENTS.md"
a = ag.read_text(encoding="utf-8")
rule = "\n9. **Script Delivery Rule (Section 19)** — every instruction that changes the repo is ONE pasteable script that BOTH writes the file(s) AND runs any commands. No \"now run this\" follow-ups.\n"
if "Script Delivery Rule (Section 19)" not in a:
    a = a.rstrip() + "\n" + rule
ag.write_text(a, encoding="utf-8")
print("[OK] AGENTS.md: rule 9 added")

# ---------- 3. ROADMAP: reorder — Governance Dashboard = Phase 1 ----------
rm = ROOT / "PROJECT/ROADMAP.md"
r = rm.read_text(encoding="utf-8")
r = r.replace(
"""| Phase | Name | Status |
|---|---|---|
| 0 | Framework bootstrap | IN PROGRESS |
| 1 | Single Provider PoC | PENDING |
| 2 | Session Harvesting + Direct HTTP | PENDING |
| 3 | Multi-Provider Adapters | PENDING |
| 4 | Routing Engine | PENDING |
| 5 | OpenAI-Compatible API | PENDING |
| 6 | Governance Dashboard | PENDING |""",
"""| Phase | Name | Status |
|---|---|---|
| 0 | Framework bootstrap | COMPLETE |
| 1 | Governance Dashboard | PENDING |
| 2 | Single Provider PoC | PENDING |
| 3 | Session Harvesting + Direct HTTP | PENDING |
| 4 | Multi-Provider Adapters | PENDING |
| 5 | Routing Engine | PENDING |
| 6 | OpenAI-Compatible API | PENDING |""")
r = r.replace("Current: Phase 0 — Framework bootstrap (IN PROGRESS)",
              "Current: Phase 0 COMPLETE — moving to Phase 1 (Governance Dashboard)")
rm.write_text(r, encoding="utf-8")
print("[OK] ROADMAP: reordered")

# ---------- 4. BUGS.md: log K002 ----------
bg = ROOT / "PROJECT/BUGS.md"
b = bg.read_text(encoding="utf-8")
if "K002" not in b:
    b = b.replace("| B001 | Medium | 0 | PowerShell here-string bootstrap broke mid-run | Migrated to Python bootstrap |",
"""| B001 | Medium | 0 | PowerShell here-string bootstrap broke mid-run | Migrated to Python bootstrap |
| K002 | Low | 0 | datetime.utcnow() deprecation warning in validate_phase.py | Patched to datetime.now(datetime.UTC) |""")
bg.write_text(b, encoding="utf-8")
print("[OK] BUGS.md: K002 logged")

# ---------- 5. .ai/CURRENT_TASK.md ----------
ct = ROOT / ".ai/CURRENT_TASK.md"
ct.write_text("""# .ai/CURRENT_TASK.md
Phase: 1 — Governance Dashboard
Goal: Build the developer governance page (commit/version toggle,
rollback via revert, roadmap tracker, bug tracker, GitHub integration).
Prior phase: 0 COMPLETE at commit b0d30ad.
Next: Phase 1 bootstrap script (Next.js dashboard skeleton).
""", encoding="utf-8")
print("[OK] CURRENT_TASK.md updated")

# ---------- 6. Commit M0.1 ----------
def run(args, check=True):
    print(f"  $ {' '.join(args)}")
    r = subprocess.run(args, cwd=ROOT, capture_output=True, text=True)
    if r.stdout.strip(): print("   ", r.stdout.strip())
    if r.stderr.strip(): print("   ", r.stderr.strip())
    if check and r.returncode != 0:
        print(f"FAIL: {r.returncode}"); sys.exit(1)
    return r

print("==> Staging doc changes")
for p in ["PROJECT_GOVERNANCE_STANDARD_v1.1.md","AGENTS.md",
          "PROJECT/ROADMAP.md","PROJECT/BUGS.md",".ai/CURRENT_TASK.md"]:
    run(["git","add","--",p])

msg = ("docs(M0.1): harden script delivery rule + reorder phases\n\n"
       "- Add Section 19 Script Delivery Rule (one script creates AND runs)\n"
       "- AGENTS.md iron rule 9\n"
       "- Reorder: Governance Dashboard is Phase 1\n"
       "- Log K002 datetime deprecation\n")
run(["git","commit","-m",msg])
run(["git","push","origin","main"])

sha = subprocess.run(["git","rev-parse","HEAD"],
                     cwd=ROOT, capture_output=True, text=True).stdout.strip()
print("="*44); print("MILESTONE: M0.1"); print("RESULT: PASS")
print(f"COMMIT: {sha}"); print("BRANCH: main"); print("="*44)
