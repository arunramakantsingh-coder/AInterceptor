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
