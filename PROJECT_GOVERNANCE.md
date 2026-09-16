# AInterceptor — Project Governance

Status: GOVERNANCE FOUNDATION
Version: 0.1.0

## 1. Purpose

AInterceptor is a web application that acts as an AI router by communicating with multiple AI providers through their public web-layer interaction surfaces rather than provider APIs. The product abstracts provider selection and execution behind a common application experience while preserving provider-specific web communication inside controlled interception runtimes.

The repository is the engineering source of truth. This document is the developer-facing control plane for project state, versioning, milestones, defects, architecture changes, validation and GitHub checkpoints.

## 2. Core Product Boundary

AInterceptor is NOT an API-key aggregation gateway that calls OpenAI, Claude, Gemini, DeepSeek or similar provider APIs directly.

The intended execution model is:

```text
User / Client Application
        |
        v
AInterceptor Web Application
        |
        v
Interception / Routing Layer
        |
        +---- Provider Web Session A
        +---- Provider Web Session B
        +---- Provider Web Session C
        |
        v
Provider public web interaction layer
```

The system must not depend on extracting provider webpage response text from rendered provider pages as its core product mechanism. Provider web sessions are communication endpoints; AInterceptor owns the intercepted request/response transport path and normalized application contract.

## 3. Governance Precedence

1. Platform, legal, security and provider terms/requirements.
2. This governance baseline.
3. `AGENTS.md` and AI operating rules.
4. `BLUEPRINT.md` and `PROJECT/ARCHITECTURE.md`.
5. `PROJECT/REQUIREMENTS.md`.
6. `PROJECT/ROADMAP.md`.
7. Milestone-specific records and approved decisions.
8. Implementation and runtime evidence.

Any project-specific exception must document reason, scope, risk/mitigation, approval and expiry/review date.

## 4. Repository Development Model

Development occurs through small, coherent, reversible checkpoints.

```text
PLAN
 -> BLUEPRINT / ARCHITECTURE
 -> IMPLEMENT
 -> LOCAL VALIDATE
 -> SECURITY / INTEGRITY REVIEW
 -> REVIEW GIT DIFF
 -> COMMIT
 -> PUSH
 -> REMOTE VERIFY
 -> DOCUMENT CHECKPOINT
 -> NEXT MILESTONE
```

A milestone is not complete merely because code compiles or an AI agent reports success.

## 5. GitHub State Tracking

The Developer Governance page in the AInterceptor web application must read repository state from GitHub and expose, at minimum:

- current repository;
- active development branch;
- current HEAD commit and short SHA;
- previous milestone checkpoint;
- latest tag/release;
- ahead/behind/diverged state against the configured baseline;
- commit history for the active milestone;
- changed-file summary;
- open pull requests;
- open bugs/issues;
- CI/check status;
- roadmap checkpoint status;
- current project version;
- current milestone/module;
- last verified remote checkpoint;
- rollback/recovery references.

The application must distinguish **observed GitHub state** from locally inferred or manually entered project state.

## 6. Version Model

Maintain four levels where applicable:

- Product version: `MAJOR.MINOR.PATCH`
- Architecture milestone: `M#` / named milestone
- Module version: module-specific semantic version
- Git checkpoint: commit SHA/tag

Example:

```text
Product:       v0.1.0
Milestone:     M1 Web Interception Foundation
Module:        web-interceptor v0.1.0
Checkpoint:    abc1234
```

Every release-worthy milestone must map to a Git commit and preferably a Git tag.

## 7. Rollback / Forward Navigation

The Developer Governance UI may provide repository navigation actions, but every mutation must be explicit and auditable.

Allowed operations should be separated into:

### Inspect

- view commit;
- compare commits;
- view branch;
- view changed files;
- view tags/releases;
- inspect CI result.

### Prepare

- create development branch;
- create rollback branch from a known-good commit;
- create release/checkpoint metadata;
- create PR.

### Mutate — protected

- reset/repoint branch;
- revert commit;
- close/delete branch;
- merge PR.

Destructive Git operations must never be triggered by a single casual UI click. They require confirmation, target SHA/ref visibility, reason capture and audit logging. Force-push and history rewrite remain disabled by default.

## 8. Current State Record

The Developer Governance page must maintain a structured current-state record:

```yaml
project_status: FOUNDATION / DEVELOPMENT / VALIDATION / RELEASE / BLOCKED / MAINTENANCE
product_version: 0.1.0
milestone: M0
active_branch: main
head_commit: <observed SHA>
last_verified_commit: <observed SHA>
roadmap_stage: <stage>
open_blockers: []
open_critical_bugs: []
last_validation: <timestamp + result>
last_remote_checkpoint: <timestamp + result>
next_action: <one concrete action>
```

## 9. Bug / Defect Governance

Use GitHub Issues as the durable defect system. Each defect should contain:

- bug ID / issue number;
- title;
- severity;
- priority;
- affected milestone/module;
- detected version/commit;
- environment;
- reproduction steps;
- expected behavior;
- actual behavior;
- evidence;
- root cause;
- fix commit/PR;
- regression test;
- status;
- verification commit.

Severity and priority are independent fields.

Critical/security defects block milestone completion until disposition is recorded.

## 10. Roadmap Governance

`PROJECT/ROADMAP.md` is the authoritative milestone sequence. The Developer Governance UI should render roadmap state from repository metadata plus GitHub issues/PRs and explicit milestone records.

Each milestone must include:

- objective;
- scope;
- dependencies;
- planned components;
- acceptance criteria;
- validation evidence;
- known risks;
- open defects/blockers;
- checkpoint commit/tag;
- completion status.

## 11. Architecture Decision Governance

Material architecture decisions must be recorded as ADRs under `PROJECT/ADR/`.

Each ADR contains:

- decision ID;
- date;
- status;
- context;
- decision;
- alternatives considered;
- consequences;
- security implications;
- migration/rollback implications.

Do not leave material architectural decisions only in chat.

## 12. Change Control

Before a material implementation change, record:

```text
Why is the change required?
What current component owns the behavior?
What contracts change?
What data/state is mutated?
What security boundary changes?
What is the rollback point?
How will the change be validated?
```

Prefer extend -> refactor -> fix. Avoid unrelated cleanup in milestone commits.

## 13. Verification Gate

Default milestone acceptance gate:

- source inventory: PASS;
- static/source review: PASS;
- configuration/schema validation: PASS;
- unit/functional tests: PASS;
- negative/edge tests: PASS;
- integration tests: PASS;
- end-to-end tests: PASS where applicable;
- security/integrity review: PASS;
- regression suite: PASS;
- Git diff review: PASS;
- commit: PASS;
- push: PASS;
- remote verification: PASS;
- documentation/roadmap checkpoint: PASS.

Non-applicable gates must be recorded as `N/A` with a reason.

## 14. Security and Provider Boundary

AInterceptor must not store or expose provider credentials/session material in source control, browser logs, GitHub issues or normal application telemetry.

Provider-specific web communication must be isolated behind explicit runtime boundaries.

The project must document and verify that each supported provider integration is technically and legally permissible for the intended use. Do not assume that public accessibility means unrestricted automation is permitted.

## 15. Developer Governance UI — Required Sections

The Developer section should contain these primary views:

1. **Project Overview** — version, stage, active milestone, health, current branch and HEAD.
2. **Git Control** — branches, commits, tags, compare, checkpoint and protected rollback/revert workflows.
3. **Roadmap** — milestone timeline, progress, dependencies and gates.
4. **Bug Tracker** — GitHub issues, severity, status, owner, regression state.
5. **Pull Requests** — review state, checks and changed files.
6. **CI / Validation** — latest workflows, pass/fail evidence and blocked gates.
7. **Architecture** — architecture map and ADR index.
8. **AI Agent Control** — active rules, agent status, takeover/handover context and permitted actions.
9. **Audit Trail** — governance actions performed through the application.
10. **Release / Checkpoints** — versions, tags, milestone commits and rollback references.

## 16. GitHub Integration Contract

GitHub integration must use a provider-neutral repository service inside AInterceptor. The UI must not embed raw GitHub API logic directly into components.

Conceptual contract:

```text
GitHubRepositoryService
  -> repository()
  -> branches()
  -> commits()
  -> compare()
  -> issues()
  -> pull_requests()
  -> checks()
  -> tags/releases()
  -> create_branch()
  -> create_pr()
  -> create_checkpoint_metadata()
```

Mutation methods must be permission-aware and audit logged.

## 17. Milestone Checkpoint Record

Every milestone checkpoint should produce a machine-readable record under `PROJECT/CHECKPOINTS/`:

```yaml
checkpoint_id: M0-001
milestone: M0
product_version: 0.1.0
commit: <SHA>
branch: <branch>
implemented: PASS
validation: PASS
security_review: PASS
git_review: PASS
remote_verified: PASS
known_bugs: []
known_blockers: []
next_action: <action>
```

## 18. AI-Agent Governance

AI agents are implementation assistants, not autonomous project owners.

Every agent must:

- read `AGENTS.md` and project control documents first;
- inspect current GitHub state before modifying code;
- distinguish verified facts from assumptions;
- avoid destructive Git operations unless explicitly authorized;
- never claim remote state, tests or deployment status without evidence;
- update project documentation when material behavior changes;
- stop at the defined task boundary.

## 19. Deployment Governance

Development, test and production environments must be distinct.

Deployment records must identify:

- source commit/tag;
- environment;
- build artifact/image;
- configuration version;
- migration state;
- validation result;
- deployment timestamp;
- rollback target.

No deployment is considered complete without recording its source commit and validation result.

## 20. Rule for This Project's Special Architecture

AInterceptor's defining architectural property is the interception boundary:

```text
Application request
      ↓
Web interception boundary
      ↓
Provider session transport
      ↓
Provider public web interaction surface
```

The system should treat the provider web session as a transport endpoint, not as the application's UI. AInterceptor owns the client experience, routing decision, session selection, transport lifecycle, normalization contract and governance. Provider-specific DOM/page structure must not leak into the core routing contract.

## 21. Reference Projects

CareerOS and CyberOS are architectural inspiration only. Useful ideas include repository-native AI instructions, handover/control documents, milestone gates, explicit source-of-truth rules, worker separation and infrastructure documentation. Their product-specific rules, domains and data models do not automatically apply to AInterceptor.

## 22. Mandatory Bootstrap Documents

The minimum project control set is:

```text
README.md
AGENTS.md
BLUEPRINT.md
PROJECT/REQUIREMENTS.md
PROJECT/ARCHITECTURE.md
PROJECT/ROADMAP.md
PROJECT/GOVERNANCE.md
PROJECT/TESTING.md
PROJECT/ADR/README.md
PROJECT/CHECKPOINTS/README.md
.ai/agents/README.md
.ai/procedures/README.md
.ai/rules/README.md
.ai/handover/README.md
```

## 23. Governance Status Vocabulary

Use controlled values:

```text
PLANNED
IN_PROGRESS
VALIDATION
BLOCKED
READY_FOR_CHECKPOINT
CHECKPOINTED
RELEASED
DEPRECATED
```

## 24. Principle

AInterceptor development must always answer four questions from the repository and GitHub:

```text
Where are we?
What changed?
What has been proven?
What is the safe next checkpoint?
```
