import pathlib, subprocess, datetime

ROOT = pathlib.Path.cwd()
(PROJ := ROOT / "PROJECT").mkdir(exist_ok=True)

F = {}

F["PROJECT/CLI_COMMAND_REFERENCE.md"] = """# CLI Command Reference

AInterceptor Cisco-style CLI. Every command, every mode.

## 1. Modes

AInterceptor-BOOT>            BOOT
AIRouter>                     EXEC
AIRouter#                     PRIVILEGED (after enable)
AIRouter(config)#             CONFIG (after configure terminal)
AIRouter(config-ai)#          CONFIG-AI (after ai)
AIRouter(config-ai-provider-<name>)#    after provider <name>
AIRouter(config-ai-routing)#  after routing
AIRouter(config-ai-routing-<cap>)#      after <capability>
AIRouter(config-billing)#     after billing
AIRouter(chat-<provider>)>    after chat <provider>

## 2. BOOT Mode

airouter          Enter EXEC mode
show boot         Boot diagnostics

## 3. EXEC Mode

enable            Enter privileged
?                 Context help
exit              Log out
show version      Software version
show system       System resources
show ai           AI subsystem summary
show providers    Provider status table
show health       Health state
chat <provider>   Enter chat with provider

## 4. PRIVILEGED Mode

All EXEC commands, plus:

configure terminal                    Enter CONFIG
show running-config                   Active config
show startup-config                   Persisted config
show sessions                         Active sessions
show models                           Available models
show routes                           Routing table
show counters                         Request counters
show credits                          Billing / quota
copy running-config startup-config    Persist
write memory                          Alias
erase startup-config                  Delete persisted
reload                                Restart with startup-config
debug <subsystem>                     Enable debug
undebug all                           Disable all debug
ping <provider>                       Health-check provider
clear counters                        Reset counters

## 5. CONFIG Mode

hostname <name>
ai
billing
no <command>
end              Jump to PRIVILEGED
exit             One level up

## 6. CONFIG-AI Mode

provider <name>
routing
policy
show running-config
exit

## 7. CONFIG-AI-PROVIDER Mode

enable
disable
login             Opens user's browser for auth (via agent)
logout
session storage-state <path>
rate-limit rps <n>
rate-limit burst <n>
rate-limit cooldown <seconds>
exit

## 8. CONFIG-AI-ROUTING Mode

<capability>      reasoning | coding | fast | long_context | vision
Under each capability:
  primary <provider>
  secondary <provider>
  tertiary <provider>
  max-fallbacks <n>
  exit

## 9. CHAT Mode

AIRouter# chat claude
AIRouter(chat-claude)> hi
Claude:
  Hi! How can I help you?
AIRouter(chat-claude)> /exit
AIRouter#

Slash commands: /exit /back /new /provider <name> /copy /clear /history

## 10. Show Commands — Sample Output

show version:
  AIRouter Software, Version 0.1.0
  AI ROUTER OPERATING SYSTEM
  Copyright (c) 2026 AInterceptor Project
  System uptime: 3 hours 12 minutes
  Config register: 0x2102

show providers:
  ID         ENABLED  SESSION        PATH  HEALTH    LAST ERROR
  claude     yes      authenticated  A     ready     -
  chatgpt    yes      authenticated  B     ready     -
  gemini     yes      authenticated  A     degraded  transport slow
  deepseek   yes      authenticated  A     ready     -

show sessions:
  PROVIDER  ALIAS    STATUS  EXPIRES     LAST USED
  claude    default  active  2026-10-05  2 min ago
  chatgpt   default  active  2026-10-05  5 min ago

show routes:
  CAPABILITY  PRIMARY   SECONDARY  TERTIARY  MAX FB
  reasoning   claude    chatgpt    gemini    2
  coding      deepseek  claude     chatgpt   2
  fast        gemini    chatgpt    -         1

show health:
  SUBSYSTEM            STATUS
  Control plane        ready
  Provider runtimes    ready (4 of 4)
  Session store        ready
  Transport capture    ready
  Orchestrator         scaffold
  Gateway              scaffold
  Database             ready

show counters:
  PROVIDER  REQUESTS  ERRORS  AVG LATENCY
  claude    128       2       480 ms
  chatgpt   94        1       2.1 s
  gemini    210       0       620 ms
  deepseek  67        3       510 ms

show credits:
  USER  TIER  QUOTA/DAY  USED  REMAINING
  me    pro   1000       342   658

## 11. Debug Mode

debug ai
debug provider claude
debug transport
debug routing
undebug all
Debug output goes to stderr.

## 12. History & Help

? after prefix shows continuations.
Ctrl+P / Ctrl+N navigates history.
Tab completes where unambiguous.
show history displays last 50 commands.
Persists in .ainterceptor/cli_history.

## 13. Scripting (batch)

airouter --batch < commands.txt

commands.txt example:
  enable
  configure terminal
  ai
  provider claude
  enable
  exit
  exit
  exit
  copy running-config startup-config

Exit 0 on success, non-zero on first failure. Failures print offending
command.
"""

F["PROJECT/ROADMAP.md"] = """# ROADMAP.md — AInterceptor

## Current Status

Phase: 1 — API product + agent
Status: IN PROGRESS (documentation complete, implementation next)
Branch: fix/nonclaude-three-providers-20260917
Next Gate: Docker + API + agent build

## Phase Overview

| Phase | Name | Status |
|---|---|---|
| 0 | Framework bootstrap | COMPLETE (v0.1.0) |
| 1 | API product + agent | IN PROGRESS |
| 2 | Multi-provider E2E (DeepSeek, Claude, Gemini) | PENDING |
| 3 | Orchestrator (capability, fallback, load balance) | PENDING |
| 4 | Webapp (chat + comparison) | PENDING |
| 5 | Billing, quotas, teams | PENDING |
| 6 | Policy-based routing, cost optimization | PENDING |
| 7 | Public launch, multi-tenant scale | PENDING |

## Phase 1 — API Product + Agent

Goal: an OpenRouter-compatible API endpoint, working end-to-end with
ChatGPT, with an agent that lets a user upload a session once.

Deliverables:
- docker/ + docker-compose.yml (Postgres + API)
- backend/app/api/ (auth, keys, sessions, chat endpoints)
- backend/app/db/ (SQLAlchemy models + Alembic)
- backend/app/crypto/ (HKDF + AES-GCM for session blobs)
- backend/app/runtime/ (Path A/B dispatcher)
- agent/ (airouter-agent login <provider>)
- /v1/chat/completions endpoint
- /api/auth, /api/keys, /api/sessions endpoints

Acceptance Criteria:
- docker compose up starts cleanly
- signup + login + API key generation works
- agent login chatgpt uploads a session
- POST /v1/chat/completions with a key returns ChatGPT reply, streamed
- Session persists across container restart
- No browser window ever appears on server

## Phase 2 — Multi-Provider E2E

Goal: DeepSeek, Claude, Gemini work through the same API.

Deliverables:
- DeepSeek working via Path A (direct HTTPS)
- Claude working via Path A
- Gemini working via Path A
- Per-provider parser tests
- Per-provider E2E tests (opt-in)

## Phase 3 — Orchestrator

Goal: capability routing, fallback, load balancing.

Deliverables:
- Orchestrator engine (capability registry, selection algorithm)
- Fallback chain execution
- Rate-limit tracking + cooldown
- Quota enforcement
- Selection observability events

## Phase 4 — Webapp

Goal: end-user chat UI, multi-AI comparison.

Deliverables:
- Login/signup flow
- Provider list, connect buttons
- Chat UI per provider
- Fan-out comparison view
- Session management UI
- API key management UI

## Phase 5 — Billing

Goal: usage tracking, quotas, tiers.

Deliverables:
- usage_events storage
- Tier definitions (free, pro, enterprise)
- Quota enforcement
- Usage dashboard
- Stripe integration (optional)

## Phase 6 — Policy-Based Routing

Goal: cost optimization, admin-tunable routing.

Deliverables:
- Policy DSL
- Cost model refinement
- Per-user policy overrides
- Admin routing dashboard

## Phase 7 — Scale

Goal: multi-tenant at scale.

Deliverables:
- Chromium context pool
- Horizontal scaling
- Kubernetes manifests
- Health/autoscaling
- Observability stack

## Phase 1 Gate

| Gate | Status |
|---|---|
| Implementation | PENDING |
| Local Validation | PENDING |
| Security Review | PENDING |
| Git Diff Review | PENDING |
| Commit | PENDING |
| Push | PENDING |
| Remote Verify | PENDING |
| Documentation | UPDATED |
| Milestone | IN PROGRESS |
"""

for rel, txt in F.items():
    p = ROOT / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(txt, encoding="utf-8", newline="\n")
    print(f"  [OK] {rel}  ({len(txt)} B)")

def git(a):
    return subprocess.run(["git"]+a, cwd=ROOT, capture_output=True, text=True)
git(["add","-A"])
r = git(["commit","-m","docs(phase-1d): CLI command reference + roadmap refresh"])
print((r.stdout.strip() or r.stderr.strip())[:400])

print()
print("=" * 60)
print("DOCUMENTATION REFRESH COMPLETE — 4 scripts landed")
print()
print("New/updated docs:")
print("  AGENTS.md")
print("  BLUEPRINT.md")
print("  .ai/CONTEXT.md, CURRENT_TASK.md, KNOWN_ISSUES.md")
print("  PROJECT/AIOS_ARCHITECTURE.md")
print("  PROJECT/PROVIDER_RUNTIME_CONTRACT.md")
print("  PROJECT/ROUTING_POLICY.md")
print("  PROJECT/CONFIGURATION_GUIDE.md")
print("  PROJECT/CLI_COMMAND_REFERENCE.md")
print("  PROJECT/ROADMAP.md")
print()
print("NEXT: review the docs. When approved, next script builds")
print("      docker/ + backend/app/api/ + backend/app/db/ + agent/")
print("=" * 60)
