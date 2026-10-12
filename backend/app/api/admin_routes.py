"""Admin routes for provider management."""
from __future__ import annotations
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from app.deps import current_user
from app.db.models import User
from app.control_plane.state import get_state
from app.control_plane.capability import SCORES, CAPABILITIES
from app.control_plane import router as cp_router
from app.control_plane.rate_limiter import get_limiter

router = APIRouter(prefix="/admin", tags=["admin"])


class ProviderAction(BaseModel):
    provider: str


@router.get("/providers")
def list_providers(user: User = Depends(current_user)):
    state = get_state()
    active = set(state.list_active())
    out = []
    for p in state.list_all():
        out.append({
            "provider": p,
            "active": p in active,
            "capabilities": SCORES.get(p, {}),
        })
    return {
        "active": sorted(active),
        "inactive": state.list_inactive(),
        "all": out,
        "capabilities": CAPABILITIES,
    }


@router.post("/providers/activate")
def activate(body: ProviderAction, user: User = Depends(current_user)):
    state = get_state()
    if body.provider.lower() not in state.list_all():
        raise HTTPException(404, f"unknown provider: {body.provider}")
    changed = state.activate(body.provider)
    return {"ok": True, "changed": changed, "active": state.list_active()}


@router.post("/providers/deactivate")
def deactivate(body: ProviderAction, user: User = Depends(current_user)):
    state = get_state()
    if body.provider.lower() not in state.list_all():
        raise HTTPException(404, f"unknown provider: {body.provider}")
    changed = state.deactivate(body.provider)
    return {"ok": True, "changed": changed, "active": state.list_active()}


@router.get("/circuits")
def circuits(user: User = Depends(current_user)):
    from app.runtime import supervisor_registry
    circuits = supervisor_registry.get_circuits()
    return circuits.snapshot() if circuits else {}


@router.get("/rate-limits")
def rate_limits(user: User = Depends(current_user)):
    return get_limiter().snapshot()


@router.get("/routes")
def routes(user: User = Depends(current_user)):
    return cp_router.snapshot()
