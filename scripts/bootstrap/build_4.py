import pathlib, subprocess

ROOT = pathlib.Path.cwd()
APP = ROOT / "backend" / "app"
(APP / "runtime").mkdir(parents=True, exist_ok=True)

F = {}

F["backend/app/runtime/__init__.py"] = '"""Runtime dispatcher (Path A / Path B)."""\n'

F["backend/app/runtime/path_a.py"] = '''"""Path A — direct HTTPS with harvested cookies."""
from __future__ import annotations
import json
from typing import AsyncIterator
import httpx


class PathAError(Exception):
    pass


async def _stream_claude(session_state: dict, prompt: str) -> AsyncIterator[str]:
    cookies = {c["name"]: c["value"] for c in session_state.get("cookies", [])}
    # Placeholder endpoint — real one requires org_id + conversation setup
    raise PathAError("claude path A not implemented yet")


async def _stream_chatgpt(session_state: dict, prompt: str) -> AsyncIterator[str]:
    # ChatGPT always requires Path B (proof-of-work).
    raise PathAError("chatgpt requires path B")


async def _stream_deepseek(session_state: dict, prompt: str) -> AsyncIterator[str]:
    cookies = {c["name"]: c["value"] for c in session_state.get("cookies", [])}
    headers = {
        "Content-Type": "application/json",
        "Accept": "text/event-stream",
    }
    body = {"chat_session_id": None, "parent_message_id": None,
            "prompt": prompt, "ref_file_ids": [], "thinking_enabled": False}
    async with httpx.AsyncClient(cookies=cookies, headers=headers, timeout=120.0) as c:
        async with c.stream("POST",
                             "https://chat.deepseek.com/api/v0/chat/completion",
                             json=body) as r:
            if r.status_code in (401, 403):
                raise PathAError(f"session expired: {r.status_code}")
            r.raise_for_status()
            async for line in r.aiter_lines():
                if not line:
                    continue
                if line.startswith("data:"):
                    yield line[5:].strip()


async def _stream_gemini(session_state: dict, prompt: str) -> AsyncIterator[str]:
    raise PathAError("gemini path A not implemented yet")


_STREAMERS = {
    "claude": _stream_claude,
    "chatgpt": _stream_chatgpt,
    "deepseek": _stream_deepseek,
    "gemini": _stream_gemini,
}


async def stream(provider: str, session_state: dict, prompt: str) -> AsyncIterator[str]:
    fn = _STREAMERS.get(provider)
    if not fn:
        raise PathAError(f"no path A for {provider}")
    async for chunk in fn(session_state, prompt):
        yield chunk
'''

F["backend/app/runtime/dispatcher.py"] = '''"""Decide Path A vs Path B for each provider + session."""
from __future__ import annotations
from typing import AsyncIterator
from app.runtime import path_a

# Per-provider policy: which paths are supported and preferred
POLICY = {
    "claude":   {"a": True,  "b": True,  "prefer": "a"},
    "chatgpt":  {"a": False, "b": True,  "prefer": "b"},
    "gemini":   {"a": True,  "b": True,  "prefer": "a"},
    "deepseek": {"a": True,  "b": True,  "prefer": "a"},
}


class ProviderUnavailable(Exception):
    pass


async def stream_reply(provider: str, session_state: dict,
                       prompt: str) -> AsyncIterator[str]:
    """Yield delta strings. Provider-agnostic.

    Phase 1: Path A only, Path B in Phase 2.
    """
    policy = POLICY.get(provider)
    if not policy:
        raise ProviderUnavailable(f"unknown provider: {provider}")

    if policy["a"] and policy["prefer"] == "a":
        try:
            async for delta in path_a.stream(provider, session_state, prompt):
                yield delta
            return
        except path_a.PathAError:
            if not policy["b"]:
                raise ProviderUnavailable(
                    f"{provider}: path A failed and B disabled")
            # fall through to Path B (not implemented yet)
        except Exception as e:
            raise ProviderUnavailable(f"{provider} path A error: {e}")

    raise ProviderUnavailable(
        f"{provider}: only Path B available, not yet implemented (Phase 2)")
'''

F["backend/app/api/sessions_routes.py"] = '''"""Session upload + management endpoints."""
from __future__ import annotations
import json, pathlib
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from pydantic import BaseModel
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.db.models import User, UserSession
from app.deps import current_user
from app.crypto.aes import encrypt_for_user, decrypt_for_user
from app.config import settings

router = APIRouter(prefix="/api/sessions", tags=["sessions"])

VALID_PROVIDERS = {"claude", "chatgpt", "gemini", "deepseek"}


class SessionOut(BaseModel):
    id: str
    provider: str
    alias: str
    status: str
    created_at: str
    expires_at: str | None
    last_used_at: str | None


def _to_out(r: UserSession) -> SessionOut:
    return SessionOut(
        id=r.id, provider=r.provider, alias=r.alias, status=r.status,
        created_at=r.created_at.isoformat(),
        expires_at=r.expires_at.isoformat() if r.expires_at else None,
        last_used_at=r.last_used_at.isoformat() if r.last_used_at else None,
    )


@router.post("/upload", response_model=SessionOut)
async def upload(
    provider: str = Form(...),
    alias: str = Form("default"),
    file: UploadFile = File(...),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    if provider not in VALID_PROVIDERS:
        raise HTTPException(400, f"unknown provider: {provider}")
    if alias != "default" and not alias.isalnum():
        raise HTTPException(400, "alias must be alphanumeric")

    raw = await file.read()
    if len(raw) > 2 * 1024 * 1024:
        raise HTTPException(413, "session file too large")

    try:
        state = json.loads(raw.decode("utf-8"))
        if "cookies" not in state:
            raise ValueError("missing 'cookies'")
    except Exception as e:
        raise HTTPException(400, f"invalid storage_state: {e}")

    ct, nonce = encrypt_for_user(user.id, raw)

    existing = db.query(UserSession).filter(
        UserSession.user_id == user.id,
        UserSession.provider == provider,
        UserSession.alias == alias,
    ).first()

    if existing:
        existing.encrypted_blob = ct
        existing.nonce = nonce
        existing.status = "active"
        existing.created_at = datetime.utcnow()
        db.commit()
        db.refresh(existing)
        return _to_out(existing)

    row = UserSession(user_id=user.id, provider=provider, alias=alias,
                      encrypted_blob=ct, nonce=nonce, status="active")
    db.add(row)
    db.commit()
    db.refresh(row)
    return _to_out(row)


@router.get("", response_model=list[SessionOut])
def list_sessions(user: User = Depends(current_user), db: Session = Depends(get_db)):
    rows = db.query(UserSession).filter(UserSession.user_id == user.id).all()
    return [_to_out(r) for r in rows]


@router.delete("/{session_id}")
def delete(session_id: str, user: User = Depends(current_user),
           db: Session = Depends(get_db)):
    row = db.get(UserSession, session_id)
    if not row or row.user_id != user.id:
        raise HTTPException(404, "session not found")
    db.delete(row)
    db.commit()
    return {"ok": True}


def load_session_state(db: Session, user_id: str, provider: str,
                       alias: str = "default") -> dict:
    row = db.query(UserSession).filter(
        UserSession.user_id == user_id,
        UserSession.provider == provider,
        UserSession.alias == alias,
        UserSession.status == "active",
    ).first()
    if not row:
        raise HTTPException(404, f"no active session for {provider}")
    raw = decrypt_for_user(user_id, row.encrypted_blob, row.nonce)
    return json.loads(raw.decode("utf-8"))
'''

F["backend/app/api/chat_routes.py"] = '''"""OpenAI-compatible /v1/chat/completions endpoint."""
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
    return f"data: {json.dumps(payload)}\\n\\n"


@router.post("/chat/completions")
async def chat(body: ChatIn,
               auth: tuple[User, ApiKey] = Depends(key_user),
               db: Session = Depends(get_db)):
    user, key = auth
    provider = body.model.lower()
    if provider not in {"claude", "chatgpt", "gemini", "deepseek"}:
        raise HTTPException(400, f"unknown model: {body.model}")

    # Use last user message as prompt (Phase 1 simplification)
    prompt = next((m.content for m in reversed(body.messages)
                   if m.role == "user"), "")
    if not prompt.strip():
        raise HTTPException(400, "no user message found")

    state = load_session_state(db, user.id, provider)

    t0 = time.monotonic()
    captured = {"text": "", "status": "ok"}

    async def gen():
        try:
            async for delta in stream_reply(provider, state, prompt):
                captured["text"] += delta
                yield _openai_chunk(body.model, delta)
            yield _openai_chunk(body.model, "", "stop")
            yield "data: [DONE]\\n\\n"
        except ProviderUnavailable as e:
            captured["status"] = "provider_unavailable"
            err = {"error": {"message": str(e), "type": "provider_unavailable"}}
            yield f"data: {json.dumps(err)}\\n\\n"
            yield "data: [DONE]\\n\\n"
        except Exception as e:
            captured["status"] = "error"
            err = {"error": {"message": str(e), "type": "internal_error"}}
            yield f"data: {json.dumps(err)}\\n\\n"
            yield "data: [DONE]\\n\\n"
        finally:
            db.add(UsageEvent(
                user_id=user.id, api_key_id=key.id,
                provider=provider, model=body.model,
                tokens_in=len(prompt), tokens_out=len(captured["text"]),
                latency_ms=int((time.monotonic() - t0) * 1000),
                status=captured["status"], path="A"))
            key.last_used_at = datetime.now(timezone.utc)
            db.commit()

    return StreamingResponse(gen(), media_type="text/event-stream")
'''

# Update main.py to include new routers
main_path = ROOT / "backend" / "app" / "main.py"
main_txt = main_path.read_text(encoding="utf-8")
if "sessions_routes" not in main_txt:
    main_txt = main_txt.replace(
        "from app.api import auth_routes, keys_routes, health_routes",
        "from app.api import auth_routes, keys_routes, health_routes, sessions_routes, chat_routes",
    )
    main_txt = main_txt.replace(
        "app.include_router(keys_routes.router)",
        "app.include_router(keys_routes.router)\napp.include_router(sessions_routes.router)\napp.include_router(chat_routes.router)",
    )
    main_path.write_text(main_txt, encoding="utf-8", newline="\n")
    print("  [OK] backend/app/main.py updated")

for rel, txt in F.items():
    p = ROOT / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(txt, encoding="utf-8", newline="\n")
    print(f"  [OK] {rel}  ({len(txt)} B)")

def git(a):
    return subprocess.run(["git"]+a, cwd=ROOT, capture_output=True, text=True)
git(["add","-A"])
r = git(["commit","-m","feat(phase-1): sessions upload + /v1/chat/completions + Path A dispatcher"])
print((r.stdout.strip() or r.stderr.strip())[:400])
print("DONE — script 4/6. Run script 5 next.")
