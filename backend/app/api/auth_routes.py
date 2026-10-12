"""Email + password authentication and session cookie."""
from __future__ import annotations
import re
from typing import Optional

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.db.models import User
from app.auth import hash_password, verify_password, make_jwt
from app.deps import SESSION_COOKIE, current_user_web
from app.api import web_common as W

router = APIRouter(prefix="/auth", tags=["auth"])

SESSION_TTL = 7 * 24 * 3600  # 7 days
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

GOOGLE_BTN = """<div style="margin: 18px 0; display:flex; align-items:center; gap:10px;">
<div style="flex:1; height:1px; background:#222;"></div>
<span class="muted" style="font-size:11px;">OR</span>
<div style="flex:1; height:1px; background:#222;"></div>
</div>
<a href="/auth/google?next=NEXTURL" class="btn btn-secondary"
   style="display:flex; align-items:center; justify-content:center; gap:8px; width:100%;
          background:#fff; color:#111; font-weight:600;">
<svg width="18" height="18" viewBox="0 0 48 48" xmlns="http://www.w3.org/2000/svg">
<path fill="#FFC107" d="M43.6 20.5H42V20H24v8h11.3C33.7 32.4 29.3 35.5 24 35.5c-6.4 0-11.6-5.2-11.6-11.5S17.6 12.5 24 12.5c3 0 5.7 1.1 7.8 3l5.7-5.7C34 6.5 29.3 4.5 24 4.5 13.2 4.5 4.5 13.2 4.5 24S13.2 43.5 24 43.5 43.5 34.8 43.5 24c0-1.2-.1-2.4-.3-3.5z"/>
<path fill="#FF3D00" d="M6.3 14.7l6.6 4.8C14.7 15.1 19 12.5 24 12.5c3 0 5.7 1.1 7.8 3l5.7-5.7C34 6.5 29.3 4.5 24 4.5c-7.5 0-14 4.3-17.7 10.2z"/>
<path fill="#4CAF50" d="M24 43.5c5.2 0 9.9-2 13.4-5.2l-6.2-5.2c-2 1.4-4.6 2.4-7.2 2.4-5.2 0-9.6-3.1-11.3-7.5l-6.5 5C9.9 39 16.4 43.5 24 43.5z"/>
<path fill="#1976D2" d="M43.6 20.5H42V20H24v8h11.3c-.8 2.3-2.3 4.3-4.1 5.8l6.2 5.2C41.9 35 43.5 30 43.5 24c0-1.2-.1-2.4-.3-3.5z"/>
</svg>
Continue with Google</a>"""


def _google_btn(next_: str) -> str:
    return GOOGLE_BTN.replace("NEXTURL", next_)



def _safe_next(n: Optional[str]) -> str:
    """Only allow same-origin relative paths as ?next= target."""
    if not n:
        return "/dashboard"
    if not n.startswith("/") or n.startswith("//"):
        return "/dashboard"
    return n


def _set_session(resp: RedirectResponse, user_id: str) -> None:
    token = make_jwt(user_id)
    resp.set_cookie(SESSION_COOKIE, token, max_age=SESSION_TTL,
                    httponly=True, samesite="lax", path="/")


def _signup_form(err: str = "", email: str = "", next_: str = "/dashboard") -> str:
    body = (
        '<div class="auth-wrap"><div class="card">'
        '<h2>Create your account</h2>'
        '<p class="muted">Sign up to connect AI providers and generate API keys.</p>'
        '<form method="POST" action="/auth/signup">'
        f'<input type="hidden" name="next" value="{W.esc(next_)}">'
        '<label>Email</label>'
        f'<input type="email" name="email" value="{W.esc(email)}" autofocus required>'
        '<label>Password (10+ characters)</label>'
        '<input type="password" name="password" minlength="10" required>'
        '<label>Name (optional)</label>'
        '<input type="text" name="name" placeholder="Your name">'
        '<div style="margin-top:20px"><button type="submit">Create account</button></div>'
        f'{err}'
        '</form>'
        + _google_btn(next_)
        + '<p class="muted" style="margin-top:20px">Already have an account? '
        f'<a href="/auth/login?next={W.esc(next_)}">Sign in</a></p>'
        '</div></div>'
    )
    return W.page("Sign up", body, W.topbar(None))


def _login_form(err: str = "", email: str = "", next_: str = "/dashboard") -> str:
    body = (
        '<div class="auth-wrap"><div class="card">'
        '<h2>Sign in</h2>'
        '<p class="muted">Welcome back.</p>'
        '<form method="POST" action="/auth/login">'
        f'<input type="hidden" name="next" value="{W.esc(next_)}">'
        '<label>Email</label>'
        f'<input type="email" name="email" value="{W.esc(email)}" autofocus required>'
        '<label>Password</label>'
        '<input type="password" name="password" required>'
        '<div style="margin-top:20px"><button type="submit">Sign in</button></div>'
        f'{err}'
        '</form>'
        + _google_btn(next_)
        + '<p class="muted" style="margin-top:20px">Need an account? '
        f'<a href="/auth/signup?next={W.esc(next_)}">Sign up</a></p>'
        '</div></div>'
    )
    return W.page("Sign in", body, W.topbar(None))


@router.get("/signup", response_class=HTMLResponse)
def signup_get(next: str = "/dashboard"):
    return HTMLResponse(_signup_form(next_=_safe_next(next)))


@router.post("/signup")
def signup_post(
    email: str = Form(...),
    password: str = Form(...),
    name: str = Form(""),
    next: str = Form("/dashboard"),
    db: Session = Depends(get_db),
):
    email = (email or "").strip().lower()
    name = (name or "").strip() or None
    next_ = _safe_next(next)

    if not EMAIL_RE.match(email):
        return HTMLResponse(_signup_form('<div class="err">Invalid email address.</div>',
                                         email, next_), status_code=400)
    if len(password) < 10:
        return HTMLResponse(_signup_form('<div class="err">Password must be at least 10 characters.</div>',
                                         email, next_), status_code=400)

    existing = db.query(User).filter(User.email == email).first()
    if existing:
        return HTMLResponse(_signup_form('<div class="err">That email is already registered. '
                                         '<a href="/auth/login">Sign in</a>.</div>',
                                         email, next_), status_code=409)

    user = User(email=email, password_hash=hash_password(password), name=name)
    db.add(user)
    db.commit()
    db.refresh(user)

    resp = RedirectResponse(url=next_, status_code=303)
    _set_session(resp, user.id)
    return resp


@router.get("/login", response_class=HTMLResponse)
def login_get(next: str = "/dashboard"):
    return HTMLResponse(_login_form(next_=_safe_next(next)))


@router.post("/login")
def login_post(
    email: str = Form(...),
    password: str = Form(...),
    next: str = Form("/dashboard"),
    db: Session = Depends(get_db),
):
    email = (email or "").strip().lower()
    next_ = _safe_next(next)
    user = db.query(User).filter(User.email == email).first()
    if not user or not user.is_active or not verify_password(password, user.password_hash):
        return HTMLResponse(_login_form('<div class="err">Invalid email or password.</div>',
                                        email, next_), status_code=401)

    resp = RedirectResponse(url=next_, status_code=303)
    _set_session(resp, user.id)
    return resp


@router.get("/logout")
def logout():
    resp = RedirectResponse(url="/auth/login", status_code=303)
    resp.delete_cookie(SESSION_COOKIE, path="/")
    return resp


@router.get("/me")
def me(user: User = Depends(current_user_web)):
    return {"id": user.id, "email": user.email, "name": user.name}
