"""API key endpoints."""
from __future__ import annotations
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.db.models import User, ApiKey
from app.auth import generate_api_key
from app.deps import current_user_or_key

router = APIRouter(prefix="/api/keys", tags=["keys"])


class CreateKeyIn(BaseModel):
    name: str = Field(min_length=1, max_length=64)


class CreateKeyOut(BaseModel):
    id: str
    key: str
    prefix: str
    name: str


class KeyOut(BaseModel):
    id: str
    prefix: str
    name: str
    created_at: str
    last_used_at: str | None
    revoked_at: str | None


@router.post("", response_model=CreateKeyOut)
def create(body: CreateKeyIn, user: User = Depends(current_user_or_key), db: Session = Depends(get_db)):
    full, prefix, hashed = generate_api_key()
    k = ApiKey(user_id=user.id, key_hash=hashed, key_prefix=prefix, name=body.name)
    db.add(k)
    db.commit()
    db.refresh(k)
    return CreateKeyOut(id=k.id, key=full, prefix=prefix, name=k.name)


@router.get("", response_model=list[KeyOut])
def list_keys(user: User = Depends(current_user_or_key), db: Session = Depends(get_db)):
    rows = db.query(ApiKey).filter(ApiKey.user_id == user.id).all()
    return [KeyOut(id=r.id, prefix=r.key_prefix, name=r.name,
                   created_at=r.created_at.isoformat(),
                   last_used_at=r.last_used_at.isoformat() if r.last_used_at else None,
                   revoked_at=r.revoked_at.isoformat() if r.revoked_at else None)
            for r in rows]


@router.delete("/{key_id}")
def revoke(key_id: str, user: User = Depends(current_user_or_key), db: Session = Depends(get_db)):
    k = db.get(ApiKey, key_id)
    if not k or k.user_id != user.id:
        raise HTTPException(404, "key not found")
    k.revoked_at = datetime.now(timezone.utc)
    db.commit()
    return {"ok": True}
