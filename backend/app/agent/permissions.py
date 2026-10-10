"""Permission gate.

Today: conservative allowlist. Reads/globs auto-allow. Writes auto-
allow inside $HOME. Shell commands auto-allow only if the binary is
on the safe list, OR the operator has set AGENT_SHELL_ALLOW=1.

Later: an approvals table + blocking wait + UI.
"""
from __future__ import annotations
import os
import pathlib

SAFE_SHELL_BINS = {
    "hostname", "pwd", "whoami", "date", "uname", "id",
    "ls", "cat", "head", "tail", "wc", "grep", "find",
    "git", "curl", "which", "type", "env", "printenv",
    "df", "du", "free", "ps", "ip", "ss", "netstat",
    "docker", "systemctl", "journalctl",
    "python", "python3", "node", "npm", "pip",
    "vboxmanage",           # VirtualBox
}


def _shell_allowed_by_env() -> bool:
    return os.getenv("AGENT_SHELL_ALLOW") == "1"


def check(tool_name: str, args: dict) -> tuple[bool, str]:
    if tool_name in ("read", "glob"):
        return True, ""

    if tool_name == "write":
        p = pathlib.Path(args.get("path", "")).expanduser()
        try:
            p = p.resolve()
        except Exception:
            return False, "unresolvable path"
        home = pathlib.Path.home()
        if str(p).startswith(str(home)):
            return True, ""
        return False, f"write outside $HOME not permitted: {p}"

    if tool_name == "shell":
        cmd = (args.get("cmd") or "").strip()
        if not cmd:
            return False, "empty command"
        first = cmd.split()[0].lower().lstrip("./")
        # Strip any path prefix, e.g. /usr/bin/git → git
        first = os.path.basename(first)
        if _shell_allowed_by_env():
            return True, ""
        if first in SAFE_SHELL_BINS:
            return True, ""
        return False, (
            f"shell command {first!r} not on safe list; "
            "set AGENT_SHELL_ALLOW=1 to permit"
        )

    return False, f"unknown tool {tool_name!r}"
