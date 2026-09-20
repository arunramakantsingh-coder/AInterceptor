"""Device code flow — /api/devices/exchange + device token auth."""
from __future__ import annotations
import secrets
import string
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.db.models import User, Device, DeviceCode
from app.auth import hash_password, verify_password

router = APIRouter(prefix="/api/devices", tags=["devices"])

# Unambiguous alphabet — no 0/O, 1/I/L
CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
CODE_TTL = timedelta(minutes=10)

DEVICE_TOKEN_PREFIX = "sk-dev-"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def generate_device_code() -> str:
    """8-char code with a dash in the middle: XXXX-XXXX."""
    raw = "".join(secrets.choice(CODE_ALPHABET) for _ in range(8))
    return f"{raw[:4]}-{raw[4:]}"


def generate_device_token() -> tuple[str, str, str]:
    """Returns (full_token, prefix, hash)."""
    raw = "".join(secrets.choice(string.ascii_letters + string.digits)
                  for _ in range(40))
    full = f"{DEVICE_TOKEN_PREFIX}{raw}"
    prefix = full[:16]
    return full, prefix, hash_password(full)


class DeviceConnectIn(BaseModel):
    code: str = Field(min_length=6, max_length=12)
    device_name: str = Field(min_length=1, max_length=120)
    os: str | None = Field(default=None, max_length=32)


class DeviceConnectOut(BaseModel):
    token: str
    server_hint: str
    device_id: str
    message: str


def _normalize(code: str) -> str:
    """Accept HK4PQR7W, hk4p-qr7w, HK4P-QR7W — normalize to XXXX-XXXX."""
    raw = "".join(c for c in code.upper() if c.isalnum())
    if len(raw) != 8:
        return code.upper().strip()
    return f"{raw[:4]}-{raw[4:]}"


@router.post("/exchange", response_model=DeviceConnectOut)
def exchange(body: DeviceConnectIn, db: Session = Depends(get_db)):
    code = _normalize(body.code)

    row = db.get(DeviceCode, code)
    if not row:
        raise HTTPException(404, "invalid or expired code")
    now = _now()
    exp = row.expires_at
    if exp.tzinfo is None:
        exp = exp.replace(tzinfo=timezone.utc)
    if exp < now:
        raise HTTPException(410, "code expired — request a new one")
    if row.consumed_at is not None:
        raise HTTPException(409, "code already used — request a new one")

    user = db.get(User, row.user_id)
    if not user or not user.is_active:
        raise HTTPException(403, "user not active")

    # consume the code
    row.consumed_at = now

    # create the device
    full_token, prefix, hashed = generate_device_token()
    dev = Device(
        user_id=user.id,
        name=body.device_name,
        os=body.os,
        token_hash=hashed,
        token_prefix=prefix,
        last_seen_at=now,
    )
    db.add(dev)
    db.commit()
    db.refresh(dev)

    return DeviceConnectOut(
        token=full_token,
        server_hint="",
        device_id=dev.id,
        message=f"Device '{dev.name}' connected. Save the token — it will not be shown again.",
    )


def device_user(authorization: str = Header(...),
                db: Session = Depends(get_db)) -> tuple[User, Device]:
    """Bearer auth that accepts sk-dev-* device tokens."""
    if not authorization.startswith("Bearer "):
        raise HTTPException(401, "invalid authorization header")
    token = authorization[7:]
    if not token.startswith(DEVICE_TOKEN_PREFIX):
        raise HTTPException(401, "not a device token")
    prefix = token[:16]
    candidates = db.query(Device).filter(
        Device.token_prefix == prefix, Device.revoked_at.is_(None)
    ).all()
    for d in candidates:
        if verify_password(token, d.token_hash):
            user = db.get(User, d.user_id)
            if not user or not user.is_active:
                raise HTTPException(401, "user inactive")
            d.last_seen_at = _now()
            db.commit()
            return user, d
    raise HTTPException(401, "invalid device token")
