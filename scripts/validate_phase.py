#!/usr/bin/env python3
from __future__ import annotations
import argparse, json, pathlib, sys, datetime

ROOT = pathlib.Path(__file__).resolve().parent.parent

GROUPS = {
  "dirs": ["PROJECT","TEST/unit","TEST/integration","TEST/e2e","TEST/security",
    "TEST/fixtures",".ai","docs/rfcs","backend/app/providers",
    "backend/app/routing","backend/app/interception","backend/app/api",
    "dashboard","scripts"],
  "root": ["README.md","AGENTS.md","BLUEPRINT.md","KICKOFF_PROMPT.txt",
    "PROJECT_GOVERNANCE_STANDARD_v1.1.md",".gitignore"],
  "project": ["PROJECT/REQUIREMENTS.md","PROJECT/ARCHITECTURE.md",
    "PROJECT/ROADMAP.md","PROJECT/BUGS.md","PROJECT/DECISIONS.md",
    "PROJECT/CHANGELOG.md","PROJECT/GOVERNANCE.md"],
  "test": ["TEST/STRATEGY.md"],
  "ai": [".ai/CONTEXT.md",".ai/CURRENT_TASK.md",".ai/SESSION.md",
    ".ai/KNOWN_ISSUES.md",".ai/FUTURE_WORK.md",".ai/HANDOFF.md"],
  "scripts": ["scripts/milestone_commit.ps1","scripts/validate_phase.py"],
}

def chk(p):
    ok = (ROOT / p).exists()
    return ok, f"{p} {'OK' if ok else 'MISSING'}"

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--phase", default=None)
    ap.add_argument("--milestone", default=None)
    a = ap.parse_args()
    label = a.milestone or (f"Phase {a.phase}" if a.phase else "Phase 0")
    print(f"VALIDATION: {label}")
    print("-" * 44)
    checks = []
    for g, items in GROUPS.items():
        for p in items: checks.append(chk(p))
    gov = ROOT / "PROJECT_GOVERNANCE_STANDARD_v1.1.md"
    if gov.exists():
        has = "SECTION:18_PASTEABLE_SCRIPTS" in gov.read_text(encoding="utf-8")
        checks.append((has, "Section 18 marker present"))
    ag = ROOT / "AGENTS.md"
    if ag.exists():
        checks.append(("Section 18" in ag.read_text(encoding="utf-8"),
                       "AGENTS.md references Section 18"))
    passed = sum(1 for ok,_ in checks if ok)
    total = len(checks)
    for ok,msg in checks:
        print(f"  [{'PASS' if ok else 'FAIL'}] {msg}")
    result = "PASS" if passed == total else "FAIL"
    print("-" * 44)
    print(f"RESULT: {result} ({passed}/{total})")
    ev = ROOT / ".evidence"; ev.mkdir(exist_ok=True)
    stamp = datetime.datetime.now(datetime.UTC).strftime("%Y%m%dT%H%M%SZ")
    log = ev / f"validate_{label.replace(' ','_')}_{stamp}.json"
    log.write_text(json.dumps({"label":label,"passed":passed,"total":total,
        "result":result,"checks":[{"ok":o,"msg":m} for o,m in checks],
        "utc":stamp}, indent=2), encoding="utf-8")
    print(f"EVIDENCE: {log.relative_to(ROOT)}")
    return 0 if result == "PASS" else 1

if __name__ == "__main__":
    sys.exit(main())
