# Generic AI Project Kickoff Standard

## Purpose

Reusable baseline for starting or taking over any repository-based software project. Project-specific rules may be stricter, never weaker.

## Rule 0 — Do Not Code First

Before implementation, establish the repository, product purpose, architecture boundaries, requirements, development workflow, validation strategy, security baseline, Git model, milestone model and handover mechanism.

## Phase A — Repository Discovery

1. Identify repository and remote.
2. Identify default and active branches.
3. Inspect working tree state where available.
4. Record current HEAD and latest release/tag.
5. Inventory existing application, infrastructure, tests and documentation.
6. Identify existing agent instructions and governance files.

## Phase B — Source of Truth

Establish precedence between:

1. platform/legal/security constraints;
2. project governance;
3. agent instructions;
4. current implementation/runtime evidence;
5. requirements;
6. architecture/blueprint;
7. roadmap;
8. historical documents.

Never use stale documentation to overwrite verified repository or runtime facts.

## Phase C — Framework Bootstrap

Minimum documents:

- README.md
- AGENTS.md
- BLUEPRINT.md
- PROJECT/REQUIREMENTS.md
- PROJECT/ARCHITECTURE.md
- PROJECT/ROADMAP.md
- TEST/STRATEGY.md
- PROJECT/GOVERNANCE.md
- .ai/CURRENT_TASK.md
- .ai/HANDOFF.md
- .ai/KNOWN_ISSUES.md

## Phase D — Architecture

Document:

- product boundary;
- major subsystems;
- interfaces/contracts;
- data ownership;
- security boundaries;
- external dependencies;
- deployment boundaries;
- observability;
- failure/recovery paths;
- prohibited architectural shortcuts.

## Phase E — Development Governance

Use:

```text
PLAN
→ FRAMEWORK
→ BLUEPRINT / ARCHITECTURE
→ IMPLEMENT
→ VALIDATE
→ REVIEW
→ COMMIT
→ PUSH
→ REMOTE VERIFY
→ DOCUMENT CHECKPOINT
```

## Phase F — Milestones

Every milestone has an objective, scope, dependencies, acceptance criteria, tests, risks, known defects, target version and Git checkpoint.

## Phase G — Defects

Track defects with severity, priority, affected component, detected version/commit, reproduction, evidence, root cause, fix, regression test and verification evidence.

## Phase H — Git Safety

Never force-push or rewrite shared history as a normal workflow. Verify branch and remote before mutation. Prefer reversible commits and explicit checkpoints. Never commit secrets.

## Phase I — AI Agent Conduct

AI agents must inspect current source before modifying it, make the smallest coherent change, state assumptions, never fabricate test results, and leave durable documentation for the next agent.

## Phase J — Completion Gate

A milestone is complete only when implementation, tests, security review, Git checkpoint, remote verification and documentation are complete.
