# AGENTS.md — AInterceptor

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

9. **Script Delivery Rule (Section 19)** — every instruction that changes the repo is ONE pasteable script that BOTH writes the file(s) AND runs any commands. No "now run this" follow-ups.

## Two Subsystems (Section 20)
- **Interceptor** — web-layer interception. `backend/app/interception/`, `providers/`.
- **Orchestrator** — routing, capability selection, merging, **public Gateway API**. `backend/app/orchestrator/`, `gateway/`.
Every change declares its subsystem. No cross-subsystem imports except via defined interfaces.

## Two Subsystems (Section 20)
- **Interceptor** — web-layer interception. `backend/app/interception/`, `providers/`.
- **Orchestrator** — routing, capability selection, merging, **public Gateway API**. `backend/app/orchestrator/`, `gateway/`.
Every change declares its subsystem. No cross-subsystem imports except via defined interfaces.

## UI-First (Section 21)
Every phase ships its dashboard page in the same milestone. No backend-only phases.
