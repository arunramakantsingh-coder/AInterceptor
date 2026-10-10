# AInterceptor - Session Handover

Last updated: 2026-10-10 (evening)
HEAD:        a0a54d6  fix(cli): bridge ops.py to admin_cli + feat(cli): atest osi <provider>
Branch:      fix/cli-chat-provider-gate-cisco-shell
Purpose:     resume cleanly in a fresh chat. Read this before touching anything.

================================================================
0. WHAT AINTERCEPTOR IS
================================================================

AInterceptor is an AGENT. It owns access: files, shell, network,
targets, credentials, browser sessions. It is the thing that acts.

AIPs (DeepSeek, Claude, Gemini, ChatGPT, others) are INTERCHANGEABLE
REASONING ENGINES. Chosen per-request by the router. They receive a
prompt, return text. They never hold a credential, never touch a
target, never execute a tool.

The SHIM translates OpenAI-shaped tool calls to each AIP's native
syntax (DeepSeek: <||DSML||>; others have their own). Per Rule 10,
that syntax lives in the provider's own file.

================================================================
1. CURRENT STATE
================================================================

  AInterceptor daemon           OK   python -m app.runtime.daemon, :8000
  /v1/chat/completions          OK   OpenAI-compatible, chat + tools
  DeepSeek via /v1              OK   ~15-25s warm (AIP-internal, not ours)
  Claude via /v1                --   parked (CF challenge on tab)
  Gemini via /v1                --   parser sometimes empty
  ChatGPT via /v1               --   parked (WebSocket capture needed)
  dsh harness (VM) on :3080     OK   served via Tailscale
  /harness URL stable           OK   https://ainterceptor.taila2310c.ts.net/harness/
  atest osi <provider>          OK   L3/L4/L6/L7 latency probe
  CLI dispatcher (ops.py)       OK   falls through to admin_cli

================================================================
2. WHAT HAPPENED TODAY (lessons)
================================================================

Attempted to improve streaming latency by adding a DOM-poll on the
hot path. Result: slower, and it broke Claude + Gemini via the shared
base class. Reverted. Three rules violated, all now explicit:

  R10  Provider isolation. Never edit web_runtime_base.py to fix a
       one-provider issue. Shared base is provider-neutral only.
       Provider-specific streaming/parsing lives in the provider's
       own __init__.py.

  R11  Performance priority. The hot path is dispatcher.stream_reply
       -> runtime.execute -> prompt submit -> response capture ->
       first delta. Nothing inside it may poll, sleep, re-scan,
       re-render, or log unless load-bearing.

  R15  Diagnose becomes command. Every ad-hoc diagnostic must be
       promoted to a command in command_tree.py in the same commit.
       No one-off scripts stay.

Root cause of "why slow": the AIP thinks, not the network. Measured
end-to-end: network floor is ~600ms (DNS+TCP+TLS+TTFB). Everything
above that is the model generating. Nothing on our side fixes it.

Second finding: the AIP's web page carries the conversation. Every
/v1 call appends to the same tab's chat. Over dozens of calls, the
chat history grows to hundreds of thousands of tokens and each reply
gets slower. This is why "158s" happened. Fix is to rotate to a new
chat when the history gets long (not built yet; on TODO).

================================================================
3. CLI ARCHITECTURE (the puzzle from today)
================================================================

Two dispatchers exist:

  backend/scripts/ops.py        Extended admin. Handles: asessions,
                                ahealth, aversion, alogs, aevidence,
                                astart, arestart, astop, abootstrap,
                                asave, aconfig-reset. Falls through
                                to admin_cli when the command is
                                not recognized (added a0a54d6).

  backend/scripts/admin_cli.py  Core admin. Handles: providers, login,
                                logout, show, hide, test, config.

  Every ~/bin/a* wrapper calls scripts.ops, which strips the leading
  "a" and forwards to admin_cli when needed.

  R12 DEBT: admin_cli.py imports backend modules in-process instead
  of talking to /internal/* over HTTP. Fix when a second consumer
  exists, not before. Noted but not urgent.

To add a new command:
  1. Handler in ops.py or admin_cli.py (whichever fits).
  2. Entry in backend/app/api/command_tree.py (same commit, R15).
  3. Wrapper in ~/bin/ if it needs a short name.
  4. Document in docs/COMMANDS.md (R3).

================================================================
4. RULES THAT BIND (from .ai/rules/)
================================================================

  R10  provider-isolation.md          -> one file per provider
  R11  performance-priority.md        -> hot path is sacred
  R12  module-split.md                -> CLI/Web/engine talk HTTP only
  R13  surgical-evolution.md          -> no rewrites, evolve
  R14  simplify-before-extend.md      -> remove code to add features
  R15  diagnose-becomes-command.md    -> no one-off scripts
  R16  provider-account-registry.md
  R17  docs-are-living.md

Plus .ai/RULES.md (R1-R7): PROGRESS.md on every milestone, tag-based
commit automation, docs before push, pasteable scripts, future work
in .ai/FUTURE_WORK.md, session log on every decision, automate.

================================================================
5. LAYOUT
================================================================

  backend/app/
    api/chat_routes.py           /v1/chat/completions
    control_plane/router.py      select(model) + alias map
    interception/<provider>/     per-provider (R10)
    interception/web_runtime_base.py  SHARED - keep neutral
    runtime/daemon.py            process entry point
    runtime/dispatcher.py        Path A / Path B selection
    runtime/browser_supervisor.py  Chrome + CDP
    runtime/session_exporter.py  cold backup every 300s
    runtime/session_importer.py  apply exports (opt-in on boot)
    runtime/tool_shim.py         OpenAI <-> text tool protocol
    agent/                       AInterceptor-native agent layer

  backend/scripts/
    ops.py                       extended admin dispatcher
    admin_cli.py                 core admin dispatcher
    osi_probe.py                 OSI latency probe (called by atest)
    chat_any.py                  CLI chat REPL

================================================================
6. ENVIRONMENT
================================================================

  VM:              ssh arun@100.82.62.82  |  cd ~/ainterceptor
  Activate:        source .venv/bin/activate
  Restart daemon:  arestart
  Status:          astatus / ahealth
  OSI probe:       atest osi <provider>
  API key:         sk-aint-0LcsVpp9OmAiiW4rOcQnE88ei4Ga4k2TCVt8KoBF
  dsh token file:  ~/deepseek-harness/dsh-url.txt
  dsh start:       ~/bin/dsh-start
  VNC redirect:    ~/bin/dsh-redirect (port 3081 -> tailscale /harness)
  Credential vault: ~/.dsh/.credentials.yaml

================================================================
7. NEXT (priority order)
================================================================

1. systemd user units for daemon + dsh + redirect.
   loginctl enable-linger arun.
   Makes every state change (reboot, resume, crash) come back.

2. Rebrand to AIN.
   Remove "DeepSeek Harness" and "OpenRouter" strings from the UI.
   Codename: AIN (AI Interceptor Node).

3. Planner-mode system prompt.
   When AGENT_EXECUTION=1, replace the "you are an agent with limited
   permission" framing with "you are a planner; the operator owns
   everything; AInterceptor executes under their permission model."
   Stops AIP refusals on operational tasks (EVE-NG, Cisco, ops).

4. Interactive permission gate.
   Replace the static allowlist in agent/permissions.py with a queue.

5. EVE-NG target connector.

6. Chat rotation.
   When the provider's page chat grows beyond N turns, open a new
   chat automatically. Fixes the accumulated-history slowdown.

================================================================
8. SNAPSHOTS (VirtualBox)
================================================================

  v0.2.3-harness-url-stable       latest, clean, known-good
  v0.2.2-stream-fix
  v0.2.1-agent-layer-released
  v0.2.0-agent-layer
  good-20261008-pre-app-layer
  good-20261007-agents-working

Restore:  VBoxManage snapshot "AInterceptor" restore "<name>"

================================================================
9. GIT TAGS
================================================================

  v0.2.3-harness-url-stable      7084256
  v0.2.2-stream-fix              dff1be7
  v0.2.1-agent-layer             12e6ee1

Uncommitted-but-pushed: a0a54d6 (CLI bridge + atest osi)

================================================================
10. WHAT NOT TO DO
================================================================

- Do NOT edit web_runtime_base.py to fix a one-provider issue.
- Do NOT put polling/sleeps on the hot path.
- Do NOT write one-off diagnostic scripts — make them commands.
- Do NOT "improve" while fixing a bug. One change at a time.
- Do NOT edit Claude without explicit operator approval.
- Do NOT mount dsh under a URL subpath (its /api calls go to root).
- Do NOT pkill -9 Chrome (cookies won't flush).

END
