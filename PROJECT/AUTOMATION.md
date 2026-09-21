# AInterceptor — Automation Design

Status: design. Not built. Track build progress here.

## Goal

Every commit leaves CHANGELOG / ROADMAP / BUGS / PROGRESS consistent
with code — no manual doc-keeping.

## Non-goals

- Auto-push (network surprise)
- Auto-commit (surprise history)
- Rewriting history
- Auto-editing prose that needs judgment

## Mechanism

    git commit
       |
       v
    .git/hooks/post-commit  (symlink from scripts/hooks/post-commit)
       |
       +-- AINT_SKIP_SYNC=1? -> exit (prevents recursion)
       |
       +-- python -m scripts.sync_docs --last-commit
       |       +-- parse commit message for tags
       |       +-- update affected docs
       |       +-- print "[sync] updated: <file>, <file>"
       |
       +-- if PROGRESS.md > 7 days old -> warn "run aprogress"

## Commit-message tags

    [roadmap:phase-a]         ROADMAP.md: phase A status=done, gate=commit
    [closes:B005]             BUGS.md + KNOWN_ISSUES.md: B005 Open -> Resolved
    [bug:B006]                BUGS.md: create B006 if missing
    [release:v0.2.0]          git tag; CHANGELOG version heading
    [feature:oauth-more]      FUTURE_WORK.md: append upcoming feature

Multiple tags allowed. Order independent.

## Commands (planned)

    sync_docs --last-commit        regenerate based on last commit
    sync_docs --since <ref>        catch-up range
    aprogress                      rebuild .ai/PROGRESS.md from git log
    asession "title" "body"        append decision to SESSION_LOG.md
    arelease <version>             tag + CHANGELOG + GH release

## Doc responsibilities

    CHANGELOG.md     append bullets to [Unreleased]; promote on release
    ROADMAP.md       set phase Status + Gate columns by ID
    BUGS.md          move rows between Open / In Progress / Resolved
    KNOWN_ISSUES.md  sync with BUGS.md (short view)
    PROGRESS.md      full regen from git log
    SESSION_LOG.md   manual via `asession` (prose needs judgment)

## Safety

- Hook is opt-in per clone: scripts/hooks/install.sh
- Uninstallable: rm .git/hooks/post-commit
- Never auto-stages; developer sees "[sync] updated: X" and decides
- AINT_SKIP_SYNC=1 prevents recursion when hook does its own commit

## Rollout order

1. sync_docs --dry-run (print intended edits)
2. Hook installer + real ROADMAP + CHANGELOG updates
3. aprogress
4. asession
5. [release:...] + arelease
6. Bug table automation
