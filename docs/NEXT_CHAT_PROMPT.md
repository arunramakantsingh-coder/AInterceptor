# Prompt for the next AI assistant chat

Paste this along with docs/HANDOVER.md (attachment) into a fresh chat.
Read the handover first, then execute.

---

I am continuing work on AInterceptor. Read the attached HANDOVER.md
fully before touching anything.

Current HEAD: ffcfb1e
Branch:       fix/cli-chat-provider-gate-cisco-shell
VM:           ssh -i ~/.ssh/id_ed25519_ainterceptor arun@100.82.62.82
              cd ~/ainterceptor  |  source .venv/bin/activate

Shipped 2026-10-12 (this cycle):
  1.3  Daemon import isolation (821b880)
  2.1  Permission gate wrapper-peeling (efd1dda)
  2.2  Chat rotation: arotate + auto-rotate at
       AINTERCEPTOR_ROTATE_TURNS=25 (ffcfb1e)

Non-negotiable rules (from .ai/rules/ and .ai/RULES.md):

  R10  Provider isolation. Never edit web_runtime_base.py to fix a
       one-provider issue. Never embed operator-specific knowledge
       (ports, machine names, conventions) in shipped code. The
       permission gate is the ONLY place that decides.
  R11  Performance priority. No polling/sleeping on the hot path.
  R12  CLI/Web/engine talk HTTP only, no cross-imports.
  R13  Surgical evolution. No rewrites.
  R14  Simplify before extend.
  R15  Every diagnostic becomes a command in command_tree.py.
  R1   PROGRESS.md on every milestone commit.
  R3   Docs before push.
  R6   Session log on every decision.

Rules learned 2026-10-12 (fold into .ai/rules/ when you have a moment):
  - One command at a time when the command writes/patches/restarts.
    Read-only diagnostics may be batched.
  - Every write command must fail closed: pre-flight checks first,
    abort WITHOUT writing if the anchor doesn't match.

Operator rule: do NOT start item 1.1 or 1.2 without a fresh chat
and a clean snapshot. This chat IS that fresh chat — the tree was
clean at ffcfb1e when the previous session stopped.

Before starting work:
  1. Run: curl -s -o /dev/null -w "daemon: %{http_code}\n" http://127.0.0.1:8000/health
  2. Run: timeout 5 ssh -o BatchMode=yes Arun@100.67.225.84 "hostname"
     Expect: DESKTOP-9S3SKGC
  3. Read docs/LLD_AGENT_ARCHITECTURE.md to understand the current
     five-layer design of the agent.
  4. Record a clean snapshot (git status, /health, astatus) in
     PROGRESS.md before touching item 1.1.

Next task: item 1.1 — on-demand provider tabs (the biggest
resource win; the daemon currently opens one tab per provider at
boot and keeps them forever). See docs/TODO.md and HANDOVER.md
section 4 for the full description. After 1.1: item 6.1
(agent-login default), then item 1.2 (AIN-native chat).

Do not start any large task without confirming state.
