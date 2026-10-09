# AInterceptor - Session Handover

Last updated: 2026-10-10
HEAD:        2bf287a (perf: incremental streaming)
Branch:      fix/cli-chat-provider-gate-cisco-shell
Purpose:     resume cleanly in a fresh chat. Read this before touching anything.

================================================================
0. WHAT AINTERCEPTOR ACTUALLY IS
================================================================

AInterceptor is an AGENT. It holds access -- files, shell, network,
targets, credentials, browser sessions. It is the thing that acts.

AIPs (AI Providers: DeepSeek, Claude, Gemini, ChatGPT, others) are
INTERCHANGEABLE REASONING ENGINES. They are chosen per-request by
the router. They receive a prompt, return text. They never hold a
credential, never touch a target, never execute a tool. They are
one brain behind a wall.

The SHIM translates between AInterceptor's OpenAI-shaped tool
protocol and each AIP's native syntax (DeepSeek emits <||DSML||>,
Claude and Gemini have their own). Rule 18: per-provider syntax
lives in the provider file, not the shim.

This is the architectural invariant. Anything that puts credentials,
targets, or execution on the AIP side breaks the model.

    Client (dsh, curl, CareerOS, phone)
       |  OpenAI /v1 protocol
       v
    AInterceptor  <- owns: targets, creds, sessions, permission gate
       |  shim: OpenAI <-> native AIP syntax
       v
    AIP  <- DeepSeek / Claude / Gemini / ChatGPT
       |  text only. no creds. no targets. no execution.
       v
    reply text -> back to client

================================================================
1. CURRENT STATE - WHAT WORKS
================================================================

  AInterceptor daemon            OK  python -m app.runtime.daemon, port 8000
  /v1/chat/completions           OK  OpenAI-compatible, chat + tools
  DeepSeek (browser/CDP)         OK  primary, streaming
  Claude                         --  parked, CF challenge on tab
  Gemini                         --  parser sometimes empty
  ChatGPT                        --  parked, needs WebSocket capture
  Shim + DSML parser             OK  committed 416e78d
  Agent loop (tools=)            OK  AGENT_EXECUTION=1
  Live streaming deltas          OK  2bf287a
  Stable /harness URL            OK  https://ainterceptor.taila2310c.ts.net/harness/
  dsh harness (VM) on :3080      OK  running
  Session restore on startup     OK  d776284
  Router aliases                 OK  d776284

Tags & snapshots (all pushed):

  v0.2.1-agent-layer        agent loop, targets, connectors
  v0.2.2-stream-fix         SSE frames, agent short-circuit streams
  v0.2.3-harness-url-stable stable URL, session restore, router aliases
  VBox: v0.2.3-harness-url-stable (top of chain)

Remote access:

  Dashboard  https://ainterceptor.taila2310c.ts.net/
  Harness    https://ainterceptor.taila2310c.ts.net/harness/  (redirects to current token)
  Daemon     127.0.0.1:8000 (loopback), 0.0.0.0:8000 on the VM

================================================================
2. LAYOUT - WHERE THINGS LIVE
================================================================

  ~/ainterceptor/backend/app/
    api/
      chat_routes.py          /v1/chat/completions (agent short-circuit here)
    control_plane/
      router.py               select(model) -- alias map + active check
      state.py                which providers are active
    interception/             per-AIP provider files (Rule 18)
      deepseek/__init__.py    SPEC + Runtime + Parser + DSML
      claude/__init__.py      SPEC + Runtime + Parser
      gemini/__init__.py
      chatgpt/__init__.py
      web_runtime_base.py     shared base (browser transport, parser loop)
      web_runtime.py          WebProviderSpec dataclass
    runtime/
      daemon.py               process entry point
      dispatcher.py           Path A / Path B selection + circuit breakers
      browser_supervisor.py   Chrome + CDP lifecycle
      session_exporter.py     writes exports/<provider>.json every 300s
      session_importer.py     applies exports back to live tab
      tool_shim.py            OpenAI <-> text tool protocol
    agent/                    AInterceptor-native agent layer
      loop.py                 ReAct loop: prompt -> tool_call -> exec -> feed
      tools.py                tool catalog + dispatcher (target-aware)
      targets.py              target registry (vm, win-laptop, ...)
      permissions.py          allowlist gate
      approvals.py            client for Windows Helper dialogs
      connectors/             local, ssh, winhelper
    providers_list.py         PATH_A_SUPPORTED, PATH_B_REQUIRED

Environment variables:

  AGENT_EXECUTION=1            turn on the agent loop when tools is set
  AGENT_SHELL_ALLOW=0|1        shell allowlist (keep 0 until gate is real)
  AINTERCEPTOR_PROFILE_DIR     Chrome profile location
  AINTERCEPTOR_EXPORT_DIR      session export JSON dir

================================================================
3. RULES - NEVER BREAK THESE
================================================================

  1. AIPs are interchangeable. No provider-specific logic outside
     interception/<name>/.
  2. Credentials never reach an AIP. They live in the vault; the
     connector fetches them for the duration of a call only.
  3. Rule 18: per-provider syntax in the provider file. DSML regex
     in deepseek/, Claude's syntax in claude/, etc. Not in the shim.
  4. Never widen a client's own sandbox by editing its config from
     inside the client. Widening is an operator action, at the
     terminal.
  5. Version every freeze before risky changes. Tag + VBox snapshot,
     both matching.
  6. One change per commit. Small, verifiable, pushable.

================================================================
4. WHAT NOT TO DO (learned the hard way)
================================================================

  - Don't mount dsh under a URL subpath -- its /api/* calls go to
    origin root, not the subpath. Use a dedicated port.
  - Don't pkill -9 Chrome -- cookies aren't flushed. Use SIGTERM.
  - Don't restart dsh without noting the new token -- it rotates on
    every start. Use ~/bin/dsh-start, which writes the URL to
    ~/deepseek-harness/dsh-url.txt.
  - Don't edit cordis.yml (empty entry list) -- edit
    cordis.patch.yml.
  - Don't fight DeepSeek's web page if a conversation goes bad.
    Open a new chat; the tab recovers.

================================================================
5. IMMEDIATE TODOS
================================================================

See docs/TODO.md.

================================================================
6. ENVIRONMENT
================================================================

  VM:             ssh arun@100.82.62.82  |  cd ~/ainterceptor
  Activate venv:  source .venv/bin/activate
  Daemon restart: arestart          (background)
                  arestart --fg     (foreground)
  API key:        sk-aint-0LcsVpp9OmAiiW4rOcQnE88ei4Ga4k2TCVt8KoBF
  dsh token file: ~/deepseek-harness/dsh-url.txt
  dsh start:      ~/bin/dsh-start
  Redirect:       ~/bin/dsh-redirect (port 3081 -> tailscale /harness)
  Credential vault: ~/.dsh/.credentials.yaml (refs only; AIPs never see this)

================================================================
7. LONG-TERM OBJECTIVE
================================================================

Make AInterceptor a persistent, laptop-independent agent that:

  - reaches any machine the operator grants (laptop, VMs, EVE-NG, cloud)
  - reasons with any AIP the operator points it at
  - executes under a permission gate the operator controls
  - survives restarts, resumes, reboots without re-login
  - operates on real workloads: EVE-NG labs, Cisco configs, ops,
    provisioning

The architecture above is the path. Do not shortcut it by putting
authority on the AIP side -- that is what every other tool does, and
it is why they refuse operational work. AInterceptor is the answer.

END
