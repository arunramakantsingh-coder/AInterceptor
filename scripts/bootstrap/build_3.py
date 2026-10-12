import pathlib, subprocess

ROOT = pathlib.Path.cwd()
API = ROOT / "backend" / "app" / "api"
API.mkdir(parents=True, exist_ok=True)

F = {}

F["backend/app/api/__init__.py"] = '"""API routes."""\n'

F["backend/app/auth.py"] = '''"""Password hashing and JWT helpers."""
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
'''

F["backend/app/deps.py"] = '''"""FastAPI dependencies."""
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
'''

F["backend/app/api/auth_routes.py"] = '''"""Auth endpoints."""
from __future__ import annotations
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.db.models import User
from app.auth import hash_password, verify_password, make_jwt
from app.deps import current_user

router = APIRouter(prefix="/api/auth", tags=["auth"])


class SignupIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class TokenOut(BaseModel):
    token: str
    user_id: str
    email: str


@router.post("/signup", response_model=TokenOut)
def signup(body: SignupIn, db: Session = Depends(get_db)):
    if db.query(User).filter(User.email == body.email).first():
        raise HTTPException(409, "email already registered")
    user = User(email=body.email, password_hash=hash_password(body.password))
    db.add(user)
    db.commit()
    db.refresh(user)
    return TokenOut(token=make_jwt(user.id), user_id=user.id, email=user.email)


@router.post("/login", response_model=TokenOut)
def login(body: LoginIn, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == body.email).first()
    if not user or not verify_password(body.password, user.password_hash):
        raise HTTPException(401, "invalid credentials")
    return TokenOut(token=make_jwt(user.id), user_id=user.id, email=user.email)


@router.get("/me")
def me(user: User = Depends(current_user)):
    return {"user_id": user.id, "email": user.email, "created_at": user.created_at.isoformat()}
'''

F["backend/app/api/keys_routes.py"] = '''"""API key endpoints."""
from __future__ import annotations
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.db.models import User, ApiKey
from app.auth import generate_api_key
from app.deps import current_user

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
def create(body: CreateKeyIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    full, prefix, hashed = generate_api_key()
    k = ApiKey(user_id=user.id, key_hash=hashed, key_prefix=prefix, name=body.name)
    db.add(k)
    db.commit()
    db.refresh(k)
    return CreateKeyOut(id=k.id, key=full, prefix=prefix, name=k.name)


@router.get("", response_model=list[KeyOut])
def list_keys(user: User = Depends(current_user), db: Session = Depends(get_db)):
    rows = db.query(ApiKey).filter(ApiKey.user_id == user.id).all()
    return [KeyOut(id=r.id, prefix=r.key_prefix, name=r.name,
                   created_at=r.created_at.isoformat(),
                   last_used_at=r.last_used_at.isoformat() if r.last_used_at else None,
                   revoked_at=r.revoked_at.isoformat() if r.revoked_at else None)
            for r in rows]


@router.delete("/{key_id}")
def revoke(key_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    k = db.get(ApiKey, key_id)
    if not k or k.user_id != user.id:
        raise HTTPException(404, "key not found")
    k.revoked_at = datetime.now(timezone.utc)
    db.commit()
    return {"ok": True}
'''

F["backend/app/api/health_routes.py"] = '''"""Health endpoint."""
from __future__ import annotations
from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session
from app.db.session import get_db

router = APIRouter(tags=["health"])

PROVIDERS = ["claude", "chatgpt", "gemini", "deepseek"]


@router.get("/healthz")
def healthz(db: Session = Depends(get_db)):
    db_ok = False
    try:
        db.execute(text("SELECT 1"))
        db_ok = True
    except Exception:
        db_ok = False
    return {
        "status": "ok" if db_ok else "degraded",
        "version": "0.1.0",
        "db": "ok" if db_ok else "fail",
        "providers": PROVIDERS,
    }
'''

F["backend/app/main.py"] = '''"""FastAPI app entrypoint."""
from __future__ import annotations
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api import auth_routes, keys_routes, health_routes

app = FastAPI(title="AInterceptor", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:4000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_routes.router)
app.include_router(auth_routes.router)
app.include_router(keys_routes.router)


@app.get("/")
def root():
    return {"name": "AInterceptor", "version": "0.1.0",
            "docs": "/docs", "health": "/healthz"}
'''

for rel, txt in F.items():
    p = ROOT / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(txt, encoding="utf-8", newline="\n")
    print(f"  [OK] {rel}  ({len(txt)} B)")

def git(a):
    return subprocess.run(["git"]+a, cwd=ROOT, capture_output=True, text=True)
git(["add","-A"])
r = git(["commit","-m","feat(phase-1): FastAPI app + auth + API key endpoints"])
print((r.stdout.strip() or r.stderr.strip())[:400])
print("DONE — script 3/6. Run script 4 next.")
