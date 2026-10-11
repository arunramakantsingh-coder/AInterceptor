"""Agentic loop.

Flow per round:
  1. Build a text prompt from (messages + tools) via build_prompt_fn
  2. Stream the AIP's reply via stream_reply(provider, state, prompt)
  3. Parse the reply for tool calls via parse_calls_fn
  4. If no calls: return the reply's text — DONE
  5. Else: execute each tool via tools.run(), append results as
     role="tool" messages, loop
"""
from __future__ import annotations
import json
import os
import time

from app.agent import tools as tools_mod
from app.agent import approval_queue as aq
from app.agent import permissions


async def run_agent(
    *,
    stream_reply,
    provider: str,
    state,
    messages: list[dict],
    tools: list[dict],
    build_prompt_fn,
    parse_calls_fn,
    session_id: str = "",
    max_rounds: int | None = None,
    max_seconds: int = 300,
) -> dict:
    if max_rounds is None:
        try:
            max_rounds = int(os.getenv("AGENT_MAX_ROUNDS", "30"))
        except ValueError:
            max_rounds = 30
    convo = [dict(m) for m in messages]
    started = time.monotonic()

    for round_i in range(max_rounds):
        if time.monotonic() - started > max_seconds:
            return {"content": f"[agent timeout after {max_seconds}s]",
                    "rounds": round_i, "conversation": convo}

        prompt = build_prompt_fn(convo, tools)

        chunks: list[str] = []
        async for d in stream_reply(provider, state, prompt):
            chunks.append(d)
        reply = "".join(chunks)

        try:
            import pathlib as _pl
            _d = _pl.Path("/tmp/ain_trace")
            _d.mkdir(exist_ok=True)
            (_d / f"round_{round_i}_raw.txt").write_text(reply)
        except Exception:
            pass

        clean, calls = parse_calls_fn(reply)

        try:
            import pathlib as _pl, json as _j
            _d = _pl.Path("/tmp/ain_trace")
            _d.mkdir(exist_ok=True)
            (_d / f"round_{round_i}_parsed.json").write_text(
                _j.dumps(calls, indent=2))
        except Exception:
            pass

        if not calls:
            return {"content": clean, "rounds": round_i + 1, "conversation": convo}

        convo.append({"role": "assistant", "content": clean})
        for call in calls:
            name = call["function"]["name"]
            try:
                args = json.loads(call["function"]["arguments"])
            except Exception as e:
                convo.append({
                    "role": "tool", "tool_call_id": call["id"],
                    "name": name, "content": f"error parsing args: {e}",
                })
                continue

            # ── Permission gate (L2) ─────────────────────────────
            target_id = args.get("target", "vm")
            decision, reason = permissions.evaluate(name, args)

            if decision == "deny":
                convo.append({
                    "role": "tool", "tool_call_id": call["id"],
                    "name": name,
                    "content": f"[permission denied] {reason}",
                })
                continue

            if decision == "ask":
                # 1. Cache hit? Recent approval for this exact call.
                cached = aq.check_recent(session_id, name, target_id, args)
                if cached is not None and cached.get("allowed"):
                    pass  # fall through to execute
                else:
                    # 2. Submit the ticket and wait BRIEFLY.
                    ticket = await aq.submit(
                        session_id=session_id,
                        request_id=str(call.get("id", "")),
                        tool=name,
                        target_id=target_id,
                        args=args,
                        reason=reason,
                    )
                    try:
                        verdict = await aq.wait(ticket, timeout=8.0)
                    except Exception:
                        verdict = {"allowed": False, "reason": "wait_failed"}
                    if not verdict.get("allowed"):
                        # 3. Not decided in 8s. Return a chat message
                        # with the ticket URL so the operator can
                        # approve on the dashboard. The next request
                        # with the same call will hit the cache.
                        import os as _os
                        base = _os.getenv("AINTERCEPTOR_PUBLIC_URL",
                                          "https://ainterceptor.taila2310c.ts.net")
                        url = f"{base}/dashboard/approvals"
                        preview = args.get("cmd") or args.get("path") or ""
                        msg = (
                            f"\n\n**[approval required]**\n"
                            f"Tool: `{name}` on `{target_id}`\n"
                            f"Reason: {reason}\n"
                            f"Preview: `{str(preview)[:160]}`\n\n"
                            f"Ticket: `{ticket.ticket_id}`\n"
                            f"Approve: {url}\n\n"
                            f"After approving, send the same message again "
                            f"\u2014 the decision will be reused."
                        )
                        return {
                            "content": (clean or "") + msg,
                            "rounds": round_i + 1,
                            "conversation": convo,
                            "approval_pending": ticket.ticket_id,
                        }

            # ── Execute (L3) ─────────────────────────────────────
            try:
                result = tools_mod.run(name, args)
            except Exception as e:
                result = f"error running tool {name}: {e}"
            convo.append({
                "role": "tool", "tool_call_id": call["id"],
                "name": name, "content": str(result)[:50_000],
            })

    # Round limit hit. Do NOT return an empty marker — the caller
    # loses the whole investigation. Instead make one final LLM call
    # (no tools this time) asking for a summary of what has been
    # learned, and return that.
    convo.append({
        "role": "user",
        "content": (
            f"You have reached the tool-round limit ({max_rounds} rounds). "
            "Do not call any more tools. In your reply, summarize "
            "everything you have learned so far. Mark any item as "
            "unverified if you could not confirm it. State briefly what "
            "you would investigate next if more rounds were available."
        ),
    })
    try:
        prompt = build_prompt_fn(convo, [])  # empty tools -> no more calls
        chunks: list[str] = []
        async for d in stream_reply(provider, state, prompt):
            chunks.append(d)
        raw = "".join(chunks)
        try:
            clean, _ = parse_calls_fn(raw)
        except Exception:
            clean = raw
        content = (clean or raw or
                   f"[agent reached max_rounds={max_rounds}; "
                   f"summarizer returned empty]")
    except Exception as e:
        content = (f"[agent reached max_rounds={max_rounds}; "
                   f"final summarization call failed: {e}]")
    return {
        "content": content,
        "rounds": max_rounds,
        "conversation": convo,
        "limit_reached": "max_rounds",
    }
