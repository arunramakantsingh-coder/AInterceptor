# Prompt for the next AI assistant chat

Paste this along with docs/HANDOVER.md (the attached file) into a
fresh chat. Read the handover first. Then proceed.

---

I am continuing work on the AInterceptor project. Read the attached
HANDOVER.md fully before touching anything.

Current HEAD: a0a54d6
Branch:       fix/cli-chat-provider-gate-cisco-shell
VM:           ssh arun@100.82.62.82  |  cd ~/ainterceptor  |  source .venv/bin/activate

Non-negotiable rules (from .ai/rules/ and .ai/RULES.md):

  R10  Provider isolation. Never edit web_runtime_base.py to fix a
       one-provider issue. Provider files are sacrosanct.
  R11  Performance priority. No polling/sleeping on the hot path.
  R12  CLI/Web/engine talk HTTP only, no cross-imports.
  R13  Surgical evolution. No rewrites.
  R14  Simplify before extend.
  R15  Every diagnostic becomes a command in command_tree.py.
  R1   PROGRESS.md on every milestone commit.
  R3   Docs before push.
  R6   Session log on every decision.

I want to work through the TODO list in docs/HANDOVER.md §7, in
order, ONE THING AT A TIME. Do not bundle changes. Verify after
each step before proceeding.

First item: systemd user units for the daemon, dsh, and redirect.

Confirm you have read the handover, then propose the systemd design
before writing any code.
