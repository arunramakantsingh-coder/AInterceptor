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


async def run_agent(
    *,
    stream_reply,
    provider: str,
    state,
    messages: list[dict],
    tools: list[dict],
    build_prompt_fn,
    parse_calls_fn,
    max_rounds: int = 8,
    max_seconds: int = 300,
) -> dict:
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

        clean, calls = parse_calls_fn(reply)

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
            try:
                result = tools_mod.run(name, args)
            except Exception as e:
                result = f"error running tool {name}: {e}"
            convo.append({
                "role": "tool", "tool_call_id": call["id"],
                "name": name, "content": str(result)[:50_000],
            })

    return {"content": f"[agent reached max_rounds={max_rounds}]",
            "rounds": max_rounds, "conversation": convo}
