# CLI Command Reference

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

---

## 14. AInterceptor Admin CLI (Linux) — Currently Implemented

These are the standalone admin commands that work on the Debian VM. They
sit alongside the Cisco-style CLI above (which is aspirational, not yet
built). All are short and fast to type. Prefix `a` = AInterceptor.

| Command | Purpose |
|---|---|
| `astatus` | Show daemon/CDP/Xvfb/x11vnc state and open tabs |
| `aprobe` | Read-only health check of all active providers |
| `aprobe <provider>` | Check one provider |
| `aprobe-on` | Enable the (invasive) background prober in `.env` |
| `aprobe-off` | Disable it |
| `chatgpt` / `claude` / `deepseek` / `gemini` | Enter chat with that provider |

**Probe states**

| State | Meaning | Suggested action |
|---|---|---|
| `REACHABLE` | Tab open, chat input found | none |
| `LOGIN_REQUIRED` | URL matches login markers | `alogin <provider>` (VNC) |
| `CLOUDFLARE` | CF challenge page | reload tab / wait |
| `SESSION_EXPIRED` | no chat input, not a login URL | `alogin <provider>` |
| `NO_TAB` | tab not open | restart daemon |
| `DOWN` | tab evaluate failed | check daemon |

**Prober flag**

The background prober (daemon) is controlled by `AINTERCEPTOR_PROBER_ENABLED`
in `.env`. When ON, it sends real "ping" messages — this pollutes chat
history. Default: OFF. Toggle with `aprobe-on` / `aprobe-off`, then
restart the daemon.

The `aprobe` command is **read-only** and is the recommended way to check
provider health. It never sends a message.

**Planned admin commands (script 2, not yet built)**

| Command | Purpose |
|---|---|
| `alogin <provider>` | Bring Chrome on-screen (VNC); wait; save storage_state |
| `alogout <provider>` | Clear that provider's cookies only |
| `atest <provider>` | Send "hi" and check the reply round-trip |
| `ashow` / `ahide` | Move Chrome on-screen / off-screen |
