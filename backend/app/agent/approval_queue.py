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


async def submit(*, session_id: str, request_id: str,
                 tool: str, target_id: str, args: dict,
                 reason: str) -> Ticket:
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
    """Block until a decision or timeout. Returns the verdict dict."""
    timeout = timeout if timeout is not None else DEFAULT_TIMEOUT_S
    try:
        await asyncio.wait_for(ticket.event.wait(), timeout=timeout)
        verdict = ticket.verdict or {"allowed": False, "reason": "no verdict"}
    except asyncio.TimeoutError:
        verdict = {"allowed": False, "reason": "timeout"}
        ticket.verdict = verdict
        _audit({
            "ts": time.time(), "event": "timeout",
            "ticket_id": ticket.ticket_id,
            "reason": f"no decision in {timeout}s",
        })
    async with _LOCK:
        _PENDING.pop(ticket.ticket_id, None)
        _HISTORY.append({
            "ts": time.time(), "ticket_id": ticket.ticket_id,
            "tool": ticket.tool, "target": ticket.target_id,
            "verdict": verdict,
        })
        if len(_HISTORY) > 500:
            del _HISTORY[:-500]
    return verdict


async def decide(ticket_id: str, allowed: bool, reason: str = "",
                 operator: str = "operator") -> bool:
    async with _LOCK:
        t = _PENDING.get(ticket_id)
        if t is None:
            return False
        t.verdict = {"allowed": allowed, "reason": reason or ("approved" if allowed else "denied")}
        t.event.set()
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
