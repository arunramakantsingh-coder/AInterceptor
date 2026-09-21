"""User dashboard — shell + API keys UI."""
from __future__ import annotations
import time
from fastapi import APIRouter, Depends, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.db.models import User, ApiKey, UserSession, Device
from app.auth import generate_api_key
from app.deps import current_user_web
from app.api import web_common as W

router = APIRouter(prefix="/dashboard", tags=["dashboard"])

# One-time token reveal: after POST creates a key, the plaintext is held
# here for 60s so the following GET (PRG redirect) can display it once.
_pending_keys: dict[str, tuple[str, float]] = {}
_PENDING_TTL = 60


# ── home ─────────────────────────────────────────────────────────────

@router.get("", response_class=HTMLResponse)
def dashboard_home(user: User = Depends(current_user_web),
                   db: Session = Depends(get_db)):
    key_count = db.query(ApiKey).filter(
        ApiKey.user_id == user.id, ApiKey.revoked_at.is_(None)).count()
    sess_count = db.query(UserSession).filter(
        UserSession.user_id == user.id, UserSession.status == "active").count()
    dev_count = db.query(Device).filter(
        Device.user_id == user.id, Device.revoked_at.is_(None)).count()

    body = W.dashboard_nav("/dashboard") + f'''
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


# ── API keys ─────────────────────────────────────────────────────────

def _keys_page(user: User, db: Session,
               new_key: str | None = None, error: str = "") -> HTMLResponse:
    rows = (db.query(ApiKey)
            .filter(ApiKey.user_id == user.id)
            .order_by(ApiKey.created_at.desc())
            .all())

    if rows:
        trs = ""
        for r in rows:
            revoked = r.revoked_at is not None
            status = ('<span style="color:#f87171">revoked</span>' if revoked
                      else '<span style="color:#4ade80">active</span>')
            last_used = (r.last_used_at.strftime("%Y-%m-%d %H:%M")
                         if r.last_used_at else "never")
            action = "" if revoked else (
                f'<form method="POST" action="/dashboard/keys/{r.id}/revoke" '
                f'style="display:inline" '
                f'onsubmit="return confirm(\'Revoke this key? Apps using it will stop working.\')">'
                f'<button type="submit" class="btn-secondary" '
                f'style="padding:5px 12px; font-size:12px;">revoke</button></form>'
            )
            trs += (
                f'<tr>'
                f'<td style="padding:12px 8px;border-bottom:1px solid #1f1f1f;">'
                f'{W.esc(r.name)}</td>'
                f'<td style="padding:12px 8px;border-bottom:1px solid #1f1f1f;'
                f'font-family:monospace;font-size:12px;">{W.esc(r.key_prefix)}…</td>'
                f'<td style="padding:12px 8px;border-bottom:1px solid #1f1f1f;">{status}</td>'
                f'<td style="padding:12px 8px;border-bottom:1px solid #1f1f1f;'
                f'color:#888;font-size:12px;">{last_used}</td>'
                f'<td style="padding:12px 8px;border-bottom:1px solid #1f1f1f;'
                f'text-align:right;">{action}</td>'
                f'</tr>'
            )
        table = (
            '<table style="width:100%;border-collapse:collapse;font-size:13px;">'
            '<thead><tr style="text-align:left;color:#888;">'
            '<th style="padding:8px;">Name</th>'
            '<th style="padding:8px;">Prefix</th>'
            '<th style="padding:8px;">Status</th>'
            '<th style="padding:8px;">Last used</th>'
            '<th style="padding:8px;"></th>'
            '</tr></thead>'
            f'<tbody>{trs}</tbody></table>'
        )
    else:
        table = '<p class="muted">No keys yet. Create one below.</p>'

    new_block = ""
    if new_key:
        new_block = f'''
<div class="card" style="margin-top:20px; border-color:#1d4ed8;">
  <h3 style="color:#60a5fa;">Your new API key</h3>
  <p class="muted" style="margin-bottom:12px;">
    This is shown <strong>once</strong>. Copy it now — you won't be able to see it again.
  </p>
  <div style="display:flex; gap:8px; align-items:center;">
    <input type="text" value="{W.esc(new_key)}" readonly
           style="flex:1; font-family:monospace; font-size:13px;"
           onclick="this.select()" id="newkey">
    <button type="button" class="btn-secondary" onclick="
      navigator.clipboard.writeText(document.getElementById('newkey').value);
      this.textContent='copied';
      setTimeout(()=>this.textContent='copy', 1500);
    ">copy</button>
  </div>
</div>
'''

    err_block = f'<div class="err" style="margin-top:12px;">{W.esc(error)}</div>' if error else ""

    body = W.dashboard_nav("/dashboard/keys") + f'''
<div class="container">
  <div class="row" style="justify-content:space-between;">
    <div>
      <h2>API keys</h2>
      <p class="muted">Use these with CareerOS or any external app.</p>
    </div>
    <a class="btn btn-secondary" href="/dashboard">← back</a>
  </div>
  {new_block}
  <div class="card" style="margin-top:20px;">
    {table}
  </div>
  <div class="card" style="margin-top:20px;">
    <h3>Create a new key</h3>
    <form method="POST" action="/dashboard/keys" style="margin-top:10px;">
      <label>Key name (for your reference, e.g. "careeros-prod")</label>
      <input type="text" name="name" required maxlength="64"
             pattern="[a-zA-Z0-9_\\-]+"
             title="letters, digits, underscore, hyphen only"
             placeholder="careeros-prod" autocomplete="off">
      {err_block}
      <div style="margin-top:16px;"><button type="submit">Create key</button></div>
    </form>
  </div>
</div>
'''
    return HTMLResponse(W.page("API keys", body, W.topbar(user.email)))


@router.get("/keys", response_class=HTMLResponse)
def dashboard_keys(user: User = Depends(current_user_web),
                   db: Session = Depends(get_db)):
    new_key = None
    entry = _pending_keys.pop(user.id, None)
    if entry:
        token, ts = entry
        if time.time() - ts < _PENDING_TTL:
            new_key = token
    return _keys_page(user, db, new_key=new_key)


@router.post("/keys", response_class=HTMLResponse)
def dashboard_keys_create(
    name: str = Form(...),
    user: User = Depends(current_user_web),
    db: Session = Depends(get_db),
):
    name = (name or "").strip()
    if not name or len(name) > 64:
        return _keys_page(user, db, error="Name must be 1-64 characters.")
    if not all(c.isalnum() or c in "_-" for c in name):
        return _keys_page(user, db,
                          error="Name may only contain letters, digits, _, -")

    full, prefix, hashed = generate_api_key()
    row = ApiKey(user_id=user.id, key_hash=hashed, key_prefix=prefix, name=name)
    db.add(row)
    db.commit()

    # PRG: hold the plaintext briefly, redirect to GET /keys
    _pending_keys[user.id] = (full, time.time())
    return RedirectResponse(url="/dashboard/keys", status_code=303)


@router.post("/keys/{key_id}/revoke", response_class=HTMLResponse)
def dashboard_keys_revoke(
    key_id: str,
    user: User = Depends(current_user_web),
    db: Session = Depends(get_db),
):
    k = db.get(ApiKey, key_id)
    if not k or k.user_id != user.id:
        raise HTTPException(404, "key not found")
    if k.revoked_at is None:
        from datetime import datetime, timezone
        k.revoked_at = datetime.now(timezone.utc)
        db.commit()
    return RedirectResponse(url="/dashboard/keys", status_code=303)


# ── sessions ─────────────────────────────────────────────────────────

