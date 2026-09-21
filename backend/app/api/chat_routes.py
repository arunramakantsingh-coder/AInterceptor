"""OpenAI-compatible /v1/chat/completions endpoint."""
from __future__ import annotations
import json, time, uuid
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
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
    role: str
    content: str


class ChatIn(BaseModel):
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

    # Use last user message as prompt (Phase 1 simplification)
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
