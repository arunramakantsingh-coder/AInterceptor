# LLD - AInterceptor Agent Tool System

Last updated: 2026-10-10
Owner: backend/app/agent/
Status: living document - update in place (R17)

================================================================
1. PURPOSE
================================================================

AIPs (DeepSeek, Claude, Gemini, ChatGPT) plan. AIN executes.
The tool system is the contract between them.

An AIP receives a catalog of tool schemas. It emits a tool call
in its native syntax (DeepSeek: <||DSML||>). AInterceptor parses
the call, dispatches it to the implementation, runs it on the AIN
host, and feeds the result back to the AIP.

The AIP never:
  - holds a credential
  - has a socket, a shell, or a filesystem
  - decides whether an operation is permitted

The AIP only decides WHICH tool to call and WHAT arguments.

================================================================
2. FILE LAYOUT
================================================================

  backend/app/agent/
    tools.py        - tool CATALOG + DISPATCHER (one file, always)
    ops_tools.py    - tool IMPLEMENTATIONS (one function per tool)
    permissions.py  - allow/deny gate (called by dispatcher)
    targets.py      - multi-host target registry
    approvals.py    - client for external approval dialogs
    connectors/     - per-protocol executors (local, ssh, winhelper)
    prompts.py      - system-prompt framing (planner mode)

Rule 10: per-provider syntax lives in the provider file, NOT here.
Rule 11: dispatcher is on the hot path - no polling, no sleeping.
Rule 15: every ad-hoc diagnostic becomes a tool in this system.

================================================================
3. THE CATALOG (tools.py :: TOOLS)
================================================================

TOOLS is a list of OpenAI-shaped function schemas. This is what
the AIP sees. One entry per tool. Format:

  {
    "type": "function",
    "function": {
      "name": "tool_name",              # snake_case, unique
      "description": "one paragraph",   # what + when to call
      "parameters": {                   # JSON Schema
        "type": "object",
        "properties": { ... },
        "required": [ ... ]
      }
    }
  }

Field rules:
  - name      <= 32 chars, [a-z0-9_], matches the dispatcher case
  - description  states what the tool does AND when to use it.
                 This is the model's only guide. Be specific.
  - parameters   JSON Schema. required[] lists mandatory args.
                 Enum types are strongly preferred over free strings.

Do NOT include target/host arguments unless the tool is
multi-host. Today all tools run on the AIN host; multi-host is
the future direction via targets.py.

================================================================
4. THE DISPATCHER (tools.py :: run)
================================================================

  def run(tool_name: str, args: dict) -> str:

Behaviour:
  1. Match tool_name against a case block. Every catalog entry
     MUST have a matching case. Mismatch = dead tool.
  2. Multi-host tools pop 'target' from args, look up the target
     in targets.py, get its connector, call the connector.
  3. All other tools call the function in ops_tools.py directly.
  4. permissions.check(tool_name, args) is called before any
     write-class tool. Read-class tools (list_*, probe_*,
     tailscale_*, list_capabilities) skip the gate.
  5. Return value is ALWAYS a plain string. No exceptions raised -
     errors are returned as "error: <reason>" strings. This keeps
     the loop simple and prevents a tool exception from killing
     the agent run.

Handler signature convention:
  def tool_name(args: dict) -> str

  - args is the raw dict from the AIP. Coerce inside the tool
    (int(args.get("port")), not args["port"]).
  - returns str. Empty is valid. Errors are "error: ...".

================================================================
5. THE IMPLEMENTATION (ops_tools.py)
================================================================

One function per tool. No classes. No state. Every tool is a
pure function that takes args and returns a string.

Subprocess pattern (mandatory):
  def _run(cmd: list[str], timeout: int = 60) -> tuple[int, str, str]:
      try:
          r = subprocess.run(cmd, capture_output=True, text=True,
                             timeout=timeout)
          return r.returncode, r.stdout or "", r.stderr or ""
      except subprocess.TimeoutExpired:
          return 124, "", f"timeout after {timeout}s"
      except FileNotFoundError:
          return 127, "", f"{cmd[0]}: not found"
      except Exception as e:
          return 1, "", f"{type(e).__name__}: {e}"

  - NEVER use shell=True. Pass a list.
  - NEVER let a tool raise. Return (rc, out, err) always.
  - Timeouts are mandatory. Default 60s, override per tool.
  - If a tool needs an external binary, check shutil.which()
    first and return a helpful "not installed" message.

Output discipline:
  - Trim long output before returning. AIPs charge per token.
    If the output exceeds ~60 lines, truncate with "... (N more)".
  - Return facts, not opinions. The AIP interprets.

================================================================
6. CURRENT TOOLS
================================================================

Catalog - tools.py::TOOLS
Implementation - ops_tools.py unless noted.

  read              runtime connector   read a file from a target
  write             runtime connector   write a file (gate applies)
  glob              runtime connector   find files by pattern
  shell             runtime connector   run a shell command (gate)
  list_targets      targets.py          list registered targets

  list_capabilities ops_tools.py        which external tools exist
  tailscale_status  ops_tools.py        tailnet peers, live status
  probe_port        ops_tools.py        TCP connect check host:port
  scan_lan          ops_tools.py        nmap wrapper (ping/TCP-connect)

Behaviour notes:
  - probe_port does a TCP connect, 3s default. Returns
    OPEN / CLOSED / TIMEOUT / ERROR.
  - scan_lan caps at /16. Refuses wider. Uses -sn (ping scan)
    unless ports given, then -sT (TCP-connect, no root).
  - shell is gated by permissions.py (allowlist by default).
  - read/write/glob/shell route through targets.py so the same
    tool name works against VM, laptop, or remote once those
    connectors exist.

================================================================
7. HOW TO ADD A NEW TOOL (checklist)
================================================================

Copy this for every new tool. Do not skip steps.

  [ ] 1. Write the implementation function in ops_tools.py
         (or the appropriate connector for multi-host).
         - signature: def my_tool(args: dict) -> str
         - never raises, always returns a string
         - uses _run() for subprocess, list-args, no shell=True
         - checks shutil.which() for external binaries
         - truncates long output

  [ ] 2. Add the schema to TOOLS in tools.py.
         - name matches the function name exactly
         - description says what AND when
         - parameters is valid JSON Schema
         - required[] lists mandatory fields

  [ ] 3. Add the dispatcher case in run() in tools.py.
         - position matters only for readability; group
           related tools together.
         - if write-class, permission gate applies. If
           read-class, no gate.

  [ ] 4. Add a smoke test to the run-only list.
         Every tool must be runnable in isolation:
           PYTHONPATH=backend python3 -c "
             from app.agent import tools
             print(tools.run('my_tool', {'arg': 'value'}))
           "

  [ ] 5. Test end-to-end through /v1 with the tool in the
         tools=[] list of a curl request. Verify the AIP calls
         it, AIN runs it, result feeds back.

  [ ] 6. Commit with tag:  feat(agent): add <tool_name> tool
         Message body must say what the tool does and when to
         use it, matching the catalog description.

  [ ] 7. If the tool needs an external binary (nmap, ansible,
         docker), add it to the list in list_capabilities() so
         the AIP can discover the requirement.
         Also note the install command in the tool's error path.

  [ ] 8. Update docs/LLD_AGENT_TOOLS.md section 6 (Current
         Tools) with one line per new tool.

================================================================
8. EXAMPLE - ADDING scan_lan (reference)
================================================================

Step 1 - ops_tools.py:

  def scan_lan(args: dict) -> str:
      target = args.get("range") or ""
      ports  = (args.get("ports") or "").strip()
      if not target:
          return "error: need 'range' (CIDR or single IP)"
      try:
          net = ipaddress.ip_network(target, strict=False)
      except Exception as e:
          return f"error: bad target {target!r}: {e}"
      if net.prefixlen < 16:
          return "error: refusing to scan a range larger than /16"
      if not shutil.which("nmap"):
          return ("error: nmap not installed. Ask the operator to run:\n"
                  "  sudo apt install -y nmap")
      if ports:
          cmd = ["nmap", "-sT", "-Pn", "-p", ports, "-T4", str(net)]
      else:
          cmd = ["nmap", "-sn", "-T4", str(net)]
      rc, out, err = _run(cmd, timeout=300)
      if rc != 0:
          return f"error (rc={rc}): {err.strip()[:400]}"
      lines = out.splitlines()
      if len(lines) > 60:
          lines = lines[:60] + [f"... ({len(out.splitlines())-60} more)"]
      return "\n".join(lines)

Step 2 - tools.py TOOLS list:

  {
    "type": "function",
    "function": {
      "name": "scan_lan",
      "description": ("Run nmap against a CIDR (max /16). Without "
                      "ports runs a ping scan; with ports does a "
                      "TCP-connect port scan. Use to discover live "
                      "hosts on the operator's network."),
      "parameters": {
        "type": "object",
        "properties": {
          "range": {"type": "string", "description": "CIDR or single IP"},
          "ports": {"type": "string", "description": "e.g. '22,80,443'"},
        },
        "required": ["range"],
      },
    },
  },

Step 3 - tools.py run():

  if tool_name == "scan_lan":
      return ops_tools.scan_lan(args)

Step 4 - smoke test:

  PYTHONPATH=backend python3 -c "
    from app.agent import tools
    print(tools.run('scan_lan', {'range': '127.0.0.1/32'}))"

Step 5 - e2e via curl with tools=[scan_lan] and message
         "scan 127.0.0.1 and report".

Step 6 - commit + push.

Step 7 - list_capabilities already checks nmap. If not, add.

Step 8 - update section 6 above.

================================================================
9. WHAT NOT TO DO
================================================================

  - Do NOT put provider-specific logic in tools.py or ops_tools.py.
    Provider parsing lives in backend/app/interception/<provider>/.
    (Rule 10)

  - Do NOT add a tool that only one AIP can call. Tools are
    provider-neutral. If a capability depends on provider features,
    solve it in the provider file, not the tool layer. (Rule 10)

  - Do NOT poll or sleep inside a tool. One-shot subprocess only.
    If a task needs waiting, model it as separate tool calls.
    (Rule 11)

  - Do NOT catch exceptions silently. Return "error: ..." strings
    so the AIP sees the failure and can adapt.

  - Do NOT return huge output. Truncate. AIPs charge per token
    and stall on long inputs.

  - Do NOT write to disk from a tool unless the tool is
    explicitly a write tool and it passes permissions.check().

  - Do NOT add a tool that requires root to the default catalog.
    If root is genuinely needed, gate it, and document the
    install/privilege requirement in the description and error
    path so the AIP can surface it to the operator.

  - Do NOT let a new tool bypass targets.py if it addresses a
    remote host. Multi-host tools must go through the connector
    layer so SSH, winhelper, and local paths stay consistent.

================================================================
10. OPEN ITEMS (from this session)
================================================================

  - The AIP sees our tool catalog, but the harness (dsh) has its
    own tool namespace. Calls emitted as `bash` are rejected by
    the harness's own denial layer before reaching us. Fix is on
    the harness side - either route dsh 100% through /v1 and let
    AInterceptor own the tool surface (preferred), or remove the
    harness's parallel tool plugins so there is one source of
    truth.

  - The AIP called probe_port with port "800" instead of "8000" -
    a truncation in the DeepSeek web stream's DSML output. Not our
    bug. Consider adding a sanity range to tools that take
    well-known ports (reject < 1024 for public IPs) as a guard
    against silent truncation.

  - Chat rotation: when the AIP's own web page accumulates
    history, it starts refusing based on the pattern of past
    requests. Rotate the tab when history grows past N turns.
    Tracked in docs/TODO.md.

END
