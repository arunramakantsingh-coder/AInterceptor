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
