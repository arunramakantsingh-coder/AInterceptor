# PROJECT GOVERNANCE STANDARD v1.1

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

<!-- SECTION:19_SCRIPT_DELIVERY -->
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
<!-- /SECTION:19_SCRIPT_DELIVERY -->
