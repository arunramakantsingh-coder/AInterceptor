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
