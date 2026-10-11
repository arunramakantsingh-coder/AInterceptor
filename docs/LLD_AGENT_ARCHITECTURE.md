# LLD: AIN Agent Architecture

Last updated: 2026-10-12
Status: living (R17)
Owner: backend/app/agent/

================================================================
0. PURPOSE
================================================================

AIN is an agent. Not a chat client. It holds access, owns tools,
executes anywhere, and extends itself under operator control.

This document describes:
  - the reasoning loop
  - the permission gate (allow / deny / ask)
  - the approval queue
  - the self-extension mechanism
  - the trust boundary
  - where every piece lives
  - build order

================================================================
1. LAYERS
================================================================

  L5  Meta       extension, credentials, audit
  L4  Targets    name -> address -> connector
  L3  Tools      catalog + dispatcher + implementations
  L2  Gate       allow | deny | ask; ask blocks on a queue
  L1  Loop       ReAct: plan -> call -> gate -> dispatch -> feed back

Each layer depends only on the layer below. Nothing reaches up.

================================================================
2. THE LOOP (L1)
================================================================

    while rounds < max_rounds and elapsed < max_seconds:
        prompt = build_prompt(convo, tools)
        reply  = stream_reply(provider, state, prompt)
        clean, calls = parse_tool_calls(reply, extractor)

        if not calls:
            return success(clean, rounds)

        for call in calls:
            decision = gate.evaluate(call)        # L2
            if decision == "deny":
                convo.append(tool_result(call, "denied"))
                continue
            if decision == "ask":
                ticket = queue.submit(call)       # L2
                verdict = await ticket.wait(timeout)
                if not verdict.allowed:
                    convo.append(tool_result(call, "denied by operator"))
                    continue
            result = tools.run(call)              # L3
            convo.append(tool_result(call, result))

    # Limit hit: one final LLM call asking for a summary, then return.

Properties:
  - the gate runs BEFORE any tool executes
  - every decision is logged
  - provider-agnostic (Rule 10)
  - client-agnostic (any client uses /v1)

The loop knows nothing about specific tools or specific targets. It
only knows: prompt, parse, gate, dispatch, feed back.

================================================================
3. THE GATE (L2)
================================================================

Three-valued decision per tool call:

  allow  safe by policy (read, glob, safe shell, writes inside HOME)
  deny   blocked by policy (write outside HOME, empty cmds, unknowns)
  ask    needs operator decision (unsafe shell, self-extension,
         first-time target, destructive markers)

    permissions.evaluate(tool_name, args, context) -> Decision

context contains:
  target_id          which target the call addresses
  is_new_target      first call to this target in this session
  is_self_extension  proposed new code that AIN will load
  cmd                shell command if tool == shell
  raw_args           original args dict for audit

Policy lives in ONE file: backend/app/agent/permissions.py.
There is no per-provider, per-client, or per-target policy code.
Rule 10 holds.

================================================================
4. THE APPROVAL QUEUE (L2)
================================================================

A ticket represents one pending decision:

    Ticket(
      ticket_id: str,           # uuid
      session_id: str,
      request_id: str,
      tool: str,
      target_id: str,
      args: dict,
      reason: str,              # why the gate chose "ask"
      preview: str,             # human-readable summary
      created_at: float,
      event: asyncio.Event,     # loop blocks on this
      verdict: Ticket verdict | None,
    )

Client-agnostic API:

    submit(ticket) -> Ticket
    list_pending() -> list[Ticket]
    get(ticket_id) -> Ticket | None
    decide(ticket_id, allowed: bool, reason: str) -> bool
    history(limit: int) -> list[Ticket]

Timeout: AGENT_APPROVAL_TIMEOUT (default 240s). On timeout, the
ticket becomes denied with reason "timeout".

Audit: every submit, every decision, every timeout appends one JSONL
line to ~/.ainterceptor/approvals.log.

================================================================
5. TOOLS (L3)
================================================================

Two classes:

  BUSINESS TOOLS   do work in the world
    shell, read, write, glob
    list_targets, list_capabilities
    scan_lan, tailscale_status, probe_port
    (planned) install_package, systemctl_control, get_system_info

  META TOOLS       extend AIN itself
    request_capability   "I need a tool/connector that does not exist"
    inspect_state        "what does AIN know about itself"
    (future) list_binaries_per_target

Every tool:

  1. declared in tools.py::TOOLS    (OpenAI-shaped schema)
  2. implemented in ops_tools.py    (pure function, never raises)
  3. dispatched in tools.py::run    (match on name)
  4. gated by permissions.evaluate  (before dispatch)

The tool implementation never checks permissions itself. The
dispatcher never checks permissions itself. The gate is the only
place that decides. This keeps policy in one place.

================================================================
6. TARGETS (L4)
================================================================

    Target(
      id: str,                 # "vm", "win-laptop", "eve-ng"
      kind: str,               # "local" | "ssh" | "docker" | "http"
      address: str,            # host or host:port
      user: str,
      capabilities: list[str], # ["shell", "fs.read", "fs.write"]
      config: dict,            # per-kind extras
    )

Connectors:

  backend/app/agent/connectors/
    local.py     the AIN host itself
    ssh.py       any machine with sshd (universal remote)
    winhelper.py legacy, unused
    (planned) docker.py, http.py, vbox.py

Common interface:

    read(path) -> str
    write(path, content) -> str
    glob(pattern, root) -> list[str]
    shell(cmd, timeout) -> str

The AIP never sees the address, the user, or the credentials. It
calls with target="<name>". AIN resolves the name to a Target, then
to a connector, then runs the operation. The IP and the SSH key
never enter the AIP's context.

================================================================
7. SELF-EXTENSION (L5)
================================================================

The AIP can ask for a new capability it does not have. The request
goes through the SAME gate as any risky tool call.

Flow:

  1. AIP wants to do X. No tool exists for X.
  2. AIP calls request_capability(
       name="install_package_windows",
       description="Install a Windows package via winget",
       sample_input={"package": "vim"},
       rationale="user asked to install vim; no equivalent tool exists",
     )
  3. Gate evaluates: request_capability is classified "ask".
  4. AIN drafts the tool implementation as Python source.
  5. AIN submits the draft to the approval queue WITH the code:
       reason: "AIP wants a new tool. Here is the code:"
       preview: <the Python source>
  6. Operator sees:
       - tool name
       - description
       - sample input
       - full Python source
       - Approve / Deny / Show more
  7. On approve, AIN:
       - writes the file to ~/.ainterceptor/tools/<name>.py
       - runs static validation (imports, signature)
       - runs the sample input in a sandbox
       - if both pass, hot-loads the tool into the catalog
       - on any failure, reverts and reports the error back to the AIP
  8. Next round, the AIP can call the new tool.

Storage:

  ~/.ainterceptor/tools/*.py       hot-loaded tools
  ~/.ainterceptor/connectors/*.py  hot-loaded connectors
  (planned) ~/.ainterceptor/audit.log

Loading at daemon start: AIN scans the directories, each file
declares TOOLS (schema list) and run(name, args) (dispatcher).
Registered into the catalog alongside built-ins. Removed files are
unregistered on the next restart.

Trust boundary:

  - self-extension is NEVER silent
  - the operator sees the code before it runs
  - static + dynamic validation happens before load
  - if validation fails, nothing is written
  - the AIP cannot extend itself without an approval

================================================================
8. TRUST BOUNDARY
================================================================

The line is drawn by the gate, and only by the gate:

  allow  no operator attention. Policy-safe.
  ask    operator decides. Risky, new, or self-extension.
  deny   blocked. No override from the AIP.

Never allow, never bypass:

  - silent self-extension
  - operations on undeclared targets
  - credential reads without approval
  - destructive commands (rm -rf /, format, drop table)
  - any tool that would raise privilege on a target

The AIP is not the permission layer. It cannot authorize itself.
The gate decides.

================================================================
9. AUDIT (L5)
================================================================

Every tool call writes one JSONL line to ~/.ainterceptor/audit.log:

  {ts, session_id, request_id, tool, target, args,
   decision, reason, duration_ms, result_summary}

Every approval writes one JSONL line to ~/.ainterceptor/approvals.log:

  {ts, ticket_id, tool, target, args_preview, decision,
   reason, operator}

Both append-only. Rotation is future work.

================================================================
10. WHERE EVERYTHING LIVES
================================================================

  backend/app/agent/
    loop.py               ReAct loop
    tools.py              catalog + dispatcher
    ops_tools.py          tool implementations
    permissions.py        allow | deny | ask
    approval_queue.py     ticket + event + audit log
    targets.py            name -> Target
    prompts.py            planner-mode system prompt
    connectors/
      local.py
      ssh.py
      winhelper.py        legacy
      (docker.py)         future
      (http.py)           future
      (vbox.py)           future

  backend/app/api/
    approvals_routes.py   /dashboard/approvals + JSON endpoints
    chat_routes.py        /v1 entry; AIN tool override
    web_common.py         nav

  ~/.ainterceptor/
    approvals.log         append-only approval audit
    audit.log             append-only tool audit
    tools/                self-extension tools
    connectors/           self-extension connectors

================================================================
11. BUILD ORDER
================================================================

PHASE 1 (tonight)
  - permissions.evaluate returns allow | deny | ask
  - approval_queue.py: ticket + event + audit
  - loop.py: on "ask", submit and await
  - approvals_routes.py: dashboard + JSON
  - web_common.py: Approvals nav entry
  - main.py: include router

PHASE 2 (next session)
  - install_package tool (apt on Debian, winget on Windows)
  - get_system_info tool (uname / Windows equivalents)
  - systemctl_control tool
  - audit.log writing

PHASE 3
  - request_capability meta-tool
  - tool hot-loading and static validation
  - credential vault (encrypted at rest)
  - per-target capability negotiation

PHASE 4
  - parallel subagents
  - per-target rate limits
  - retry / backoff on target failure

================================================================
12. WHAT IS NOT BUILT YET
================================================================

Honest inventory:

  - self-extension is designed, not implemented
  - credential vault is designed, not implemented
  - audit log is designed, not implemented
  - capability negotiation is designed, not implemented
  - parallel subagents are not designed, only named
  - rate limits are not designed, only named

Phase 1 is what ships tonight.

END
