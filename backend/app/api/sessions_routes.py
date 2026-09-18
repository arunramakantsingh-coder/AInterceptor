"""Session upload + management endpoints."""
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
