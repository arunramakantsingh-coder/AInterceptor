# bootstrap.py — AInterceptor Phase 0 bootstrap (single-file, idempotent)
import pathlib, sys, datetime, shutil, os

ROOT = pathlib.Path(__file__).resolve().parent
TS   = datetime.datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
BAK  = ROOT / ".bak" / TS

DIRS = [
    "PROJECT","TEST/unit","TEST/integration","TEST/e2e","TEST/security",
    "TEST/fixtures",".ai","docs/rfcs","backend/app/providers",
    "backend/app/routing","backend/app/interception","backend/app/api",
    "dashboard","scripts",".evidence",
]
for d in DIRS:
    (ROOT / d).mkdir(parents=True, exist_ok=True)

F = {}

F["README.md"] = """# AInterceptor

**One endpoint. Many AI web interfaces. Zero provider APIs.**

Web-layer interception router for multi-provider AI chat.

- Status: Phase 0 — Framework bootstrap
- Codename: AINT
- Governance: PROJECT_GOVERNANCE_STANDARD_v1.1.md
- Repo: https://github.com/arunramakantsingh-coder/AInterceptor
"""

F["AGENTS.md"] = """# AGENTS.md — AInterceptor

Read order: this file -> PROJECT_GOVERNANCE_STANDARD_v1.1.md -> BLUEPRINT.md
-> PROJECT/ROADMAP.md -> .ai/CURRENT_TASK.md -> .ai/KNOWN_ISSUES.md

## Iron Rules
1. Never force-push. Rollback = revert commit.
2. Never commit secrets.
3. Verify remote + branch before milestone ops.
4. Never claim success without observed evidence.
5. Every change is a single pasteable script (Governance Section 18).
6. Milestone commits only via scripts/milestone_commit.ps1.
7. No implementation before the framework exists.
8. Project rules may be stricter, never weaker.

## Stack
Python (FastAPI + Playwright) backend. Next.js dashboard (Phase 6).
"""

F["BLUEPRINT.md"] = """# BLUEPRINT.md — AInterceptor

Unified OpenAI-compatible gateway routing across AI providers via
web-layer interception (no provider APIs).

## Phases
| Phase | Name | Goal |
|---|---|---|
| 1 | Single Provider PoC | Intercept Claude or Gemini end-to-end |
| 2 | Session Harvesting + Direct HTTP | Fast path without browser |
| 3 | Multi-Provider Adapters | ChatGPT, DeepSeek, Qwen |
| 4 | Routing Engine | Fallback, load balancing, rate limits |
| 5 | OpenAI-Compatible API | /v1/chat/completions |
| 6 | Governance Dashboard | GitHub-integrated project UI |

## Legal Boundary
Personal, non-commercial, educational use only.
"""

F["KICKOFF_PROMPT.txt"] = """You are the lead implementation agent for AInterceptor.
Read AGENTS.md, PROJECT_GOVERNANCE_STANDARD_v1.1.md, BLUEPRINT.md,
PROJECT/ROADMAP.md, .ai/CURRENT_TASK.md, .ai/KNOWN_ISSUES.md before
proposing any change.
Follow Section 18. Milestone commits only via scripts/milestone_commit.ps1.
"""

F[".gitignore"] = """__pycache__/
*.py[cod]
.venv/
venv/
.pytest_cache/
node_modules/
.next/
dist/
.env
*.env
sessions/
*.session.json
cookies.json
credentials.json
.bak/
.evidence/*.log
.vscode/settings.json
.DS_Store
"""

F["PROJECT_GOVERNANCE_STANDARD_v1.1.md"] = """# PROJECT GOVERNANCE STANDARD v1.1

## 1. Purpose
Default governance for repository-based projects. Project docs may add
stricter rules but must not weaken this baseline.

## 2. Mandatory Bootstrap
README.md, AGENTS.md, BLUEPRINT.md, PROJECT/REQUIREMENTS.md,
PROJECT/ARCHITECTURE.md, PROJECT/ROADMAP.md, TEST strategy.

## 3. Method
PLAN -> FRAMEWORK -> BLUEPRINT -> IMPLEMENT -> VALIDATE -> REVIEW ->
COMMIT -> PUSH -> VERIFY -> DOCUMENT CHECKPOINT.

## 4. Milestone Gate
Implementation + validation + security + git diff + commit + push +
remote verify + roadmap update. Local-only is not complete.

## 5. Git Discipline
No force-push. No history rewrite. No secrets. Verify branch/remote.

## 6. Testing
Positive + negative + edge. Synthetic fixtures. PASS/FAIL output.

## 7. Scripts
Idempotent. Explicit paths. Backups before mutation.

## 8. Docs
Repository is the durable memory.

## 9. Agents
Read governance first. Never claim unobserved success.

## 10. Security
No secrets in logs/fixtures/commits.

## 11-17
Change management, checklist, milestone status table, precedence,
mandatory verification, verification gate, defect hardening.

<!-- SECTION:18_PASTEABLE_SCRIPTS -->
## 18. Pasteable Script Policy & Auto-Commit Checkpoint

### 18.1 Policy
Every repo-changing instruction MUST be a single, complete, pasteable
script. Idempotent. Backs up mutated files to .bak/<UTC>/ first. Uses
markers <!-- SECTION:NAME --> ... <!-- /SECTION:NAME --> for section
edits. Prints PASS/FAIL block. Fails safely.

### 18.2 Milestone Auto-Commit
After local validation passes, milestone script verifies repo/branch/
remote, runs validation, scans for secrets, stages intended files only,
commits with structured message, pushes, verifies remote SHA. Emits PASS
with commit SHA or BLOCKED with exact reason.

### 18.3 Forbidden
Manual milestone git ops. Force-push. Committing without validation.
Secrets in any file/log/message.
<!-- /SECTION:18_PASTEABLE_SCRIPTS -->
"""

F["PROJECT/REQUIREMENTS.md"] = """# REQUIREMENTS.md

## Functional
FR-001 Submit prompt to provider web UI, stream response. (Phase 1)
FR-002 Normalize SSE/WebSocket to chunks. (1)
FR-003 Detect session expiry pre-dispatch. (1)
FR-004 Playwright session harvesting. (2)
FR-005 Direct HTTP with harvested tokens. (2)
FR-006 Adapters for ChatGPT/DeepSeek/Qwen. (3)
FR-007 Routing with fallback. (4)
FR-008 Rate-limit tracking + 429 cooldown. (4)
FR-009 OpenAI-compatible /v1/chat/completions. (5)
FR-010 Governance dashboard. (6)

## Non-Functional
NFR-001 Idempotent scripts.
NFR-002 No plaintext credentials.
NFR-003 PASS/FAIL output.
NFR-004 Pasteable-script policy.
NFR-005 No secrets in git.
NFR-006 Isolated adapters, shared interface.

## Exclusions
Official APIs. Commercial resale.
"""

F["PROJECT/ARCHITECTURE.md"] = """# ARCHITECTURE.md

Client -> Routing Engine -> Provider Adapters -> Interception Layer ->
Provider Web UIs.

## Data
Session { provider, cookies, tokens, csrf, expiry } -> sessions/ (git-ignored)
Chunk { provider, delta, finish_reason, meta }
ProviderHealth { provider, status, last_success, error_rate, latency_ms }

## Interfaces
/v1/chat/completions (OpenAI JSON)
/health/providers (JSON)
/api/github/* (dashboard)

## Trust
Browser sandbox. Encrypted session vault. OAuth device flow for GitHub.
"""

F["PROJECT/ROADMAP.md"] = """# ROADMAP.md

Current: Phase 0 — Framework bootstrap (IN PROGRESS)

| Phase | Name | Status |
|---|---|---|
| 0 | Framework bootstrap | IN PROGRESS |
| 1 | Single Provider PoC | PENDING |
| 2 | Session Harvesting + Direct HTTP | PENDING |
| 3 | Multi-Provider Adapters | PENDING |
| 4 | Routing Engine | PENDING |
| 5 | OpenAI-Compatible API | PENDING |
| 6 | Governance Dashboard | PENDING |

## Phase 0 Gate
| Gate | Status |
|---|---|
| Implementation | PENDING |
| Local Validation | PENDING |
| Security/integrity | PENDING |
| Git diff review | PENDING |
| Commit | PENDING |
| Push | PENDING |
| Remote verification | PENDING |
| Documentation/ROADMAP | PENDING |
| Milestone | IN PROGRESS |
"""

F["PROJECT/BUGS.md"] = """# BUGS.md

## Open
| ID | Severity | Phase | Title | Status |
|---|---|---|---|---|

## Resolved
| ID | Severity | Phase | Title | Resolution |
|---|---|---|---|---|
| B001 | Medium | 0 | PowerShell here-string bootstrap broke mid-run | Migrated to Python bootstrap |

## Regression
| ID | Title | Test That Should Catch |
|---|---|---|
"""

F["PROJECT/DECISIONS.md"] = """# DECISIONS.md

| ADR | Title | Status | Date |
|---|---|---|---|
| 0001 | Playwright + network interception as Phase 1 mechanism | Accepted | 2026-09-15 |
| 0002 | Rollback = revert commit, never force-push | Accepted | 2026-09-15 |
| 0003 | Every repo change is a single pasteable script | Accepted | 2026-09-15 |
| 0004 | Milestone commits via script only | Accepted | 2026-09-15 |
| 0005 | Python over PowerShell for bootstrap scripts | Accepted | 2026-09-15 |
"""

F["PROJECT/CHANGELOG.md"] = """# CHANGELOG.md

## [Unreleased]
### Added
- Phase 0 framework
- Governance v1.1 with Section 18
- AGENTS.md, BLUEPRINT.md, KICKOFF_PROMPT.txt
- PROJECT/* docs, TEST/STRATEGY.md, .ai/*
- scripts/milestone_commit.ps1, scripts/validate_phase.py
### Fixed
- B001 PowerShell here-string -> Python bootstrap
"""

F["PROJECT/GOVERNANCE.md"] = """# GOVERNANCE.md

Project-specific rules (never weaker than baseline).

1. Provider isolation — no cross-imports between adapters.
2. Session files never committed.
3. Adapter interface freeze (5 methods). Changes require ADR.
4. Rate-limit floor: 1 req / 2 sec / provider account (Phase 1-3).
5. Legal notice header in every adapter file.
6. Bootstrap scripts use Python (ADR-0005).
"""

F["TEST/STRATEGY.md"] = """# TEST/STRATEGY.md

Layers: TEST/unit, integration, e2e, security, fixtures. Tool: pytest.

## Phase 0 Checks
0.1 Root files present
0.2 PROJECT files present
0.3 .ai files present
0.4 scripts present
0.5 Section 18 marker in governance
0.6 AGENTS.md references Section 18

## Output
VALIDATION: <label>
  [x.y] PASS/FAIL
RESULT: PASS (n/n)
EVIDENCE: .evidence/<file>.json
"""

F[".ai/CONTEXT.md"] = """# .ai/CONTEXT.md
Project: AInterceptor
Phase: 0
Active: see CURRENT_TASK.md
Issues: see KNOWN_ISSUES.md
"""

F[".ai/CURRENT_TASK.md"] = """# .ai/CURRENT_TASK.md
Phase: 0
Goal: Complete bootstrap, validate M0, commit, push, verify.
Next: python scripts/validate_phase.py --milestone M0
"""

F[".ai/SESSION.md"] = """# .ai/SESSION.md

## 2026-09-15 — Bootstrap
- Fresh restart. Python bootstrap. B001 resolved via ADR-0005.
"""

F[".ai/KNOWN_ISSUES.md"] = """# .ai/KNOWN_ISSUES.md
| ID | Severity | Summary | Status |
|---|---|---|---|
| B001 | Medium | PowerShell here-string broke bootstrap | Resolved |
| K001 | Low | backend/dashboard README list Phase 1+/6 commands before those phases | Open |
"""

F[".ai/FUTURE_WORK.md"] = """# .ai/FUTURE_WORK.md
- Chrome extension interception mode
- MITM proxy (mitmproxy + WireGuard)
- Multi-account rotation
- OS keychain session vault
"""

F[".ai/HANDOFF.md"] = """# .ai/HANDOFF.md
Paste for mid-project agent swap:

You are the lead implementation agent for AInterceptor.
Read AGENTS.md, PROJECT_GOVERNANCE_STANDARD_v1.1.md, BLUEPRINT.md,
PROJECT/ROADMAP.md, .ai/CURRENT_TASK.md, .ai/KNOWN_ISSUES.md.
Follow Section 18. Milestone commits only via scripts/milestone_commit.ps1.
"""

F["docs/rfcs/0000-template.md"] = """# RFC-0000 — <Title>
- Status: Draft
- Author:
- Date:

## Context
## Decision
## Consequences
## Alternatives
"""

F["docs/DECISION_LOG.md"] = """# DECISION_LOG.md
| Date | Decision | Rationale |
|---|---|---|
| 2026-09-15 | Name AInterceptor | Short, precise, no collision |
| 2026-09-15 | Python bootstrap over PowerShell | B001 |
"""

F["backend/README.md"] = """# backend/
Phase 0 — not implemented. Phase 1 adds requirements.txt and Claude adapter.
Do NOT run pip install -r requirements.txt before Phase 1.
"""

F["dashboard/README.md"] = """# dashboard/
Phase 6 — not implemented. Do NOT run npm install before Phase 6.
"""

F["scripts/validate_phase.py"] = '''#!/usr/bin/env python3
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
    stamp = datetime.datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    log = ev / f"validate_{label.replace(' ','_')}_{stamp}.json"
    log.write_text(json.dumps({"label":label,"passed":passed,"total":total,
        "result":result,"checks":[{"ok":o,"msg":m} for o,m in checks],
        "utc":stamp}, indent=2), encoding="utf-8")
    print(f"EVIDENCE: {log.relative_to(ROOT)}")
    return 0 if result == "PASS" else 1

if __name__ == "__main__":
    sys.exit(main())
'''

F["scripts/milestone_commit.ps1"] = r'''param([Parameter(Mandatory=$true)][string]$Milestone)
$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
if (-not (Test-Path '.git')) { Write-Host "BLOCKED: not a git repo"; exit 1 }
$branch = (& git rev-parse --abbrev-ref HEAD).Trim()
$remote = (& git remote get-url origin 2>$null)
if (-not $remote) { Write-Host "BLOCKED: no origin"; exit 1 }

New-Item -ItemType Directory -Force -Path '.evidence' | Out-Null
$stamp = (Get-Date).ToUniversalTime().ToString('yyyyMMddTHHmmssZ')
$log = ".evidence\${Milestone}_$stamp.log"

& python scripts\validate_phase.py --milestone $Milestone 2>&1 | Tee-Object -FilePath $log
if ($LASTEXITCODE -ne 0) { Write-Host "RESULT: BLOCKED - validation"; exit 1 }

& git add -N . 2>$null | Out-Null
$diff = (& git diff --cached -U0) -join "`n"
$pats = @('sk-[A-Za-z0-9]{20,}','Bearer\s+[A-Za-z0-9._\-]{20,}',
  '-----BEGIN [A-Z ]+PRIVATE KEY-----','SECURE_1PSID')
foreach ($p in $pats) {
  if ($diff -match $p) { Write-Host "RESULT: BLOCKED - secret $p"; exit 1 }
}

foreach ($p in @('PROJECT','TEST','.ai','docs','scripts','backend','dashboard',
  'README.md','AGENTS.md','BLUEPRINT.md','KICKOFF_PROMPT.txt',
  'PROJECT_GOVERNANCE_STANDARD_v1.1.md','.gitignore')) {
  if (Test-Path $p) { & git add -- $p 2>$null }
}

$msg = "feat(${Milestone}): milestone checkpoint`n`nMilestone: $Milestone`nValidation: PASS`nEvidence: $log"
& git commit -m $msg
if ($LASTEXITCODE -ne 0) { Write-Host "RESULT: BLOCKED - commit"; exit 1 }

& git push origin $branch
if ($LASTEXITCODE -ne 0) { Write-Host "RESULT: BLOCKED - push"; exit 1 }

$sha = (& git rev-parse HEAD).Trim()
$ls = (& git ls-remote origin "refs/heads/$branch") -join "`n"
if ($ls -notmatch [regex]::Escape($sha)) {
  Write-Host "RESULT: BLOCKED - remote verify"; exit 1 }

Write-Host "============================================"
Write-Host "MILESTONE: $Milestone"
Write-Host "RESULT: PASS"
Write-Host "COMMIT: $sha"
Write-Host "BRANCH: $branch"
Write-Host "============================================"
'''

# write
created = modified = 0
for rel, content in F.items():
    p = ROOT / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    if p.exists():
        if p.read_text(encoding="utf-8", errors="replace") == content:
            continue
        bak = BAK / rel
        bak.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(p, bak)
        modified += 1
    else:
        created += 1
    p.write_text(content, encoding="utf-8", newline="\n")

print("=" * 44)
print("SCRIPT: bootstrap.py")
print("RESULT: PASS")
print(f"CREATED:  {created}")
print(f"MODIFIED: {modified}")
print("NEXT: python scripts\\validate_phase.py --milestone M0")
print("=" * 44)