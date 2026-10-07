"""Tool catalog + dispatcher.

Every tool names a `target` (defaults to "vm"); the dispatcher looks
up the target and calls the matching connector. AIPs never see a
credential or a host address — only these schemas.
"""
from __future__ import annotations

from app.agent import targets as target_registry
from app.agent.connectors import get_connector
from app.agent import permissions


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
