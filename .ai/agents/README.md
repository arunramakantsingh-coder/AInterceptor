# .ai/agents/

Role definitions for the AIN multi-agent model.

Each file describes one role: what it may read, write, execute, and
what it must escalate. The orchestrator (future) picks a role per
task based on this directory.

Status: folders created 2026-10-12. Role files not yet written.

Planned files:
  orchestrator.md    decides which role handles a task
  architect.md       reads repository, writes architecture docs, no exec
  developer.md       reads repo, writes src/, runs tests
  reviewer.md        reads repo, no write, runs tests only
  security.md        reads repo, no write, audits and reports
