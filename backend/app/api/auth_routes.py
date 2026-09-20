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
        '<p class="muted" style="margin-top:20px">Already have an account? '
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
        '<p class="muted" style="margin-top:20px">Need an account? '
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
