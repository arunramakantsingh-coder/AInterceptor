"""Health endpoint."""
from __future__ import annotations
from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session
from app.db.session import get_db

router = APIRouter(tags=["health"])

from app.providers_list import ALL_PROVIDERS as PROVIDERS


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
