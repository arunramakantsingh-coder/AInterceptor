"""Google OAuth 2.0 login."""
from __future__ import annotations
import base64, hashlib, hmac, json, os, secrets, urllib.error, urllib.parse, urllib.request
from typing import Optional
from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.db.models import User
from app.auth import make_jwt
from app.deps import SESSION_COOKIE
from app.api import web_common as W

router = APIRouter(prefix="/auth", tags=["auth-google"])
STATE_COOKIE = "aint_oauth_state"
SESSION_TTL = 7 * 24 * 3600

def _client_id(): return os.environ.get("AINTERCEPTOR_GOOGLE_CLIENT_ID", "").strip()
def _client_secret(): return os.environ.get("AINTERCEPTOR_GOOGLE_CLIENT_SECRET", "").strip()
def _public_url(): return os.environ.get("AINTERCEPTOR_PUBLIC_URL", "").rstrip("/")
def _redirect_uri(): return f"{_public_url()}/auth/google/callback"
def _configured(): return bool(_client_id() and _client_secret() and _public_url())
def _safe_next(n: Optional[str]) -> str:
    return n if n and n.startswith("/") and not n.startswith("//") else "/dashboard"
def _sign_state(p): return hmac.new(_client_secret().encode(), p.encode(), hashlib.sha256).hexdigest()

def _err_page(msg, status=400):
    body = ('<div class="auth-wrap"><div class="card"><h2>Sign-in failed</h2>'
            f'<p class="muted">{W.esc(msg)}</p>'
            '<p style="margin-top:20px"><a class="btn" href="/auth/login">Try again</a></p>'
            '</div></div>')
    return HTMLResponse(W.page("Sign-in error", body, W.topbar(None)), status_code=status)

@router.get("/google")
def google_start(next: str = "/dashboard"):
    if not _configured():
        return _err_page("Google sign-in not configured on this server.")
    state = secrets.token_urlsafe(24)
    safe_next = _safe_next(next)
    params = {
        "client_id": _client_id(),
        "redirect_uri": _redirect_uri(),
        "response_type": "code",
        "scope": "openid email profile",
        "state": state,
        "access_type": "online",
        "prompt": "select_account",
    }
    url = "https://accounts.google.com/o/oauth2/v2/auth?" + urllib.parse.urlencode(params)
    resp = RedirectResponse(url=url, status_code=303)
    payload = f"{state}|{safe_next}"
    resp.set_cookie(STATE_COOKIE, f"{payload}|{_sign_state(payload)}",
                    max_age=600, httponly=True, samesite="lax", path="/auth")
    return resp

@router.get("/google/callback")
def google_callback(request: Request, code: str = "", state: str = "", error: str = "",
                    db: Session = Depends(get_db)):
    if error: return _err_page(f"Google returned: {error}")
    if not code or not state: return _err_page("Missing code or state.")
    raw = request.cookies.get(STATE_COOKIE, "")
    try:
        s_stored, next_path, sig = raw.rsplit("|", 2)
    except ValueError:
        return _err_page("Invalid state cookie.")
    if not hmac.compare_digest(sig, _sign_state(f"{s_stored}|{next_path}")):
        return _err_page("State signature mismatch.")
    if s_stored != state:
        return _err_page("State mismatch.")

    body = urllib.parse.urlencode({
        "code": code, "client_id": _client_id(), "client_secret": _client_secret(),
        "redirect_uri": _redirect_uri(), "grant_type": "authorization_code",
    }).encode()
    req = urllib.request.Request(
        "https://oauth2.googleapis.com/token", data=body, method="POST",
        headers={"Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            tokens = json.loads(r.read())
    except urllib.error.HTTPError as e:
        return _err_page(f"Token exchange failed ({e.code}): {e.read().decode()[:200]}")
    except Exception as e:
        return _err_page(f"Token exchange failed: {e}")

    id_token = tokens.get("id_token")
    if not id_token: return _err_page("No id_token from Google.")
    try:
        payload_b64 = id_token.split(".")[1]
        pad = "=" * (-len(payload_b64) % 4)
        claims = json.loads(base64.urlsafe_b64decode(payload_b64 + pad).decode())
    except Exception as e:
        return _err_page(f"Bad id_token: {e}")

    sub = claims.get("sub") or ""
    email = (claims.get("email") or "").strip().lower()
    name = (claims.get("name") or "").strip() or None
    if not sub or not email: return _err_page("Missing sub/email.")
    if not claims.get("email_verified"): return _err_page("Email not verified.")

    user = db.query(User).filter(User.provider == "google", User.provider_id == sub).first()
    if user is None:
        user = db.query(User).filter(User.email == email).first()
        if user:
            user.provider = "google"; user.provider_id = sub
            if name and not user.name: user.name = name
            db.commit(); db.refresh(user)
        else:
            user = User(email=email, password_hash="", name=name,
                        provider="google", provider_id=sub)
            db.add(user); db.commit(); db.refresh(user)

    if not user.is_active: return _err_page("Account disabled.")

    token = make_jwt(user.id)
    resp = RedirectResponse(url=_safe_next(next_path), status_code=303)
    resp.set_cookie(SESSION_COOKIE, token, max_age=SESSION_TTL,
                    httponly=True, samesite="lax", path="/")
    resp.delete_cookie(STATE_COOKIE, path="/auth")
    return resp
