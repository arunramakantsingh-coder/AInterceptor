"""AIRouter Gateway authentication."""
from __future__ import annotations
import os
import secrets
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials

DEFAULT_DEV_KEY = "aro_local_dev"

def configured_api_key() -> str:
    return os.getenv("AINTERCEPTOR_API_KEY", DEFAULT_DEV_KEY)

def require_api_key(credentials: HTTPAuthorizationCredentials | None) -> None:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(status_code=401, detail="AIRouter API key required", headers={"WWW-Authenticate": "Bearer"})
    if not secrets.compare_digest(credentials.credentials, configured_api_key()):
        raise HTTPException(status_code=401, detail="Invalid AIRouter API key", headers={"WWW-Authenticate": "Bearer"})
