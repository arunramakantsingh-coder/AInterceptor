# AInterceptor — Developer Governance Control Plane

## Purpose

The Developer section is the application's engineering control plane. It provides an auditable view of project state and GitHub-backed development evidence.

## Primary Views

### 1. Overview

Show:

- product version;
- current milestone;
- project status;
- active branch;
- HEAD SHA;
- latest checkpoint;
- CI state;
- open blockers;
- critical/high defects;
- current roadmap stage;
- next action;
- last remote verification.

### 2. Git

Show and compare:

- branches;
- commits;
- tags/releases;
- commit ancestry;
- changed files;
- pull requests;
- CI/checks;
- ahead/behind/diverged state.

Every displayed Git fact must identify its source and observation time.

### 3. Checkpoints

A checkpoint binds:

```text
Product Version
+ Milestone
+ Module Version
+ Branch
+ Commit SHA
+ Validation Result
+ Security Result
+ Documentation State
```

A checkpoint is not valid merely because a commit exists.

### 4. Roadmap

Render milestone sequence, status, dependencies, acceptance criteria, defects, blockers and Git checkpoints.

### 5. Bugs

Render GitHub Issues with project fields for severity, priority, component, affected version/commit, evidence, root cause, fix and verification.

### 6. Architecture / ADR

Show architecture baseline, subsystem boundaries, active ADRs and superseded decisions.

### 7. Provider / Interceptor Status

Show provider runtime state separately from Orchestrator state:

- provider;
- runtime version;
- session status;
- transport status;
- last successful interception;
- stream health;
- active errors;
- capability status.

No provider credential or session secret may be displayed.

### 8. Validation

Show actual observed test/build/security results and their commit SHA. `PASS` requires evidence.

### 9. Handover

Show current AI/human handover, exact branch/commit, completed work, blockers, known issues, decisions and next action.

## Git Mutation Safety

The UI may expose Git operations only through explicit workflows.

Safe default actions:

- inspect commit;
- compare commits;
- create branch from commit;
- create recovery branch;
- create PR.

Protected actions:

- revert;
- merge;
- branch deletion;
- branch repointing;
- history rewriting.

Protected actions require target visibility, confirmation, reason and audit record. Force-push is disabled by project policy.

## Data Model Direction

The control plane should maintain durable project metadata for:

- `project_state`
- `milestone`
- `module_version`
- `checkpoint`
- `defect_reference`
- `architecture_decision`
- `validation_run`
- `handover_record`
- `audit_event`

GitHub remains the source of truth for Git objects, issues and pull requests. AInterceptor stores references and project-specific metadata rather than copying Git history into a competing database.

## Integration Boundary

```text
Developer UI
     |
     v
Control Plane Service
     |
     +---- GitHub adapter
     +---- Project metadata store
     +---- Validation evidence
     +---- Audit service
```

The frontend must not call GitHub directly with privileged credentials.

## Future Implementation Gate

Do not implement destructive Git controls until authentication, authorization, audit logging, CSRF protection, confirmation workflows and GitHub permission handling are defined and tested.
