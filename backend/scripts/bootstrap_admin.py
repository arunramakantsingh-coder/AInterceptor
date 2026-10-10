"""Create admin user + first API key. Idempotent.

Usage:  python -m scripts.bootstrap_admin
"""
from __future__ import annotations
import pathlib
import secrets
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from app.db.session import SessionLocal
from app.db.models import User, ApiKey
from app.auth import hash_password, generate_api_key


ADMIN_EMAIL = "admin@ainterceptor.local"
KEY_NAME    = "agent-bootstrap"
KEY_FILE    = pathlib.Path.home() / ".ainterceptor" / "admin_api_key.txt"


def main() -> int:
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == ADMIN_EMAIL).first()
        if user:
            print(f"[i] admin user exists: {user.id}")
        else:
            # inspect model for the password column name
            cols = {c.name for c in User.__table__.columns}
            pw_col = next((n for n in ("password_hash", "hashed_password", "password")
                           if n in cols), None)
            if pw_col is None:
                print(f"[FAIL] cannot find password column; User columns: {sorted(cols)}")
                return 1
            user = User(email=ADMIN_EMAIL, is_active=True,
                        **{pw_col: hash_password(secrets.token_urlsafe(32))})
            db.add(user)
            db.commit()
            db.refresh(user)
            print(f"[OK] created admin user: {user.id}")

        # mint API key if none active
        existing = db.query(ApiKey).filter(
            ApiKey.user_id == user.id, ApiKey.revoked_at.is_(None)
        ).first()
        if existing:
            print(f"[i] active key already exists (prefix {existing.key_prefix})")
            print(f"     file: {KEY_FILE}")
            return 0

        full, prefix, hashed = generate_api_key()
        k = ApiKey(user_id=user.id, key_hash=hashed, key_prefix=prefix, name=KEY_NAME)
        db.add(k)
        db.commit()
        db.refresh(k)

        KEY_FILE.parent.mkdir(parents=True, exist_ok=True)
        KEY_FILE.write_text(full + "\n", encoding="utf-8")
        try:
            KEY_FILE.chmod(0o600)
        except Exception:
            pass

        print()
        print("=" * 60)
        print(" ADMIN API KEY CREATED")
        print("=" * 60)
        print(f"  id:      {k.id}")
        print(f"  prefix:  {prefix}")
        print(f"  token:   {full}")
        print(f"  saved:   {KEY_FILE} (chmod 600)")
        print()
        print("  The agent uses this as:  --token <the token above>")
        print("=" * 60)
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
