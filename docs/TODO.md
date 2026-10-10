# AInterceptor - TODO

Ordered by priority. Check off, do not reorder silently.

================================================================
NOW
================================================================

[ ] Rebrand dsh UI.
    Remove all "DeepSeek Harness" branding from the web UI.
    New codename chosen by operator (AIF / AIN candidates).
    UI must present itself as AInterceptor, not DeepSeek.
    Update docs/HANDOVER.md references after.

[ ] Response time tuning.
    Current: ~15-20s to first content chunk on DeepSeek web
    (AIP typing time, not AInterceptor overhead).
    Options:
      (a) skip sending full history when client sends only last
          user message
      (b) warm the tab before the first user prompt
      (c) direct WebSocket from CDP instead of streamResourceContent
    Do (b) first -- 5 min.

[ ] Systemd user units for daemon + dsh + redirect.
    loginctl enable-linger arun.
    Reboot/resume safe.

================================================================
NEXT
================================================================

[ ] Planner-mode system prompt for the agent loop.
    Replace dsh's "you are an agent with limited permission"
    framing with "you are a planner; the operator owns everything;
    AInterceptor executes under their permission model."
    This is what stops AIP refusals on operational tasks
    (EVE-NG lab setup, Cisco configs, ops).

[ ] Interactive permission gate.
    Replace the static allowlist in agent/permissions.py with
    queued approvals shown via dashboard, phone client, or
    Windows Helper dialog.

[ ] EVE-NG target.
    REST API connector; register as target; test "create a small
    OSPF lab" end-to-end.

[ ] SSH connector.
    agent/connectors/ssh.py -- same shape as local.py, uses
    ~/.ssh/config. Register Windows laptop reverse-key first.

================================================================
LATER
================================================================

[ ] Claude tab: solve CF challenge (agent login flow at /login/claude).
[ ] ChatGPT: WebSocket capture for its streaming format.
[ ] Gemini: investigate parser-empty-on-completed-conversation.
[ ] Phone-as-brain: CDP-remote mode
    (AINTERCEPTOR_CDP_REMOTE=ws://vm:9222) so the phone runs the
    FastAPI daemon and borrows the VM's Chrome.
[ ] Windows Helper bootstrap (tray approval dialog, one-time install).
[ ] Multi-root workspace for the agent (currently $HOME only).

END

## Small cleanups (do not bundle)

- [ ] Dashboard nav has TWO "Docs" entries:
      `/dashboard/docs` and `/docs`. Rename one or remove.
- [ ] `atest osi` should move to `/internal/osi/<provider>` per R12.
      Currently admin_cli imports the probe in-process.
- [ ] Chat rotation: open a new tab chat when history grows past N
      turns. Fixes accumulated-context slowdown (see HANDOVER §2).

## Rebrand (deferred — SVG, not string replacement)

The "deepseek HARNESS" header is drawn as SVG paths in:
  ~/.npm/_npx/*/node_modules/@deepseek-ai/dsh-web-frontend/dist/assets/index-*.js

Classes: `_wordmark_*`, `_boot_*`, `_card_*` (see `wordmark_u7vgf_31`)
Grep for `dsh-wordmark-whale-clip` and `dsh-wordmark-badge-clip`.

Two paths to fix:
  A. Local copy + CSS override in dist/index.html
     - `[class*="wordmark"] { display: none }` + inject "AIN" text
  B. Write a dsh client plugin that replaces the wordmark slot

Deferred: cosmetic. Do after planner-mode prompt is live.

## Harness code review — 2026-10-10 (dsh read-only pass)

Findings ranked by severity. All from an automated dsh review of
this repo. Verify each before fixing.

### Critical (may be live bugs)

- [ ] daemon.py: undefined `is_alive()` called by watchdog.
      Watchdog runs every 3s; trace whether this actually fires.
- [ ] daemon.py: stray `}` at end of file. Check if it's real or
      inside a docstring/string literal.

### Architectural

- [ ] dispatcher.py is built on "Path A / Path B", but .ai/rules/
      10-provider-isolation.md explicitly forbids that concept.
      Refactor candidate — not urgent, code works.
- [ ] Two provider lists disagree in size:
      interception/registry.py (4) vs browser_supervisor.PROVIDER_URLS (20).
      Pick one as source of truth, delete the other.
- [ ] perplexity appears in both NO_RUNTIME_MODULE and
      PATH_A_SUPPORTED — Path A unreachable by definition.

### Cleanup

- [ ] daemon.py: orphaned prober — `_probe_dispatch` defined,
      `prober = None` returned, teardown swallows AttributeError.
- [ ] _chrome_args: unused `pos` variable.
- [ ] push_chrome_off_screen(): duplicated platform guard.
- [ ] command_tree.py read only through line ~120 during review.
      Complete the read when touching it next.
- [ ] ops.py and admin_cli.py not reviewed by the automated pass.
      Add to a future review run.

### Verification gap

- [ ] targets.py couldn't be read during the review (DSML multi-arg
      bug). See section above. Fix that bug, then re-read targets.py.
