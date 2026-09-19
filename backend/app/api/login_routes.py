"""Login endpoints — bring Chrome on-screen for user login."""
from __future__ import annotations
import pathlib
import os
from fastapi import APIRouter, Depends, HTTPException
from app.deps import current_user
from app.db.models import User
from app.runtime import supervisor_registry
from app.runtime.login_helper import begin_login

router = APIRouter(prefix="/api/login", tags=["login"])


@router.post("/{provider}")
async def login(provider: str, user: User = Depends(current_user)):
    sup = supervisor_registry.get_supervisor()
    if sup is None:
        raise HTTPException(503, "browser supervisor not running")
    export_dir = pathlib.Path(os.environ.get(
        "AINTERCEPTOR_EXPORT_DIR",
        str(pathlib.Path.cwd() / ".ainterceptor" / "exports")))
    result = await begin_login(provider, sup, export_dir)
    if not result.get("ok"):
        raise HTTPException(400, result.get("error", "login failed"))
    return result
