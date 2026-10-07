"""Translate OpenAI tool-calling protocol into plain-text prompts for
web-UI providers, and parse their replies back into OpenAI-shaped
tool_calls responses.

dsh (and any OpenAI-compatible agent client) sends:
  - messages: [{role, content}, ...]  (system, user, assistant, tool)
  - tools:    [{type: "function", function: {name, description, parameters}}]

The web-UI provider (DeepSeek/Claude/Gemini web) only understands a
text prompt and produces text. We:
  1. Build a text prompt from system + tool definitions + history
  2. Send that via the existing stream_reply()
  3. Parse the reply for <tool_call>...</tool_call> blocks
  4. Shape the result as an OpenAI response (content or tool_calls)
"""
from __future__ import annotations
import json
import re
import time
import uuid

TOOL_CALL_OPEN = "<tool_call>"
TOOL_CALL_CLOSE = "</tool_call>"
_TOOL_CALL_RE = re.compile(
    re.escape(TOOL_CALL_OPEN) + r"\s*(.*?)\s*" + re.escape(TOOL_CALL_CLOSE),
    re.DOTALL,
)


def _render_content(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        out = []
        for c in content:
            if isinstance(c, dict):
                out.append(c.get("text") or c.get("content") or "")
            else:
                out.append(str(c))
        return "".join(out)
    return str(content or "")


def render_tool_definitions(tools: list[dict]) -> str:
    if not tools:
        return ""
    lines = [
        "# Available tools",
        "",
        "You have access to the tools listed below. To call a tool, emit "
        "EXACTLY this block in your reply and nothing else in that turn:",
        "",
        TOOL_CALL_OPEN,
        '{"name": "<tool_name>", "arguments": {<json object>}}',
        TOOL_CALL_CLOSE,
        "",
        "Emit one block per tool call. You may emit multiple blocks in one "
        "reply. After emitting the block(s), STOP — do not narrate, explain, "
        "or continue the conversation. The harness will run the tools and "
        "send the results back.",
        "",
        "## Tool list",
    ]
    for t in tools:
        fn = t.get("function") or {}
        name = fn.get("name") or "?"
        desc = (fn.get("description") or "").strip()
        params = fn.get("parameters") or {}
        lines.append(f"- **{name}** — {desc}")
        if params:
            schema_str = json.dumps(params, separators=(",", ":"))
            if len(schema_str) > 700:
                schema_str = schema_str[:700] + "...(truncated)"
            lines.append(f"    arguments schema: {schema_str}")
    return "\n".join(lines)


def build_full_prompt(messages: list[dict], tools: list[dict]) -> str:
    """Assemble a single text prompt from OpenAI messages + tools."""
    system_parts: list[str] = []
    convo_parts: list[str] = []
    for m in messages:
        role = (m.get("role") or "").lower()
        text = _render_content(m.get("content"))
        if role == "system":
            if text.strip():
                system_parts.append(text)
        elif role == "user":
            convo_parts.append(f"USER: {text}")
        elif role == "assistant":
            # Skip empty assistant turns (tool-only turns) in the transcript
            if text.strip():
                convo_parts.append(f"ASSISTANT: {text}")
        elif role == "tool":
            # A tool result coming back from the harness
            name = m.get("name") or m.get("tool_call_id") or "tool"
            convo_parts.append(f"TOOL RESULT ({name}): {text}")

    tool_block = render_tool_definitions(tools)

    sections = []
    if system_parts:
        sections.append("\n\n".join(system_parts))
    if tool_block:
        sections.append(tool_block)
    if convo_parts:
        sections.append("# Conversation\n\n" + "\n\n".join(convo_parts))
    return "\n\n".join(sections)


def parse_tool_calls(text: str) -> tuple[str, list[dict]]:
    """Return (clean_text_without_blocks, tool_calls_list)."""
    calls: list[dict] = []
    for m in _TOOL_CALL_RE.finditer(text or ""):
        raw = m.group(1)
        try:
            obj = json.loads(raw)
        except json.JSONDecodeError:
            continue
        name = obj.get("name")
        args = obj.get("arguments", {})
        if not name:
            continue
        if isinstance(args, (dict, list)):
            args_str = json.dumps(args)
        else:
            args_str = str(args)
        calls.append({
            "id": f"call_{uuid.uuid4().hex[:16]}",
            "type": "function",
            "function": {"name": name, "arguments": args_str},
        })
    clean = _TOOL_CALL_RE.sub("", text or "").strip()
    return clean, calls


def shape_response(content: str, tool_calls: list[dict], model: str) -> dict:
    msg: dict = {"role": "assistant", "content": content or None}
    if tool_calls:
        msg["tool_calls"] = tool_calls
    finish = "tool_calls" if tool_calls else "stop"
    return {
        "id": f"chatcmpl-{uuid.uuid4().hex[:24]}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": model,
        "choices": [{"index": 0, "message": msg, "finish_reason": finish}],
        "usage": {
            "prompt_tokens": len(content or ""),
            "completion_tokens": len(content or ""),
            "total_tokens": 2 * len(content or ""),
        },
    }


def stream_chunks(content: str, tool_calls: list[dict], model: str, cmpl_id: str):
    """Yield SSE frames for a tools-aware non-streaming-shaped reply."""
    # Opening role chunk
    yield "data: " + json.dumps({
        "id": cmpl_id, "object": "chat.completion.chunk",
        "created": int(time.time()), "model": model,
        "choices": [{"index": 0, "delta": {"role": "assistant"}, "finish_reason": None}],
    }) + "\n\n"

    if tool_calls:
        for idx, tc in enumerate(tool_calls):
            yield "data: " + json.dumps({
                "id": cmpl_id, "object": "chat.completion.chunk",
                "created": int(time.time()), "model": model,
                "choices": [{"index": 0, "delta": {
                    "tool_calls": [{
                        "index": idx,
                        "id": tc["id"],
                        "type": "function",
                        "function": {
                            "name": tc["function"]["name"],
                            "arguments": tc["function"]["arguments"],
                        },
                    }]
                }, "finish_reason": None}],
            }) + "\n\n"
        finish = "tool_calls"
    else:
        yield "data: " + json.dumps({
            "id": cmpl_id, "object": "chat.completion.chunk",
            "created": int(time.time()), "model": model,
            "choices": [{"index": 0, "delta": {"content": content or ""}, "finish_reason": None}],
        }) + "\n\n"
        finish = "stop"

    yield "data: " + json.dumps({
        "id": cmpl_id, "object": "chat.completion.chunk",
        "created": int(time.time()), "model": model,
        "choices": [{"index": 0, "delta": {}, "finish_reason": finish}],
    }) + "\n\n"
    yield "data: [DONE]\n\n"
