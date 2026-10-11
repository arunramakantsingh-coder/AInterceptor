"""Approval queue: ticket-based, event-driven, client-agnostic.

One Ticket per pending "ask" decision. The loop blocks on the
ticket's asyncio.Event until the operator (or timeout) resolves it.

Storage: in-memory dict, keyed by ticket_id. History is appended
to ~/.ainterceptor/approvals.log as JSONL.
"""
from __future__ import annotations
import asyncio
import json
import os
import pathlib
import time
import uuid
from dataclasses import dataclass, field, asdict


LOG_PATH = pathlib.Path.home() / ".ainterceptor" / "approvals.log"
DEFAULT_TIMEOUT_S = float(os.getenv("AGENT_APPROVAL_TIMEOUT", "240"))


@dataclass
class Ticket:
    ticket_id: str
    session_id: str
    request_id: str
    tool: str
    target_id: str
    args: dict
    reason: str
    created_at: float
    preview: str = ""
    verdict: dict | None = None
    event: asyncio.Event = field(default_factory=asyncio.Event)


_PENDING: dict[str, Ticket] = {}
_HISTORY: list[dict] = []
_LOCK = asyncio.Lock()


def _preview(tool: str, target: str, args: dict) -> str:
    if tool == "shell":
        return f"shell on {target}: {args.get('cmd', '')[:200]}"
    if tool == "write":
        return f"write to {args.get('path', '?')} on {target}"
    if tool == "request_capability":
        return f"new tool requested: {args.get('name', '?')}"
    return f"{tool} on {target}"


def _audit(record: dict) -> None:
    try:
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with LOG_PATH.open("a") as fh:
            fh.write(json.dumps(record, default=str) + "\n")
    except Exception:
        pass


# ── recent decision cache ─────────────────────────────────────
# Keyed by (session_id, tool, target_id, args_hash). Stores decisions
# from the last RECENT_TTL_S seconds. Allows the loop to skip the
# queue on a re-send after the operator has already approved the same
# action.
import hashlib as _hashlib
RECENT_TTL_S = 600.0
_RECENT: dict[str, dict] = {}


def _signature(session_id: str, tool: str, target_id: str, args: dict) -> str:
    blob = json.dumps({"s": session_id, "t": tool, "g": target_id, "a": args},
                      sort_keys=True, default=str)
    return _hashlib.sha256(blob.encode()).hexdigest()[:24]


def check_recent(session_id: str, tool: str, target_id: str, args: dict) -> dict | None:
    """Return the last cached verdict for this exact call, if fresh."""
    sig = _signature(session_id, tool, target_id, args)
    hit = _RECENT.get(sig)
    if hit is None:
        return None
    if time.time() - hit["ts"] > RECENT_TTL_S:
        _RECENT.pop(sig, None)
        return None
    return hit["verdict"]


async def submit(*, session_id: str, request_id: str,
                 tool: str, target_id: str, args: dict,
                 reason: str) -> Ticket:
    try:
        await expire_old()
    except Exception:
        pass
    async with _LOCK:
        t = Ticket(
            ticket_id=uuid.uuid4().hex[:12],
            session_id=session_id,
            request_id=request_id,
            tool=tool,
            target_id=target_id,
            args=dict(args),
            reason=reason,
            created_at=time.time(),
            preview=_preview(tool, target_id, args),
        )
        _PENDING[t.ticket_id] = t
        _audit({
            "ts": t.created_at, "event": "submit",
            "ticket_id": t.ticket_id, "tool": tool,
            "target": target_id, "reason": reason,
            "preview": t.preview,
        })
        return t


async def wait(ticket: Ticket, timeout: float | None = None) -> dict:
    """Block until a decision, or until `timeout` seconds pass.

    IMPORTANT: an early return from this function does NOT cancel the
    ticket. The ticket stays in the pending queue so the operator can
    still decide it later. Only decide() or the janitor close a ticket.
    """
    timeout = timeout if timeout is not None else DEFAULT_TIMEOUT_S
    try:
        await asyncio.wait_for(ticket.event.wait(), timeout=timeout)
        return ticket.verdict or {"allowed": False, "reason": "no verdict"}
    except asyncio.TimeoutError:
        # The caller is tired of waiting; the ticket is not dead.
        # Return a "still pending" verdict; leave the ticket in _PENDING.
        return {"allowed": False, "reason": "still_pending",
                "ticket_id": ticket.ticket_id}


async def expire_old() -> int:
    """Janitor: remove tickets older than DEFAULT_TIMEOUT_S from
    _PENDING and record them as expired. Call this on each submit().
    """
    now = time.time()
    expired = 0
    async with _LOCK:
        for tid, t in list(_PENDING.items()):
            if now - t.created_at > DEFAULT_TIMEOUT_S:
                _PENDING.pop(tid, None)
                _HISTORY.append({
                    "ts": now, "ticket_id": tid,
                    "tool": t.tool, "target": t.target_id,
                    "verdict": {"allowed": False, "reason": "expired"},
                })
                _audit({"ts": now, "event": "expired", "ticket_id": tid})
                expired += 1
        if len(_HISTORY) > 500:
            del _HISTORY[:-500]
    return expired


async def decide(ticket_id: str, allowed: bool, reason: str = "",
                 operator: str = "operator") -> bool:
    async with _LOCK:
        t = _PENDING.get(ticket_id)
        if t is None:
            return False
        t.verdict = {"allowed": allowed, "reason": reason or ("approved" if allowed else "denied")}
        t.event.set()
        try:
            sig = _signature(t.session_id, t.tool, t.target_id, t.args)
            _RECENT[sig] = {"ts": time.time(), "verdict": t.verdict}
        except Exception:
            pass
        _audit({
            "ts": time.time(), "event": "decide",
            "ticket_id": ticket_id, "allowed": allowed,
            "reason": reason, "operator": operator,
        })
        return True


async def list_pending() -> list[dict]:
    async with _LOCK:
        return [
            {
                "ticket_id": t.ticket_id,
                "tool": t.tool,
                "target": t.target_id,
                "args": t.args,
                "reason": t.reason,
                "preview": t.preview,
                "age_s": int(time.time() - t.created_at),
            }
            for t in _PENDING.values()
        ]


async def history(limit: int = 100) -> list[dict]:
    async with _LOCK:
        return list(reversed(_HISTORY[-limit:]))
