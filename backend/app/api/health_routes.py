"""Health and status endpoints."""
from __future__ import annotations
from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.providers_list import ALL_PROVIDERS

router = APIRouter(tags=["health"])


def _db_ok(db: Session) -> bool:
    try:
        db.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


@router.get("/healthz")
def healthz(db: Session = Depends(get_db)):
    """Liveness probe. Cheap. No external calls."""
    return {
        "status": "ok" if _db_ok(db) else "degraded",
        "version": "0.1.0",
        "db": "ok" if _db_ok(db) else "fail",
        "providers": ALL_PROVIDERS,
    }


@router.get("/health")
def health(db: Session = Depends(get_db)):
    """Full health snapshot. Includes supervisor, exporter, prober, circuits."""
    from app.runtime import supervisor_registry

    out: dict = {
        "status": "ok",
        "version": "0.1.0",
        "db": "ok" if _db_ok(db) else "fail",
    }

    sup = supervisor_registry.get_supervisor()
    out["supervisor"] = sup.snapshot() if sup else {"ready": False, "reason": "not started"}

    exp = supervisor_registry.get_exporter()
    out["exporter"] = exp.snapshot() if exp else {"exports": 0, "reason": "not started"}

    prb = supervisor_registry.get_prober()
    if prb:
        out["prober"] = prb.snapshot()
    else:
        out["prober"] = {"reason": "not started"}

    circuits = supervisor_registry.get_circuits()
    if circuits:
        out["circuits"] = circuits.snapshot()
    else:
        out["circuits"] = {}

    # aggregate status: degraded if any circuit is OPEN
    if circuits:
        any_open = any(c.to_dict().get("state") == "OPEN"
                       for c in circuits.all().values())
        if any_open:
            out["status"] = "degraded"

    return out
