"""Password hashing and JWT helpers."""
from __future__ import annotations
import secrets, string
from datetime import datetime, timedelta, timezone
import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from app.config import settings

_ph = PasswordHasher()


def hash_password(pw: str) -> str:
    return _ph.hash(pw)


def verify_password(pw: str, h: str) -> bool:
    try:
        _ph.verify(h, pw)
        return True
    except VerifyMismatchError:
        return False
    except Exception:
        return False


def make_jwt(user_id: str) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": user_id,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(hours=settings.jwt_expiry_hours)).timestamp()),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")


def read_jwt(token: str) -> str | None:
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
        return payload.get("sub")
    except Exception:
        return None


_ALPHABET = string.ascii_letters + string.digits


def generate_api_key() -> tuple[str, str, str]:
    """Return (full_key, prefix, hash)."""
    raw = "".join(secrets.choice(_ALPHABET) for _ in range(40))
    full = f"sk-aint-{raw}"
    prefix = full[:16]
    return full, prefix, hash_password(full)


def verify_api_key(full: str, hashed: str) -> bool:
    return verify_password(full, hashed)
