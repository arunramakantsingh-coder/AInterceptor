# R-Diagnose-Becomes-Command

When an AI or human performs a diagnostic step (query, script, manual
inspection) to investigate a live issue:

  1. First check `backend/app/api/command_tree.py` — does a command
     already cover this?
  2. If yes: use it. If it fails, improve it in place.
  3. If no: either add it now, or add a `built: false` entry with a
     TODO marker in the same commit as the diagnosis.
  4. Never let a one-off diagnostic stay ad-hoc.

Rationale: the command surface is the institutional memory of how we
investigate. Every ad-hoc grep is technical debt.
