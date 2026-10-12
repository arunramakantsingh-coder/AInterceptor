# AInterceptor - Session Handover

Last updated: 2026-10-12
HEAD:        38c253c  docs(ai): create .ai/agents and .ai/workflows skeleton
Tag:         v0.2.10-approval-gate
Snapshot:    v0.2.10-approval-gate (VBox)
Branch:      fix/cli-chat-provider-gate-cisco-shell
Purpose:     resume cleanly in a fresh chat. Read this before touching anything.

================================================================
0. WHAT AINTERCEPTOR IS
================================================================

AInterceptor is an AGENT. It holds access: files, shell, network,
targets, credentials, browser sessions. It is the thing that acts.

AIPs (DeepSeek, Claude, Gemini, ChatGPT, others) are INTERCHANGEABLE
REASONING ENGINES. Chosen per-request by the router. They receive a
prompt, return text. They never hold a credential, never touch a
target, never execute a tool.

The SHIM translates between AInterceptor's OpenAI-shaped tool
protocol and each AIP's native syntax (DeepSeek: <||DSML||>; others
have their own). Per Rule 10, provider-specific syntax lives in the
provider file, not the shim.

================================================================
1. CURRENT STATE - WHAT WORKS
================================================================

  AInterceptor daemon              OK   python -m app.runtime.daemon, :8000
  /v1/chat/completions             OK   OpenAI-compatible, chat + tools
  DeepSeek via /v1                 OK   reply verified, port digits preserved
  Claude via /v1                   --   parked, CF challenge unresolved
  Gemini via /v1                   --   parser sometimes empty
  ChatGPT via /v1                  --   parked, needs WebSocket capture
  dsh harness (VM) on :3080        OK   served via Tailscale, native tools disabled
  /harness URL stable              OK   https://ainterceptor.taila2310c.ts.net/harness/
  AIN owns the tool catalog        OK   verified: model lists AIN's tools only
  SSH connector                    OK   ssh.py, reaches win-laptop
  win-laptop as kind=ssh           OK   100.67.225.84, key auth
  Interactive approval gate        OK   allow | deny | ask, dashboard + queue
  Approval dashboard               OK   /dashboard/approvals
  max_rounds with summarizer       OK   30 default, env AGENT_MAX_ROUNDS

================================================================
2. WHAT SHIPPED TODAY (commits in order)
================================================================

  38c253c  docs(ai): create .ai/agents and .ai/workflows skeleton
  c1a8cc4  fix(agent): forgiving approval cache + on-disk persistence
  5fbf8ca  fix(agent): decide() clears pending + writes history; loop wait 120s
  abd24f7  fix(agent): session_id is stable per API key, not random
  0ca9679  fix(agent): approval ticket survives caller timeout
  4002464  fix(agent): session_id uses module-level uuid, not block-local _uuid
  c6898db  feat(agent): interactive approval gate
  55412b5  docs(lld): AIN agent architecture
  bc796c1  deploy(dsh): disable native tools, route all actions through AIN
  6f6454e  docs(todo): verified end-to-end multi-target via /v1
  a919d08  feat(agent): SSH connector + win-laptop as kind=ssh target
  efe2fed  fix(agent): raise max_rounds to 30, summarize on limit

Also earlier today: port-fix in deepseek/__init__.py verified end-to-end,
snapshot v0.2.9-harness-to-windows.

================================================================
3. THE MILESTONE THAT PROVES THE ARCHITECTURE
================================================================

The whole chain works:

  dsh (client) -> POST /v1 -> AIN agent loop -> permissions.evaluate
     -> allow | deny | ask
     -> tool dispatch -> connector (local or ssh)
     -> Windows laptop over SSH
     -> result back to AIP
     -> AIP summarizes -> reply

Verified: "Run VBoxManage list vms on win-laptop" returned
  "Tiny Core", "AInterceptor", "EVE" - the three VirtualBox VMs.

The AIP never saw the IP 100.67.225.84. It called with target name
"win-laptop". AIN's targets.py resolved name -> address + key +
transport. That is the design.

================================================================
4. WHAT'S NOT DONE - NEXT SESSION'S WORK
================================================================

Priority order:

1. AIN-native chat with in-chat approval.
   3-4 hours. Refactor loop.py to yield events, /chat/stream SSE
   endpoint, HTML page with chat + inline Allow/Deny buttons. Replaces
   dsh as the client. Solves the approval UX friction (no tab switch,
   no re-send).

2. ~~Daemon import isolation.~~ SHIPPED 2026-10-12 —
   main.py safe-loads all 24 api routers; tools.py guards the ops
   backend; connectors load per-kind through safe loaders.
   Fault-injection verified (poisoned approvals_routes -> daemon
   imports, health present, approvals absent). See PROGRESS.md.

3. Multi-arg DSML parser correctness.
   When 3+ parameters are in one invoke block, the closing tag can
   leak. DSH flagged this earlier. Verify with a 3-arg sample and fix
   _DSML_PARAM_RE if broken.

4. install_package, get_system_info, systemctl_control tools.
   See docs/LLD_AGENT_ARCHITECTURE.md, Phase 2.

5. EVE-NG connector (http.py connector + register target).

6. self-extension (request_capability meta-tool).
   Designed in LLD Phase 3. Not built.

7. Daemon on-boot Chrome: skip non-active provider tabs.

8. Permission policy refinements in permissions.py:
   - DESTRUCTIVE_MARKERS list is minimal
   - SAFE_SHELL_BINS list will need operator-specific entries
   - consider per-target policy (win-laptop vs linux: different safe lists)

================================================================
5. RULES THAT BIND
================================================================

Read first:
  .ai/RULES.md                    R1-R7 (progress, tags, docs, script, future,
                                       session log, automate)
  .ai/rules/10-provider-isolation.md
  .ai/rules/11-performance-priority.md
  .ai/rules/12-module-split.md
  .ai/rules/13-surgical-evolution.md
  .ai/rules/14-simplify-before-extend.md
  .ai/rules/15-diagnose-becomes-command.md
  .ai/rules/16-provider-account-registry.md
  .ai/rules/17-docs-are-living.md

Rule 10 is the one most often violated by well-meaning changes:
  - per-provider syntax in the provider file
  - do NOT put provider-specific logic in shared base classes
  - do NOT put operator-specific knowledge (custom ports, machine
    names, service conventions) into shipped code
  - the gate is the only place that decides permissions

Rule 11: the hot path (stream_reply -> execute -> submit -> capture
-> first delta) has no polling, no sleeping, no re-scanning.

Rules we learned this session and want recorded (not yet in .ai):
  - One command at a time when the command writes state.
  - The gate is the only place that decides. The dispatcher is pure.

================================================================
6. ENVIRONMENT
================================================================

  VM:               ssh arun@100.82.62.82  |  cd ~/ainterceptor
  Activate:         source .venv/bin/activate
  Restart daemon:   systemctl --user restart ainterceptor-daemon.service
                    (also restarts dsh and redirect via PartOf)
  Status:           astatus / ahealth
  OSI probe:        atest osi <provider>
  Approvals:        https://ainterceptor.taila2310c.ts.net/dashboard/approvals
  API key:          sk-aint-0LcsVpp9OmAiiW4rOcQnE88ei4Ga4k2TCVt8KoBF
  dsh token file:   ~/deepseek-harness/dsh-url.txt
  dsh start:        ~/bin/dsh-start
  dsh profile:      ~/.dsh/profiles/web/cordis.patch.yml
                    (native tools disabled; AIN owns catalog)
  Approvals log:    ~/.ainterceptor/approvals.log (JSONL)
  Approvals cache:  ~/.ainterceptor/approvals_cache.json

================================================================
7. FILES CREATED / TOUCHED THIS SESSION
================================================================

New:
  backend/app/agent/approval_queue.py       ticket queue + cache + audit
  backend/app/agent/connectors/ssh.py       SSH connector (universal remote)
  backend/app/agent/prompts.py              planner-mode system prompt
  backend/app/api/approvals_routes.py       dashboard + JSON endpoints
  docs/LLD_AGENT_ARCHITECTURE.md            five-layer agent design
  docs/LLD_AGENT_TOOLS.md                   tool system design
  deploy/systemd-user/*.service             systemd units (repo copy)
  deploy/systemd-user/README.md
  deploy/dsh-profile/cordis.patch.yml       dsh profile (repo copy)
  deploy/dsh-profile/README.md
  .ai/agents/README.md                      skeleton
  .ai/workflows/README.md                   skeleton

Modified:
  backend/app/agent/loop.py                 gate + queue + summarizer
  backend/app/agent/permissions.py          3-valued evaluate
  backend/app/agent/tools.py                dispatcher is pure
  backend/app/agent/targets.py              win-laptop kind=ssh
  backend/app/api/chat_routes.py            session_id stable per key
  backend/app/api/web_common.py             Approvals nav entry
  backend/app/main.py                       approvals router
  backend/app/interception/deepseek/__init__.py  port-digit fix
  docs/HANDOVER.md                          this doc
  docs/TODO.md                              running list

================================================================
8. GOTCHAS LEARNED THIS SESSION
================================================================

- Python local scope: a name assigned anywhere in a function is
  function-local for the WHOLE function. Referencing `_uuid` before
  `import uuid as _uuid` = UnboundLocalError. Use module-level imports.

- The daemon crash-loops if any imported module fails. One bad file
  = no daemon. Nothing guards imports yet.

- DeepSeek web UI drops the trailing digit of 4-digit numbers ending
  in a repeated digit: 8000 -> 800, 2222 -> 222, 7777 -> 777, but
  9090 survives. Root cause was OUR parser's suffix-matching
  idempotency check in DeepSeekStreamParser._append_content. Fixed.

- Windows OpenSSH Server has a restricted PATH: it does not include
  C:/Program Files/Oracle/VirtualBox. Add via Machine env var, not
  the user's. Restart-Service sshd to pick it up.

- dsh sends its own tool catalog. When AIN owns the catalog, we
  override it in chat_routes.py. Otherwise the model sees bash/read
  (dsh's) alongside shell/read (AIN's) and gets confused.

- The approval flow's in-chat message appears only after the loop's
  wait expires. Chicken-and-egg: user sees message -> switches tabs
  -> clicks -> comes back -> re-sends. The AIN-native chat with
  in-chat buttons is the correct fix.

================================================================
9. IMMEDIATE NEXT ACTIONS
================================================================

1. Fresh chat with this handover + docs/NEXT_CHAT_PROMPT.md.
2. Read the rules.
3. Verify daemon + SSH work (two read-only commands).
4. Then decide: AIN-native chat, or a smaller piece from section 4.

Do not start a large task without confirming state (daemon 200,
ssh Arun@100.67.225.84 hostname returns DESKTOP-9S3SKGC).

END
