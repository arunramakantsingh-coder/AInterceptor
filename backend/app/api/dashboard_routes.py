"""User dashboard — shell now, keys/sessions/devices in later phases."""
from __future__ import annotations
from fastapi import APIRouter, Depends
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.db.models import User, ApiKey, UserSession, Device
from app.deps import current_user_web
from app.api import web_common as W

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("", response_class=HTMLResponse)
def dashboard_home(user: User = Depends(current_user_web),
                   db: Session = Depends(get_db)):
    key_count = db.query(ApiKey).filter(
        ApiKey.user_id == user.id, ApiKey.revoked_at.is_(None)).count()
    sess_count = db.query(UserSession).filter(
        UserSession.user_id == user.id, UserSession.status == "active").count()
    dev_count = db.query(Device).filter(
        Device.user_id == user.id, Device.revoked_at.is_(None)).count()

    body = f'''
<div class="container">
  <h2>Welcome{", " + W.esc(user.name) if user.name else ""}</h2>
  <p class="muted" style="margin-top:6px">Signed in as {W.esc(user.email)}</p>

  <div class="grid" style="grid-template-columns:repeat(auto-fit,minmax(220px,1fr)); margin-top:28px;">
    <div class="card">
      <h3>API keys</h3>
      <p style="font-size:32px; font-weight:700; margin:6px 0 10px;">{key_count}</p>
      <a class="btn btn-secondary" href="/dashboard/keys">Manage keys →</a>
    </div>
    <div class="card">
      <h3>Provider sessions</h3>
      <p style="font-size:32px; font-weight:700; margin:6px 0 10px;">{sess_count}</p>
      <a class="btn btn-secondary" href="/dashboard/sessions">View sessions →</a>
    </div>
    <div class="card">
      <h3>Devices</h3>
      <p style="font-size:32px; font-weight:700; margin:6px 0 10px;">{dev_count}</p>
      <a class="btn btn-secondary" href="/dashboard/devices">Manage devices →</a>
    </div>
  </div>

  <div class="card" style="margin-top:24px;">
    <h3>Quick start</h3>
    <ol class="muted" style="line-height:1.9; padding-left:20px; margin:8px 0 0;">
      <li>Generate an API key on <a href="/dashboard/keys">the keys page</a>.</li>
      <li>Install <code>airouter-agent</code> on your laptop (Phase D).</li>
      <li>Connect providers by logging in on your own machine.</li>
    </ol>
  </div>
</div>
'''
    return HTMLResponse(W.page("Dashboard", body, W.topbar(user.email)))


@router.get("/keys", response_class=HTMLResponse)
def dashboard_keys(user: User = Depends(current_user_web),
                   db: Session = Depends(get_db)):
    body = f'''
<div class="container">
  <div class="row" style="justify-content:space-between;">
    <div><h2>API keys</h2>
      <p class="muted">Use these with CareerOS or any external app.</p></div>
    <a class="btn btn-secondary" href="/dashboard">← back</a>
  </div>
  <div class="card" style="margin-top:20px;">
    <p class="muted">Key management UI arrives in Phase B. For now, use the CLI:</p>
    <pre style="background:#0a0a0a; padding:14px; border-radius:6px; color:#ccc; font-size:12px; overflow-x:auto;">akeys create &lt;name&gt; --save
akeys list
akeys revoke &lt;id&gt;</pre>
  </div>
</div>
'''
    return HTMLResponse(W.page("API keys", body, W.topbar(user.email)))


@router.get("/sessions", response_class=HTMLResponse)
def dashboard_sessions(user: User = Depends(current_user_web),
                       db: Session = Depends(get_db)):
    rows = db.query(UserSession).filter(UserSession.user_id == user.id).all()
    if rows:
        trs = "".join(
            f'<tr><td style="padding:10px 8px;border-bottom:1px solid #1f1f1f;">{W.esc(r.provider)}</td>'
            f'<td style="padding:10px 8px;border-bottom:1px solid #1f1f1f;">{W.esc(r.alias)}</td>'
            f'<td style="padding:10px 8px;border-bottom:1px solid #1f1f1f;">{W.esc(r.status)}</td>'
            f'<td style="padding:10px 8px;border-bottom:1px solid #1f1f1f;">{r.created_at.strftime("%Y-%m-%d %H:%M")}</td></tr>'
            for r in rows)
        table = (
            '<table style="width:100%;border-collapse:collapse;font-size:13px;">'
            '<thead><tr style="text-align:left;color:#888;">'
            '<th style="padding:8px;">Provider</th><th style="padding:8px;">Alias</th>'
            '<th style="padding:8px;">Status</th><th style="padding:8px;">Created</th>'
            f'</tr></thead><tbody>{trs}</tbody></table>'
        )
    else:
        table = '<p class="muted">No sessions yet. Connect a provider to get started.</p>'
    body = f'''
<div class="container">
  <div class="row" style="justify-content:space-between;">
    <div><h2>Provider sessions</h2>
      <p class="muted">Each row is a logged-in provider stored for your account.</p></div>
    <a class="btn btn-secondary" href="/dashboard">← back</a>
  </div>
  <div class="card" style="margin-top:20px;">{table}</div>
</div>
'''
    return HTMLResponse(W.page("Sessions", body, W.topbar(user.email)))


@router.get("/devices", response_class=HTMLResponse)
def dashboard_devices(user: User = Depends(current_user_web),
                      db: Session = Depends(get_db)):
    rows = db.query(Device).filter(Device.user_id == user.id,
                                   Device.revoked_at.is_(None)).all()
    if rows:
        trs = "".join(
            f'<tr><td style="padding:10px 8px;border-bottom:1px solid #1f1f1f;">{W.esc(r.name)}</td>'
            f'<td style="padding:10px 8px;border-bottom:1px solid #1f1f1f;">{W.esc(r.os or "—")}</td>'
            f'<td style="padding:10px 8px;border-bottom:1px solid #1f1f1f;">'
            f'{r.last_seen_at.strftime("%Y-%m-%d %H:%M") if r.last_seen_at else "never"}</td></tr>'
            for r in rows)
        table = (
            '<table style="width:100%;border-collapse:collapse;font-size:13px;">'
            '<thead><tr style="text-align:left;color:#888;">'
            '<th style="padding:8px;">Name</th><th style="padding:8px;">OS</th>'
            '<th style="padding:8px;">Last seen</th></tr></thead>'
            f'<tbody>{trs}</tbody></table>'
        )
    else:
        table = '<p class="muted">No devices connected. Device flow arrives in Phase D.</p>'
    body = f'''
<div class="container">
  <div class="row" style="justify-content:space-between;">
    <div><h2>Devices</h2>
      <p class="muted">Laptops that can upload sessions on your behalf.</p></div>
    <a class="btn btn-secondary" href="/dashboard">← back</a>
  </div>
  <div class="card" style="margin-top:20px;">{table}</div>
</div>
'''
    return HTMLResponse(W.page("Devices", body, W.topbar(user.email)))
