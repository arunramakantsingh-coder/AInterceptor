# AInterceptor — Project Rules

Binding for every human and AI contributor.

## R1 — Progress report on every milestone commit

After every commit that closes a milestone, feature, fix, or phase:

  1. Update `.ai/PROGRESS.md` with:
     - what shipped (one line per commit)
     - what's now working end-to-end
     - known issues opened / closed
     - next-session candidates (reranked)
  2. Stage + commit PROGRESS.md in the same commit OR an immediate
     follow-up (`docs(progress): ...`).
  3. The PROGRESS.md is the durable "where are we" file. Chat history
     does not count.

Small commits (typo, version bump) may skip. Rule applies to any commit
that changes behavior, adds a feature, fixes a bug, or completes a phase.

## R2 — Commit message tags drive automation

Commit messages follow:

  <type>(<scope>): <summary>

  type:   feat | fix | docs | chore | test | refactor | perf | release
  scope:  phase-a | phase-b | ... | cli | agent | v1 | providers | auth | ...

Special markers recognised by tooling:

  [roadmap:phase-a]      update ROADMAP.md phase A status
  [bug:B005]             reference bug tracker entry B005
  [closes:B005]          close bug B005 (moves to Resolved)
  [release:v0.2.0]       tag + GitHub release + CHANGELOG
  [feature:new-name]     add to "upcoming features" list

## R3 — Docs before push

Every push must leave the repo's docs consistent with the code:
- `PROJECT/CHANGELOG.md` — reflects new commits (auto or manual)
- `PROJECT/ROADMAP.md` — phase status current
- `.ai/PROGRESS.md` — latest milestone reflected
- `docs/COMMANDS.md` — any new CLI command documented

If a doc update would break the commit, do it in a follow-up.

## R4 — Every change is a pasteable script (Section 18)

See PROJECT_GOVERNANCE_STANDARD_v1.1.md Section 18.
No exceptions for milestone work.

## R5 — Deferred items go in .ai/FUTURE_WORK.md

Ideas, "we should later", "not now but important" — all land in
`.ai/FUTURE_WORK.md`, not in chat history, not in comments.


## R6 — Session log on every decision

Any time we choose between options — even obvious ones — append an entry
to .ai/SESSION_LOG.md with: Title, Context, Options, Chosen, Why, Drift,
Impact. Durable record across chat sessions.

## R7 — Automation by default

Manual doc updates are a failure mode. When a task CAN be automated,
prefer the automated path even if it costs extra work now. Track gaps in
PROJECT/AUTOMATION.md.
