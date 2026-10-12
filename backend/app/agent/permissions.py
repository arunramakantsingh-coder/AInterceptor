"""Permission gate.

Three-valued decision per tool call:

  "allow"   policy-safe, run without operator attention
  "deny"    blocked by policy, no operator override
  "ask"     risky, new, or self-extension -> approval queue

Policy lives here and ONLY here. No per-provider, per-client, or
per-target policy code. Rule 10 holds.

The gate never runs the tool. The dispatcher never checks policy.
Only this file decides.
"""
from __future__ import annotations
import os
import pathlib

# Commands that are safe to run without asking. Read-only system
# inspection and version checks. If a command needs to modify state
# on the target, it does NOT belong on this list.
SAFE_SHELL_BINS = {
    "hostname", "pwd", "whoami", "date", "uname", "id",
    "ls", "cat", "head", "tail", "wc", "grep", "find",
    "which", "type", "env", "printenv",
    "df", "du", "free", "ps", "ip", "ss", "netstat",
    "git", "curl",                    # version checks + fetches
    "python", "python3", "node", "npm",
    "docker", "systemctl", "journalctl",  # status-only if used read-only
    "vboxmanage",
    # pure read-only inspection tools (no side effects on the target).
    # sed/awk are deliberately EXCLUDED: sed -i rewrites files in place
    # and awk can shell out — both stay "ask".
    "diff", "stat", "file", "md5sum", "sha256sum", "jq",
}

# Shell wrappers that may precede the real command. The gate peels
# them (and their arguments) and evaluates the inner command, so
# "timeout 5 rm -rf /" is judged by "rm", never by "timeout".
WRAPPER_BINS = {
    "timeout", "env", "nice", "nohup", "ionice", "stdbuf",
}


def _is_number(token: str) -> bool:
    try:
        float(token)
        return True
    except ValueError:
        return False


def _is_wrapper_arg(token: str) -> bool:
    """An option, a number, or a VAR=VALUE assignment — a wrapper
    argument, never a command name."""
    return token.startswith("-") or "=" in token or _is_number(token)


def _peel_wrappers(cmd: str) -> str:
    """Strip leading shell wrappers and their arguments so the gate
    judges the inner command. Fail closed: any token that is neither
    a known wrapper nor a wrapper argument stops the peel."""
    tokens = cmd.split()
    while tokens:
        name = os.path.basename(tokens[0].lower().lstrip("./"))
        if name not in WRAPPER_BINS:
            break
        tokens = tokens[1:]
        while tokens and _is_wrapper_arg(tokens[0]):
            tokens = tokens[1:]
    return " ".join(tokens)

# Substrings that force "ask" regardless of anything else. These are
# operators of last resort: if a command contains one, the operator
# must see it before it runs.
DESTRUCTIVE_MARKERS = (
    "rm -rf", "rm -fr", "mkfs", "dd if=", "format ", "> /dev/sd",
    "drop table", "drop database", "truncate table",
    ":(){:|:&};:",                      # fork bomb
    "shutdown", "reboot", "halt",
    "del /f", "format ", "rmdir /s",
)


def _shell_allowed_by_env() -> bool:
    return os.getenv("AGENT_SHELL_ALLOW") == "1"


def evaluate(tool_name: str, args: dict, context: dict | None = None) -> tuple[str, str]:
    """Return (decision, reason).

    decision is one of: "allow" | "deny" | "ask"
    reason is empty for allow, a short sentence otherwise.
    """
    ctx = context or {}

    # ── reads and globs: always allow ────────────────────────────
    if tool_name in ("read", "glob"):
        return "allow", ""

    if tool_name == "list_targets" or tool_name == "list_capabilities":
        return "allow", ""
    if tool_name in ("tailscale_status", "probe_port"):
        return "allow", ""

    # ── writes: allow inside HOME, ask outside ───────────────────
    if tool_name == "write":
        p = pathlib.Path(args.get("path", "")).expanduser()
        try:
            p = p.resolve()
        except Exception:
            return "deny", "unresolvable path"
        home = pathlib.Path.home()
        if str(p).startswith(str(home)):
            return "allow", ""
        return "ask", f"write outside $HOME: {p}"

    # ── shell: three-way ─────────────────────────────────────────
    if tool_name == "shell":
        cmd = (args.get("cmd") or "").strip()
        if not cmd:
            return "deny", "empty command"

        # Destructive markers: always ask, no matter what.
        for marker in DESTRUCTIVE_MARKERS:
            if marker in cmd.lower() or marker in cmd:
                return "ask", f"destructive marker: {marker!r}"

        # Scanner: allow. Read-only network probe.
        if tool_name == "scan_lan":
            return "allow", ""

        # First binary: check safe list — AFTER peeling wrappers, so
        # "timeout 5 rm -rf /" is judged by "rm", not "timeout".
        peeled = _peel_wrappers(cmd)
        if not peeled:
            return "deny", "command is only shell wrappers"
        first = peeled.split()[0].lower().lstrip("./")
        first = os.path.basename(first)

        if _shell_allowed_by_env():
            return "allow", ""

        if first in SAFE_SHELL_BINS:
            return "allow", ""

        return "ask", f"shell command {first!r} not on safe list"

    # ── scan_lan: allow with parsed CIDR cap (already enforced inside) ──
    if tool_name == "scan_lan":
        return "allow", ""

    # ── self-extension: always ask (Phase 3 will draft code) ────
    if tool_name == "request_capability":
        return "ask", "self-extension: AIP requests a new tool"

    # ── unknown tools: deny ──────────────────────────────────────
    return "deny", f"unknown tool {tool_name!r}"


# Backward-compat shim for any external caller that still uses check().
def check(tool_name: str, args: dict) -> tuple[bool, str]:
    decision, reason = evaluate(tool_name, args)
    return decision == "allow", reason
