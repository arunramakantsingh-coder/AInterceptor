import pathlib, subprocess

ROOT = pathlib.Path.cwd()
BE = ROOT / "backend" / "app"
for d in ["config","crypto","db","db/models"]:
    (BE / d).mkdir(parents=True, exist_ok=True)

F = {}

F["backend/app/__init__.py"] = '"""AInterceptor backend application."""\n'

F["backend/app/config.py"] = '''"""Application settings loaded from environment."""
from __future__ import annotations
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    master_key: str          # base64, 32 bytes
    jwt_secret: str
    jwt_expiry_hours: int = 720
    database_url: str
    log_level: str = "INFO"
    sessions_dir: str = "/app/sessions"


settings = Settings()
'''

F["backend/app/crypto/__init__.py"] = '"""Cryptographic helpers."""\n'

F["backend/app/crypto/aes.py"] = '''"""Per-user key derivation + AES-GCM for session blobs."""
from __future__ import annotations
import base64, os
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from app.config import settings


def _master_key() -> bytes:
    raw = base64.b64decode(settings.master_key)
    if len(raw) != 32:
        raise ValueError("MASTER_KEY must be 32 bytes base64-encoded")
    return raw


def derive_subkey(user_id: str) -> bytes:
    hkdf = HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=user_id.encode("utf-8"),
        info=b"session-v1",
    )
    return hkdf.derive(_master_key())


def encrypt_for_user(user_id: str, plaintext: bytes) -> tuple[bytes, bytes]:
    key = derive_subkey(user_id)
    nonce = os.urandom(12)
    ct = AESGCM(key).encrypt(nonce, plaintext, user_id.encode("utf-8"))
    return ct, nonce


def decrypt_for_user(user_id: str, ciphertext: bytes, nonce: bytes) -> bytes:
    key = derive_subkey(user_id)
    return AESGCM(key).decrypt(nonce, ciphertext, user_id.encode("utf-8"))
'''

F["backend/app/db/__init__.py"] = '"""Database package."""\n'

F["backend/app/db/session.py"] = '''"""SQLAlchemy engine + sessionmaker."""
from __future__ import annotations
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase
from app.config import settings


class Base(DeclarativeBase):
    pass


engine = create_engine(settings.database_url, pool_pre_ping=True, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
'''

F["backend/app/db/models/__init__.py"] = '''from app.db.models.user import User
from app.db.models.api_key import ApiKey
from app.db.models.user_session import UserSession
from app.db.models.usage_event import UsageEvent

__all__ = ["User", "ApiKey", "UserSession", "UsageEvent"]
'''

F["backend/app/db/models/user.py"] = '''from __future__ import annotations
import uuid
from datetime import datetime, timezone
from sqlalchemy import String, Boolean, DateTime
from sqlalchemy.orm import Mapped, mapped_column
from app.db.session import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True,
                                    default=lambda: str(uuid.uuid4()))
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
'''

F["backend/app/db/models/api_key.py"] = '''from __future__ import annotations
import uuid
from datetime import datetime
from sqlalchemy import String, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from app.db.session import Base
from app.db.models.user import utcnow


class ApiKey(Base):
    __tablename__ = "api_keys"

    id: Mapped[str] = mapped_column(String(36), primary_key=True,
                                    default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), index=True)
    key_hash: Mapped[str] = mapped_column(String(255))
    key_prefix: Mapped[str] = mapped_column(String(32), index=True)
    name: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
'''

F["backend/app/db/models/user_session.py"] = '''from __future__ import annotations
import uuid
from datetime import datetime
from sqlalchemy import String, DateTime, ForeignKey, LargeBinary, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from app.db.session import Base
from app.db.models.user import utcnow


class UserSession(Base):
    __tablename__ = "user_sessions"
    __table_args__ = (UniqueConstraint("user_id", "provider", "alias", name="uq_user_provider_alias"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True,
                                    default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), index=True)
    provider: Mapped[str] = mapped_column(String(32), index=True)
    alias: Mapped[str] = mapped_column(String(32), default="default")
    encrypted_blob: Mapped[bytes] = mapped_column(LargeBinary)
    nonce: Mapped[bytes] = mapped_column(LargeBinary)
    status: Mapped[str] = mapped_column(String(32), default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
'''

F["backend/app/db/models/usage_event.py"] = '''from __future__ import annotations
import uuid
from datetime import datetime
from sqlalchemy import String, Integer, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from app.db.session import Base
from app.db.models.user import utcnow


class UsageEvent(Base):
    __tablename__ = "usage_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True,
                                    default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), index=True)
    api_key_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("api_keys.id"), nullable=True)
    provider: Mapped[str] = mapped_column(String(32), index=True)
    model: Mapped[str] = mapped_column(String(64))
    tokens_in: Mapped[int] = mapped_column(Integer, default=0)
    tokens_out: Mapped[int] = mapped_column(Integer, default=0)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(32))
    path: Mapped[str] = mapped_column(String(1))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
'''

for rel, txt in F.items():
    p = ROOT / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(txt, encoding="utf-8", newline="\n")
    print(f"  [OK] {rel}  ({len(txt)} B)")

def git(a):
    return subprocess.run(["git"]+a, cwd=ROOT, capture_output=True, text=True)
git(["add","-A"])
r = git(["commit","-m","feat(phase-1): config, crypto (HKDF+AES-GCM), db models"])
print((r.stdout.strip() or r.stderr.strip())[:400])
print("DONE — script 2/6. Run script 3 next.")
