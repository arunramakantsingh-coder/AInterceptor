"""FastAPI dependencies."""
from __future__ import annotations
from fastapi import Depends, Header, HTTPException, Request
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.db.models import User, ApiKey
from app.auth import read_jwt, verify_api_key, verify_password


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

    # ── API key (sk-aint-*) ──
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

    # ── device token (sk-dev-*) ──
    if token.startswith("sk-dev-"):
        from app.db.models import Device
        prefix = token[:16]
        candidates = db.query(Device).filter(
            Device.token_prefix == prefix, Device.revoked_at.is_(None)
        ).all()
        for d in candidates:
            if verify_password(token, d.token_hash):
                user = db.get(User, d.user_id)
                if user and user.is_active:
                    from datetime import datetime, timezone
                    d.last_seen_at = datetime.now(timezone.utc)
                    db.commit()
                    return user
        raise HTTPException(401, "invalid device token")

    # ── JWT session cookie ──
    uid = read_jwt(token)
    if uid:
        user = db.get(User, uid)
        if user and user.is_active:
            return user
    raise HTTPException(401, "invalid token")

SESSION_COOKIE = "aint_session"


def current_user_web(request: Request, db: Session = Depends(get_db)) -> User:
    """Cookie-based auth for HTML routes.

    On failure: raises HTTPException(303) so the browser is redirected
    to /auth/login?next=<original path>. JSON clients should use
    current_user (Bearer header) or key_user (Bearer sk-aint-*) instead.
    """
    token = request.cookies.get(SESSION_COOKIE)
    next_path = request.url.path
    if not token:
        raise HTTPException(
            status_code=303,
            headers={"Location": f"/auth/login?next={next_path}"},
        )
    uid = read_jwt(token)
    if not uid:
        raise HTTPException(
            status_code=303,
            headers={"Location": f"/auth/login?next={next_path}"},
        )
    user = db.get(User, uid)
    if not user or not user.is_active:
        raise HTTPException(
            status_code=303,
            headers={"Location": f"/auth/login?next={next_path}"},
        )
    return user
