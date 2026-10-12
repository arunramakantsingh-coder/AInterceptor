"""Talk to a Windows AInterceptor Helper: request user approval, run a
command on the target machine, receive the result."""
from __future__ import annotations
import json
import os
import socket
import uuid


DEFAULT_TIMEOUT = int(os.getenv("AGENT_APPROVAL_TIMEOUT", "300"))


class ApprovalDenied(Exception):
    """User clicked Deny, or the helper rejected the request."""


class ApprovalTimeout(Exception):
    """No response from the helper within the timeout."""


def request_approval(address: str, command: str, cwd: str | None = None,
                     reason: str = "", timeout: int = DEFAULT_TIMEOUT) -> dict:
    """Open a TCP connection to the helper, send one JSON line, wait
    for one JSON line back. Returns the parsed response dict."""
    host, _, port_s = address.partition(":")
    port = int(port_s or "8765")
    req = {
        "id": uuid.uuid4().hex[:12],
        "command": command,
        "cwd": cwd or "",
        "reason": reason or "(no reason given)",
    }
    try:
        with socket.create_connection((host, port), timeout=timeout) as s:
            s.settimeout(timeout)
            s.sendall((json.dumps(req) + "\n").encode("utf-8"))
            buf = b""
            while not buf.endswith(b"\n"):
                chunk = s.recv(4096)
                if not chunk:
                    break
                buf += chunk
    except socket.timeout:
        raise ApprovalTimeout(f"no response from helper at {address} in {timeout}s")
    try:
        resp = json.loads(buf.decode("utf-8").strip())
    except Exception as e:
        raise RuntimeError(f"bad helper response: {buf[:200]!r} ({e})")
    if not resp.get("allowed"):
        raise ApprovalDenied(resp.get("error") or "denied by user")
    return resp
