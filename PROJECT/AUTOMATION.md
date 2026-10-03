# AInterceptor — Automation Design

Status: design. Not built.

## Goal
Every commit leaves CHANGELOG / ROADMAP / BUGS / PROGRESS consistent with code.

## Non-goals
Auto-push, auto-commit, history rewrite, prose auto-editing.

## Mechanism
git commit -> .git/hooks/post-commit -> sync_docs --last-commit -> doc updates
Recursion guard: AINT_SKIP_SYNC=1

## Commit-message tags
[roadmap:phase-a]   ROADMAP status=done
[closes:B005]       BUGS + KNOWN_ISSUES: Open -> Resolved
[bug:B006]          BUGS: create B006
[release:v0.2.0]    git tag + CHANGELOG version heading
[feature:foo]       FUTURE_WORK append

## Commands (planned)
sync_docs --last-commit
sync_docs --since <ref>
aprogress
asession "title" "body"
arelease <version>

## Rollout
1. sync_docs --dry-run
2. Hook + ROADMAP + CHANGELOG updates
3. aprogress
4. asession
5. release flow
6. Bug table automation
