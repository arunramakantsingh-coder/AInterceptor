"""FastAPI dependencies."""
from __future__ import annotations
from fastapi import Depends, Header, HTTPException
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.db.models import User, ApiKey
from app.auth import read_jwt, verify_api_key


def current_user(authorization: str = Header(...), db: Session = Depends(get_db)) -> User:
    if not authorization.startswith("Bearer "):
        raise HTTPException(401, "invalid authorization header")
    token = authorization[7:]
    uid = read_jwt(token)
    if not uid:
        raise HTTPException(401, "invalid token")
    user = db.get(User, uid)
    if not user or not user.is_active:
        raise HTTPException(401, "user not found")
    return user


def key_user(authorization: str = Header(...), db: Session = Depends(get_db)) -> tuple[User, ApiKey]:
    if not authorization.startswith("Bearer "):
        raise HTTPException(401, "invalid authorization header")
    token = authorization[7:]
    if not token.startswith("sk-aint-"):
        raise HTTPException(401, "not an API key")
    prefix = token[:16]
    candidates = db.query(ApiKey).filter(ApiKey.key_prefix == prefix,
                                          ApiKey.revoked_at.is_(None)).all()
    for k in candidates:
        if verify_api_key(token, k.key_hash):
            user = db.get(User, k.user_id)
            if not user or not user.is_active:
                raise HTTPException(401, "user inactive")
            return user, k
    raise HTTPException(401, "invalid API key")

def current_user_or_key(authorization: str = Header(...),
                        db: Session = Depends(get_db)) -> User:
    """Accept either a JWT (browser) or an sk-aint-* API key (agent)."""
    if not authorization.startswith("Bearer "):
        raise HTTPException(401, "invalid authorization header")
    token = authorization[7:]
    if token.startswith("sk-aint-"):
        prefix = token[:16]
        candidates = db.query(ApiKey).filter(
            ApiKey.key_prefix == prefix, ApiKey.revoked_at.is_(None)
        ).all()
        for k in candidates:
            if verify_api_key(token, k.key_hash):
                user = db.get(User, k.user_id)
                if user and user.is_active:
                    return user
        raise HTTPException(401, "invalid API key")
    uid = read_jwt(token)
    if uid:
        user = db.get(User, uid)
        if user and user.is_active:
            return user
    raise HTTPException(401, "invalid token")
