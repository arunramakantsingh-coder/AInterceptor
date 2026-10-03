"""pytest configuration.

Adds repo root AND repo root's backend/ to sys.path so both import styles
work:
    from app.runtime import ...          (as the app does internally)
    from backend.app.runtime import ...  (as some tests do)
"""
import os
import sys
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent
BACKEND = ROOT / "backend"

for p in (str(ROOT), str(BACKEND)):
    if p not in sys.path:
        sys.path.insert(0, p)

# Set test-safe env vars early
os.environ.setdefault("MASTER_KEY", __import__("base64").b64encode(os.urandom(32)).decode())
os.environ.setdefault("JWT_SECRET", "test-secret-do-not-use")
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
