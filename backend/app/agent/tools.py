"""Tool catalog + dispatcher.

Every tool names a `target` (defaults to "vm"); the dispatcher looks
up the target and calls the matching connector. AIPs never see a
credential or a host address — only these schemas.
"""
from __future__ import annotations

from app.agent import targets as target_registry
from app.agent.connectors import get_connector
from app.agent import permissions
from app.agent import ops_tools


TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "list_targets",
            "description": (
                "List every machine AInterceptor can reach, with its "
                "capabilities. Use this first when you need to know "
                "what's available."
            ),
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read",
            "description": "Read a file from a target machine.",
            "parameters": {
                "type": "object",
                "properties": {
                    "target": {"type": "string", "description": "Target id, e.g. 'vm'. Defaults to 'vm'."},
                    "path": {"type": "string", "description": "Absolute path or path relative to cwd/$HOME."},
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write",
            "description": "Write a file on a target machine. Blocked outside $HOME by policy.",
            "parameters": {
                "type": "object",
                "properties": {
                    "target": {"type": "string"},
                    "path": {"type": "string"},
                    "content": {"type": "string"},
                },
                "required": ["path", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "glob",
            "description": "Find files matching a glob pattern.",
            "parameters": {
                "type": "object",
                "properties": {
                    "target": {"type": "string"},
                    "pattern": {"type": "string", "description": "e.g. '**/*.py'"},
                    "root": {"type": "string", "description": "Base directory; defaults to $HOME."},
                },
                "required": ["pattern"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_capabilities",
            "description": ("Report which external tools AIN can drive on "
                            "this host (nmap, tailscale, ssh, docker, ...). "
                            "Call this first when unsure what's installed."),
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "tailscale_status",
            "description": ("List every tailnet peer reachable from this "
                            "host, with IP and online state."),
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "probe_port",
            "description": "TCP-connect check on host:port. Returns OPEN / CLOSED / TIMEOUT.",
            "parameters": {
                "type": "object",
                "properties": {
                    "host": {"type": "string", "description": "hostname or IP"},
                    "port": {"type": "integer", "description": "1-65535"},
                    "timeout_s": {"type": "number", "description": "default 3"},
                },
                "required": ["host", "port"],
            },
        },
    },
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
                    "ports": {"type": "string", "description": "e.g. '22,80,443' (optional)"},
                },
                "required": ["range"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "shell",
            "description": (
                "Run a shell command on a target. Some commands are "
                "allowlisted; others require user approval. Prefer "
                "read/glob/write when they suffice."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "target": {"type": "string"},
                    "cmd": {"type": "string"},
                    "timeout": {"type": "integer", "description": "Seconds. Default 60."},
                },
                "required": ["cmd"],
            },
        },
    },
]


def run(tool_name: str, args: dict) -> str:
    """Execute a tool call. Returns a plain string result."""
    # ── Operational tools (run on the AIN host) ──
    if tool_name == "list_capabilities":
        return ops_tools.list_capabilities(args)
    if tool_name == "tailscale_status":
        return ops_tools.tailscale_status(args)
    if tool_name == "probe_port":
        return ops_tools.probe_port(args)
    if tool_name == "scan_lan":
        return ops_tools.scan_lan(args)

    if tool_name == "list_targets":
        rows = []
        for t in target_registry.list_targets():
            rows.append(f"- {t.id}  kind={t.kind}  capabilities={','.join(t.capabilities)}")
        return "\n".join(rows) if rows else "(no targets)"

    target_id = args.pop("target", "vm")
    t = target_registry.get(target_id)

    ok, reason = permissions.check(tool_name, args)
    if not ok:
        return f"[permission denied] {reason}"

    conn = get_connector(t)

    if tool_name == "read":
        return conn.read(args["path"])
    if tool_name == "write":
        return conn.write(args["path"], args["content"])
    if tool_name == "glob":
        hits = conn.glob(args["pattern"], args.get("root"))
        return "\n".join(hits) if hits else "(no matches)"
    if tool_name == "shell":
        return conn.shell(args["cmd"], int(args.get("timeout", 60)))

    return f"error: unknown tool {tool_name!r}"
