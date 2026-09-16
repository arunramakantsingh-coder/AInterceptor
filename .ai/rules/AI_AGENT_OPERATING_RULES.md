# AInterceptor — AI Agent Operating Rules

## 1. Read Before Acting

Read, in order:

1. `AGENTS.md`
2. `PROJECT_GOVERNANCE_STANDARD_v1.1.md`
3. `PROJECT_GOVERNANCE.md`
4. `BLUEPRINT.md`
5. `PROJECT/REQUIREMENTS.md`
6. `PROJECT/ARCHITECTURE.md`
7. `PROJECT/ROADMAP.md`
8. `.ai/CURRENT_TASK.md`
9. `.ai/KNOWN_ISSUES.md`
10. `.ai/HANDOFF.md`
11. relevant subsystem rules.

## 2. Investigate Before Changing

Trace the actual implementation path before proposing a fix:

```text
UI → API/Gateway → Orchestrator → Interface → Interceptor → Provider Runtime → Transport
```

Do not guess at missing implementation.

## 3. Change Discipline

- Make the smallest coherent change.
- Preserve subsystem boundaries.
- Do not perform unrelated cleanup.
- Do not silently change requirements.
- Do not replace architecture merely because a shortcut is easier.

## 4. Evidence Discipline

Never state that a test, build, Git operation, runtime check, or deployment succeeded unless evidence was actually observed.

Use explicit states such as `PASS`, `FAIL`, `BLOCKED`, `NOT RUN`.

## 5. Script Discipline

Repository-changing work must follow the project's single pasteable, reproducible script policy. Scripts must be safe, explicit, idempotent where possible, and must not contain secrets.

## 6. Git Discipline

Verify repository, branch, remote and current state before milestone operations. Never force-push. Prefer reversible commits and named checkpoints.

## 7. Security Discipline

Never expose provider session secrets, cookies, authentication headers, tokens, API keys, or private configuration in source, logs, fixtures, screenshots or commits.

## 8. Provider Boundary

Do not add provider inference APIs to bypass the web-interception architecture. Provider-specific behavior belongs inside provider runtimes and explicit interception interfaces.

## 9. Handover

At the end of a meaningful task, record exact branch, commit, changes, tests, known issues, blockers, decisions and next action in the project handover record.

## 10. Stop Condition

When the requested task is complete and validated, stop. Do not expand scope without instruction.
