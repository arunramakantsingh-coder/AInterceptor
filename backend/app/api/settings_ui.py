"""Dashboard: settings page — account, password, linked providers, delete."""
from __future__ import annotations
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.db.models import User, ApiKey, UserSession, Device, DeviceCode
from app.auth import hash_password, verify_password
from app.deps import current_user_web, SESSION_COOKIE
from app.api import web_common as W

router = APIRouter(prefix="/dashboard", tags=["dashboard-settings"])


@router.get("/settings", response_class=HTMLResponse)
def settings_page(user: User = Depends(current_user_web),
                  db: Session = Depends(get_db),
                  saved: str = "", err: str = ""):
    # Account block
    linked = "Google" if (user.provider == "google") else "email + password"
    has_password = bool(user.password_hash)

    # Saved banner
    banner = ""
    if saved:
        banner = '<div class="card" style="background:#052e16; border-color:#166534; margin-bottom:16px; padding:14px 18px;"><span style="color:#4ade80;">&#10003; ' + W.esc(saved) + '</span></div>'
    if err:
        banner = '<div class="card" style="background:#450a0a; border-color:#7f1d1d; margin-bottom:16px; padding:14px 18px;"><span style="color:#f87171;">&#10007; ' + W.esc(err) + '</span></div>'

    # Change password block (only useful if they have a password OR want to add one)
    pw_form = (
        '<div class="card" style="margin-top:20px;">'
        '<h3>' + ('Change password' if has_password else 'Set password') + '</h3>'
        '<p class="muted" style="font-size:13px; margin-bottom:14px;">'
        + ('Your account currently uses Google sign-in only. Setting a password lets you log in with email too.'
           if not has_password else
           'Password must be at least 10 characters.')
        + '</p>'
        '<form method="POST" action="/dashboard/settings/password">'
        + ('<label>Current password</label>'
           '<input type="password" name="current" required autocomplete="current-password">'
           if has_password else '')
        + '<label>New password</label>'
        '<input type="password" name="new" minlength="10" required autocomplete="new-password">'
        '<label>Confirm new password</label>'
        '<input type="password" name="confirm" minlength="10" required autocomplete="new-password">'
        '<div style="margin-top:16px;"><button type="submit">Update password</button></div>'
        '</form></div>'
    )

    # Account info card
    account_card = (
        '<div class="card" style="margin-top:20px;">'
        '<h3>Account</h3>'
        '<div style="padding:10px 0;">'
        '<div class="muted" style="font-size:12px;">Email</div>'
        '<div style="margin-top:2px;">' + W.esc(user.email) + '</div>'
        '</div>'
        '<div style="padding:10px 0; border-top:1px solid #1f1f1f;">'
        '<div class="muted" style="font-size:12px;">Name</div>'
        '<div style="margin-top:2px;">' + (W.esc(user.name) if user.name else '<span class="muted">(not set)</span>') + '</div>'
        '</div>'
        '<div style="padding:10px 0; border-top:1px solid #1f1f1f;">'
        '<div class="muted" style="font-size:12px;">Sign-in method</div>'
        '<div style="margin-top:2px;">' + linked + '</div>'
        '</div>'
        '<div style="padding:10px 0; border-top:1px solid #1f1f1f;">'
        '<div class="muted" style="font-size:12px;">Member since</div>'
        '<div style="margin-top:2px;">' + (user.created_at.strftime("%Y-%m-%d") if user.created_at else "?") + '</div>'
        '</div>'
        '</div>'
    )

    # Stats
    kc = db.query(ApiKey).filter(ApiKey.user_id == user.id, ApiKey.revoked_at.is_(None)).count()
    sc = db.query(UserSession).filter(UserSession.user_id == user.id, UserSession.status == "active").count()
    dc = db.query(Device).filter(Device.user_id == user.id, Device.revoked_at.is_(None)).count()

    stats_card = (
        '<div class="card" style="margin-top:20px;">'
        '<h3>What this account owns</h3>'
        '<div class="grid" style="grid-template-columns:repeat(auto-fit,minmax(150px,1fr)); margin-top:10px;">'
        '<div><div class="muted" style="font-size:12px;">API keys</div>'
        '<div style="font-size:22px; font-weight:700;">' + str(kc) + '</div></div>'
        '<div><div class="muted" style="font-size:12px;">Sessions</div>'
        '<div style="font-size:22px; font-weight:700;">' + str(sc) + '</div></div>'
        '<div><div class="muted" style="font-size:12px;">Devices</div>'
        '<div style="font-size:22px; font-weight:700;">' + str(dc) + '</div></div>'
        '</div></div>'
    )

    # Danger zone
    danger = (
        '<div class="card" style="margin-top:20px; border-color:#7f1d1d;">'
        '<h3 style="color:#f87171;">Danger zone</h3>'
        '<p class="muted" style="font-size:13px; margin-bottom:14px;">'
        'Deleting your account removes every API key, session, and device '
        'registered to it. This cannot be undone.</p>'
        '<form method="POST" action="/dashboard/settings/delete" '
        'onsubmit="return confirm(\'Delete this account and everything in it?\')">'
        '<label>Type DELETE to confirm</label>'
        '<input type="text" name="confirm" placeholder="DELETE" '
        'style="font-family:monospace;" required>'
        '<div style="margin-top:16px;">'
        '<button type="submit" class="btn" '
        'style="background:#7f1d1d;">Delete account</button>'
        '</div></form></div>'
    )

    body = (
        W.dashboard_nav("/dashboard/settings")
        + '<div class="container" style="max-width:720px;">'
        + '<h2>Settings</h2>'
        + '<p class="muted">Manage your account.</p>'
        + banner
        + account_card
        + stats_card
        + pw_form
        + danger
        + '</div>'
    )
    return HTMLResponse(W.page("Settings", body, W.topbar(user.email)))


@router.post("/settings/password")
def settings_password(current: str = Form(""),
                      new: str = Form(...),
                      confirm: str = Form(...),
                      user: User = Depends(current_user_web),
                      db: Session = Depends(get_db)):
    from fastapi.responses import RedirectResponse
    if new != confirm:
        return RedirectResponse(url="/dashboard/settings?err=Passwords+do+not+match",
                                status_code=303)
    if len(new) < 10:
        return RedirectResponse(url="/dashboard/settings?err=Password+too+short",
                                status_code=303)
    if user.password_hash:
        if not verify_password(current or "", user.password_hash):
            return RedirectResponse(url="/dashboard/settings?err=Current+password+is+wrong",
                                    status_code=303)
    user.password_hash = hash_password(new)
    db.commit()
    return RedirectResponse(url="/dashboard/settings?saved=Password+updated",
                            status_code=303)


@router.post("/settings/delete")
def settings_delete(confirm: str = Form(...),
                    user: User = Depends(current_user_web),
                    db: Session = Depends(get_db)):
    from fastapi.responses import RedirectResponse
    if (confirm or "").strip() != "DELETE":
        return RedirectResponse(url="/dashboard/settings?err=Type+DELETE+to+confirm",
                                status_code=303)

    uid = user.id
    db.query(ApiKey).filter(ApiKey.user_id == uid).delete()
    db.query(UserSession).filter(UserSession.user_id == uid).delete()
    db.query(Device).filter(Device.user_id == uid).delete()
    db.query(DeviceCode).filter(DeviceCode.user_id == uid).delete()
    db.delete(user)
    db.commit()

    resp = RedirectResponse(url="/auth/login", status_code=303)
    resp.delete_cookie(SESSION_COOKIE, path="/")
    return resp
