"""Internal-only routes for admin tools (CLI, scripts) on the same host.

Bound to loopback only. No auth. Refuses any request that appears to
have come through a reverse proxy (Funnel, nginx, ...).

The CLI calls these over http://127.0.0.1:8000/internal/*.
"""
from __future__ import annotations
import json, os, time, uuid
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.db.models import User
from app.api.sessions_routes import load_session_state
from app.runtime.dispatcher import stream_reply, ProviderUnavailable

router = APIRouter(prefix="/internal", tags=["internal"])


def _is_loopback(request: Request) -> bool:
    """Strict loopback check. Rejects reverse-proxy traffic."""
    client = request.client
    if client is None or client.host not in ("127.0.0.1", "::1", "localhost"):
        return False
    # Any proxy header means the request came through something
    for h in ("x-forwarded-for", "x-real-ip", "x-forwarded-host", "forwarded"):
        if request.headers.get(h):
            return False
    # Host header must be loopback (Funnel sets Host to the public URL)
    host = (request.headers.get("host") or "").lower()
    if not host.startswith(("127.0.0.1", "localhost", "[::1]")):
        return False
    return True


class DispatchIn(BaseModel):
    provider: str
    prompt: str
    stream: bool = True
    user_email: str | None = None
    force_path: str | None = None  # "A" | "B" | "CLAUDE" | None


@router.post("/dispatch")
async def dispatch(body: DispatchIn, request: Request,
                   db: Session = Depends(get_db)):
    if not _is_loopback(request):
        raise HTTPException(403, "internal route: loopback only")

    email = (body.user_email
             or os.getenv("AINTERCEPTOR_ADMIN_EMAIL", "").strip())
    if not email:
        raise HTTPException(500, "no user_email and no AINTERCEPTOR_ADMIN_EMAIL")

    user = db.query(User).filter(User.email == email).first()
    if not user:
        raise HTTPException(404, f"user not found: {email}")

    try:
        state = load_session_state(db, user.id, body.provider)
    except Exception as e:
        raise HTTPException(500, f"session load failed: {e}")

    t0 = time.monotonic()
    request_id = f"internal-{uuid.uuid4().hex[:12]}"

    # Non-streaming: collect and return JSON
    if not body.stream:
        chunks: list[str] = []
        try:
            async for delta in stream_reply(
                body.provider, state, body.prompt,
                force_path=body.force_path,
            ):
                chunks.append(delta)
        except ProviderUnavailable as e:
            raise HTTPException(503, str(e))
        except Exception as e:
            raise HTTPException(500, str(e))
        return {
            "id": request_id,
            "provider": body.provider,
            "text": "".join(chunks),
            "latency_ms": int((time.monotonic() - t0) * 1000),
        }

    # Streaming: SSE with {"delta": "..."}
    async def gen():
        try:
            async for delta in stream_reply(
                body.provider, state, body.prompt,
                force_path=body.force_path,
            ):
                yield f"data: {json.dumps({'delta': delta})}\n\n"
        except ProviderUnavailable as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream")
