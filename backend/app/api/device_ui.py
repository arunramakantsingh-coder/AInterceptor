"""Dashboard: connect-a-device page (device code flow)."""
from __future__ import annotations
from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.db.models import User, Device, DeviceCode
from app.deps import current_user_web
from app.api import web_common as W
from app.api.device_routes import generate_device_code, CODE_TTL

router = APIRouter(prefix="/dashboard", tags=["dashboard-devices"])

# Copy helper — works over plain HTTP (navigator.clipboard requires HTTPS)
_COPY_JS = """
function _aintCopy(elId) {
  const el = document.getElementById(elId);
  if (!el) return;
  const text = el.innerText || el.value || el.textContent || '';
  if (navigator.clipboard && window.isSecureContext) {
    navigator.clipboard.writeText(text).then(() => _aintFlash(elId + '_btn'));
    return;
  }
  const ta = document.createElement('textarea');
  ta.value = text;
  ta.style.position = 'fixed';
  ta.style.left = '-9999px';
  document.body.appendChild(ta);
  ta.select();
  try { document.execCommand('copy'); _aintFlash(elId + '_btn'); }
  catch (e) { alert('Copy failed — select manually'); }
  document.body.removeChild(ta);
}
function _aintFlash(btnId) {
  const b = document.getElementById(btnId);
  if (!b) return;
  const old = b.textContent;
  b.textContent = 'copied';
  setTimeout(() => b.textContent = old, 1200);
}
"""



DEFAULT_SERVER = "http://100.82.62.82:8000"


def _connect_page(user: User, db: Session) -> HTMLResponse:
    now = datetime.now(timezone.utc)
    row = (db.query(DeviceCode)
           .filter(DeviceCode.user_id == user.id,
                   DeviceCode.consumed_at.is_(None),
                   DeviceCode.expires_at > now)
           .order_by(DeviceCode.created_at.desc())
           .first())

    if row:
        code = row.code
        exp_iso = row.expires_at.isoformat()
        full_cmd = (
            f"airouter-agent connect --server {DEFAULT_SERVER} --code {code}"
        )
        code_block = (
            '<div class="card" style="border-color:#1d4ed8;">'
            '<h3 style="color:#60a5fa;">Connect this device</h3>'
            '<p class="muted" style="margin-bottom:14px;">'
            'On the laptop you want to connect, open a terminal and run:'
            '</p>'
            '<div style="background:#0a0a0a; padding:16px; border-radius:6px;'
            ' font-family:monospace; font-size:13px; line-height:1.7; color:#ccc;'
            ' overflow-x:auto; margin-bottom:14px;">'
            f'<div id="fullcmd">airouter-agent connect --server {W.esc(DEFAULT_SERVER)} '
            f'--code {W.esc(code)}</div>'
            '</div>'
            '<div class="row" style="gap:10px; margin-bottom:14px;">'
            f'<button type="button" class="btn" style="padding:8px 16px; font-size:13px;"'
            f' id="fullcmd_btn" onclick="_aintCopy(\'fullcmd\')">Copy full command</button>'
            '<span class="muted">or copy just the code:</span>'
            f'<code id="code" style="font-size:16px; font-weight:700;'
            f' letter-spacing:2px; color:#fff;">{W.esc(code)}</code>'
            '<button type="button" class="btn-secondary"'
            ' style="padding:5px 12px; font-size:12px;"'
            f' id="code_btn" onclick="_aintCopy(\'code\')">copy</button>'
            '</div>'
            '<p class="muted" id="status" style="margin-top:4px;">'
            '<span style="color:#facc15;">&#9679; waiting&hellip;</span>'
            ' <span style="margin-left:8px;">expires in '
            '<span id="countdown">--</span></span></p>'
            '</div>'
            f'<script>{_COPY_JS}'
            f'const expires = new Date("{exp_iso}");'
            'const cd = document.getElementById("countdown");'
            'const st = document.getElementById("status");'
            'function tick() {'
            '  const s = Math.max(0, Math.round((expires - new Date())/1000));'
            '  const m = Math.floor(s/60), r = s % 60;'
            '  cd.textContent = m + ":" + String(r).padStart(2,"0");'
            '  if (s === 0) {'
            '    st.innerHTML = "&#9679; expired &mdash; refresh to get a new code";'
            '    clearInterval(t);'
            '  }'
            '}'
            'const t = setInterval(tick, 1000); tick();'
            'const poll = setInterval(async () => {'
            '  try {'
            f'    const r = await fetch("/dashboard/connect/status?code={W.esc(code)}");'
            '    const d = await r.json();'
            '    if (d.consumed) {'
            '      st.innerHTML = "&#9679; device connected!";'
            '      clearInterval(poll); clearInterval(t);'
            '      setTimeout(() => location.href = "/dashboard/devices", 1200);'
            '    }'
            '  } catch (e) {}'
            '}, 2000);'
            '</script>'
        )
        action_block = ""
    else:
        code_block = ""
        action_block = (
            '<div class="card" style="text-align:center; padding:40px;">'
            '<p class="muted" style="margin-bottom:20px;">'
            'No active code. Generate one to connect a new laptop.</p>'
            '<form method="POST" action="/dashboard/connect">'
            '<button type="submit">Generate device code</button>'
            '</form>'
            '</div>'
        )

    body = W.dashboard_nav("/dashboard/connect") + (
        '<div class="container">'
        '<div class="row" style="justify-content:space-between;">'
        '<div><h2>Connect a device</h2>'
        '<p class="muted">Link a laptop running airouter-agent to this account.</p></div>'
        '<a class="btn btn-secondary" href="/dashboard">&larr; back</a>'
        '</div>'
        f'<div style="margin-top:20px;">{code_block}</div>'
        f'{action_block}'
        '</div>'
    )
    return HTMLResponse(W.page("Connect device", body, W.topbar(user.email)))


@router.get("/connect", response_class=HTMLResponse)
def dashboard_connect(user: User = Depends(current_user_web),
                      db: Session = Depends(get_db)):
    return _connect_page(user, db)


@router.post("/connect", response_class=HTMLResponse)
def dashboard_connect_generate(user: User = Depends(current_user_web),
                               db: Session = Depends(get_db)):
    now = datetime.now(timezone.utc)
    db.query(DeviceCode).filter(
        DeviceCode.user_id == user.id,
        DeviceCode.consumed_at.is_(None),
    ).delete()
    code = generate_device_code()
    row = DeviceCode(code=code, user_id=user.id, expires_at=now + CODE_TTL)
    db.add(row)
    db.commit()
    return RedirectResponse(url="/dashboard/connect", status_code=303)


@router.get("/connect/status")
def dashboard_connect_status(code: str,
                             user: User = Depends(current_user_web),
                             db: Session = Depends(get_db)):
    row = db.get(DeviceCode, code)
    if not row or row.user_id != user.id:
        return {"consumed": False, "error": "not found"}
    return {
        "consumed": row.consumed_at is not None,
        "expires_at": row.expires_at.isoformat() if row.expires_at else None,
    }
