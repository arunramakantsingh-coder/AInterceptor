"""OpenAI-compatible /v1/chat/completions endpoint."""
from __future__ import annotations
import json, time, uuid
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, Header, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.db.models import User, ApiKey, UsageEvent
from app.deps import key_user
from app.api.sessions_routes import load_session_state
from app.runtime.dispatcher import stream_reply, ProviderUnavailable

router = APIRouter(prefix="/v1", tags=["chat"])


class Message(BaseModel):
    # Extra="allow" so OpenAI agent clients can send tool_calls,
    # tool_call_id, name, and any future fields without 422-ing the
    # whole request. We only read role + content downstream.
    model_config = {"extra": "allow"}

    role: str
    # content is a string for text turns, null for a pure tool_call
    # assistant turn, and can be a list of parts for multimodal input.
    content: str | list | None = None


class ChatIn(BaseModel):
    tools: list[dict] | None = None
    tool_choice: str | dict | None = None
    model: str
    messages: list[Message]
    stream: bool = True


def _openai_chunk(model: str, delta: str, finish: str | None = None) -> str:
    payload = {
        "id": f"chatcmpl-{uuid.uuid4().hex[:24]}",
        "object": "chat.completion.chunk",
        "created": int(time.time()),
        "model": model,
        "choices": [{
            "index": 0,
            "delta": ({"content": delta} if delta else {}),
            "finish_reason": finish,
        }],
    }
    return f"data: {json.dumps(payload)}\n\n"


def optional_key_user(
    authorization: str | None = Header(None),
    db: Session = Depends(get_db),
) -> tuple[User, ApiKey] | None:
    """Like `key_user`, but tolerates a missing Authorization header.

    Model listing is metadata: it must not require the caller to hold a key, or
    discovery fails and the client cannot even present a model picker. When a
    header IS supplied it is validated exactly as `key_user` does, so an invalid
    credential is still rejected rather than silently ignored.
    """
    if not authorization:
        return None
    return key_user(authorization=authorization, db=db)


@router.get("/models")
def list_models(
    auth: tuple[User, ApiKey] | None = Depends(optional_key_user),
) -> dict:
    """OpenAI-compatible model listing.

    Each model id IS a provider name: AInterceptor routes on the request's
    `model` field. This exists so OpenAI-compatible clients (the DeepSeek
    Harness among them) can discover providers dynamically instead of having
    every provider hand-listed in their configuration. Without it, discovery
    does a GET on this path and gets a 404.

    Active providers are listed first. Inactive ones are included, suffixed
    "(inactive)", so the catalogue is visible; calling one returns
    AInterceptor's own "no active session" error instead of a discovery failure.
    """
    # The control plane exposes a module-level singleton factory, not module
    # level list_* helpers - mirror health_routes here.
    from app.control_plane.state import get_state as _get_state

    _st = _get_state()
    try:
        active = list(_st.list_active())
        inactive = list(_st.list_inactive())
    except Exception:
        active, inactive = [], list(_st.list_all())

    created = int(time.time())
    data = [
        {"id": p, "object": "model", "created": created, "owned_by": "ainterceptor"}
        for p in active
    ] + [
        {"id": p, "object": "model", "created": created, "owned_by": "ainterceptor",
         "ainterceptor": {"status": "inactive"},
         "name": f"{p} (inactive)"}
        for p in inactive
    ]
    return {"object": "list", "data": data}


@router.post("/chat/completions")
async def chat(body: ChatIn,
               auth: tuple[User, ApiKey] = Depends(key_user),
               db: Session = Depends(get_db)):
    user, key = auth
    # Route via control plane (handles "auto", capabilities, or explicit providers)
    from app.control_plane.router import select, NoProviderAvailable
    try:
        provider = select(body.model)
    except NoProviderAvailable as e:
        raise HTTPException(503, str(e))

    # Per-provider tool syntax (Rule 18: lives in the provider file).
    # If the provider module doesn't expose these, shim falls back to
    # generic <tool_call> handling.
    import importlib as _importlib
    try:
        _provider_mod = _importlib.import_module(f"app.interception.{provider}")
    except Exception:
        _provider_mod = None
    _tool_prompt_fn = getattr(_provider_mod, "tool_prompt", None) if _provider_mod else None
    _extract_fn = getattr(_provider_mod, "extract_tool_calls", None) if _provider_mod else None

    # When the client sends OpenAI tools, build a text prompt
    # containing the tool catalog + full message history. Otherwise
    # keep the original "last user message" simplification.
    tools_active = bool(getattr(body, "tools", None))
    if tools_active:
        from app.runtime.tool_shim import build_full_prompt
        _msgs = []
        for _m in body.messages:
            if hasattr(_m, "model_dump"):
                _msgs.append(_m.model_dump())
            elif isinstance(_m, dict):
                _msgs.append(_m)
            else:
                _msgs.append({"role": getattr(_m, "role", ""),
                              "content": getattr(_m, "content", "")})
        prompt = build_full_prompt(_msgs, body.tools or [], _tool_prompt_fn)
    else:
        prompt = next((m.content for m in reversed(body.messages)
                       if m.role == "user"), "")
    if not prompt.strip():
        raise HTTPException(400, "no user message found")

    state = load_session_state(db, user.id, provider)

    t0 = time.monotonic()

    # ── non-streaming path ──────────────────────────────────────────
    if not body.stream:
        chunks: list[str] = []
        status = "ok"
        try:
            async for delta in stream_reply(provider, state, prompt):
                chunks.append(delta)
            if not chunks:
                status = "empty_stream"
        except ProviderUnavailable as e:
            status = "provider_unavailable"
            raise HTTPException(503, str(e))
        except Exception as e:
            status = "error"
            raise HTTPException(500, str(e))
        full = "".join(chunks)
        if tools_active:
            from app.runtime.tool_shim import parse_tool_calls, shape_response
            _clean, _calls = parse_tool_calls(full, _extract_fn)
            latency_ms = int((time.monotonic() - t0) * 1000)
            try:
                db.add(UsageEvent(
                    user_id=user.id, api_key_id=key.id,
                    provider=provider, model=body.model,
                    tokens_in=len(prompt), tokens_out=len(full),
                    latency_ms=latency_ms,
                    status="tool_calls" if _calls else "ok",
                    path="A"))
                from datetime import datetime, timezone as _tz
                key.last_used_at = datetime.now(_tz.utc)
                db.commit()
            except Exception:
                pass
            return shape_response(_clean, _calls, body.model)
        latency_ms = int((time.monotonic() - t0) * 1000)
        try:
            db.add(UsageEvent(
                user_id=user.id, api_key_id=key.id,
                provider=provider, model=body.model,
                tokens_in=len(prompt), tokens_out=len(full),
                latency_ms=latency_ms, status=status, path="A"))
            from datetime import datetime, timezone as _tz
            key.last_used_at = datetime.now(_tz.utc)
            db.commit()
        except Exception:
            pass
        return {
            "id": f"chatcmpl-{uuid.uuid4().hex[:24]}",
            "object": "chat.completion",
            "created": int(time.time()),
            "model": body.model,
            "choices": [{
                "index": 0,
                "message": {"role": "assistant", "content": full},
                "finish_reason": "stop",
            }],
            "usage": {
                "prompt_tokens": len(prompt),
                "completion_tokens": len(full),
                "total_tokens": len(prompt) + len(full),
            },
        }
    # ── streaming path (existing) ───────────────────────────────────
    captured = {"text": "", "status": "ok"}

    async def gen():
        delta_count = 0
        error_msg = None
        # When tools are active, buffer the whole reply, then parse for
        # <tool_call> blocks and emit either tool_calls chunks or a
        # plain content chunk. Cannot stream token-by-token here because
        # we do not know if the model will emit tool calls mid-reply.
        if tools_active:
            _buf: list[str] = []
            try:
                async for delta in stream_reply(provider, state, prompt):
                    _buf.append(delta)
                _full_reply = "".join(_buf)
                from app.runtime.tool_shim import parse_tool_calls, stream_chunks
                _clean, _calls = parse_tool_calls(_full_reply, _extract_fn)
                try:
                    import pathlib as _pl, json as _j
                    _pl.Path("/tmp/dsh_tool_debug/parsed_calls.json").write_text(
                        _j.dumps(_calls, indent=2))
                except Exception:
                    pass
                _cmpl_id = f"chatcmpl-{uuid.uuid4().hex[:24]}"
                for _frame in stream_chunks(_clean, _calls, body.model, _cmpl_id):
                    yield _frame
                captured["text"] = _full_reply
                captured["status"] = "tool_calls" if _calls else "ok"
            except ProviderUnavailable as e:
                err = {"error": {"message": str(e), "type": "provider_unavailable"}}
                yield f"data: {json.dumps(err)}\n\n"
                yield "data: [DONE]\n\n"
            except Exception as e:
                err = {"error": {"message": str(e), "type": "internal_error"}}
                yield f"data: {json.dumps(err)}\n\n"
                yield "data: [DONE]\n\n"
            return
        try:
            async for delta in stream_reply(provider, state, prompt):
                captured["text"] += delta
                delta_count += 1
                yield _openai_chunk(body.model, delta)
            if delta_count == 0:
                # Provider stream ended with no text — surface a diagnostic
                err = {"error": {
                    "message": f"{provider} returned no text (path A got HTTP 200 but no parsable deltas). "
                               f"Set AINTERCEPTOR_PATH_A_DEBUG=1 in .env and retry to see raw lines.",
                    "type": "empty_stream",
                }}
                yield f"data: {json.dumps(err)}\n\n"
                captured["status"] = "empty_stream"
            else:
                captured["status"] = "ok"
            yield _openai_chunk(body.model, "", "stop")
            yield "data: [DONE]\n\n"
        except ProviderUnavailable as e:
            captured["status"] = "provider_unavailable"
            err = {"error": {"message": str(e), "type": "provider_unavailable"}}
            yield f"data: {json.dumps(err)}\n\n"
            yield "data: [DONE]\n\n"
        except Exception as e:
            captured["status"] = "error"
            err = {"error": {"message": str(e), "type": "internal_error"}}
            yield f"data: {json.dumps(err)}\n\n"
            yield "data: [DONE]\n\n"
        finally:
            try:
                db.add(UsageEvent(
                    user_id=user.id, api_key_id=key.id,
                    provider=provider, model=body.model,
                    tokens_in=len(prompt), tokens_out=len(captured["text"]),
                    latency_ms=int((time.monotonic() - t0) * 1000),
                    status=captured["status"], path="A"))
                key.last_used_at = datetime.now(timezone.utc)
                db.commit()
            except Exception:
                pass

    return StreamingResponse(gen(), media_type="text/event-stream")
