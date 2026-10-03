# AI Collaboration & Project Governance

Status: Living document. Update in place. Never recreate from scratch.
Last updated: 2026-10-03

## Truth hierarchy

  1. Git (GitHub)     - source of truth for code and docs
  2. VM snapshots     - safety net, not a source of truth
  3. .ai/ docs        - design authority for decisions
  4. Chat transcripts - context only, never authoritative

## Workflow

  - Chat (any AI) produces one PowerShell or bash script
  - VS Code SSH on the VM runs it: writes files, commits, pushes
  - GitHub reflects the change
  - Admin page (/dashboard/docs) renders the docs

Rules for scripts:
  - one script per commit
  - idempotent (skip if already applied)
  - paste-safe (heredocs over SSH must be short; long ones mangle)
  - validates after writing (parse check, import check)
  - prints local HEAD + remote HEAD for verification

## Snapshot protocol

Before risky change:
  VBoxManage snapshot "AInterceptor" take "pre-<desc>"

After verified working:
  VBoxManage snapshot "AInterceptor" take "good-<YYYYMMDD>-<desc>"

On failure:
  VBoxManage snapshot "AInterceptor" restore "pre-<desc>"

## GitHub protocol

  - every working change: one commit, one push
  - commit tags drive docs: [feature:x] [bug:Bxxx] [rule:y]
    [provider:z] [docs:scope] [wip:scope]
  - post-commit hook updates .ai/PROGRESS.md and .ai/KNOWN_ISSUES.md
  - after every push verify:
        git rev-parse HEAD == git ls-remote origin <branch>

## AI agent rules

  1. Read PROJECT/AIF_MASTER_DESIGN.md first
  2. Read .ai/rules/* before proposing anything
  3. Never invent rules; if missing, ask
  4. Never rewrite a doc; amend in place with a dated section
  5. Never touch code without a rule or ADR justifying the change
  6. Every hot-path change must be measured (R-Performance-Priority)
  7. Do not split a module that doesn't work yet (R-Surgical-Evolution)
  8. Every diagnosis becomes a command, or a TODO on the command page
     (R-Diagnose-Becomes-Command)

## Canonical source

The VM is canonical for AInterceptor work. The Windows clone is a
stale backup — do not commit from it. airouter-agent will eventually
run as a Windows service, not from a repo clone.
