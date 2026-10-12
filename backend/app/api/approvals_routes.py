"""Approval gate UI + loopback JSON API.

Dashboard page (login required, same as other /dashboard/* pages):
  GET  /dashboard/approvals

Loopback JSON (no auth, only reachable from the daemon host):
  GET  /dashboard/approvals.json
  GET  /dashboard/approvals/history.json
  POST /dashboard/approvals/{ticket_id}/allow
  POST /dashboard/approvals/{ticket_id}/deny

Client-agnostic: a phone app, a shell script, or the dashboard all
use the same endpoints. Nothing in the endpoint code assumes a
specific tool, target, or provider.
"""
from __future__ import annotations
import json
from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse

from app.agent import approval_queue as aq
from app.api import web_common as W


router = APIRouter(prefix="/dashboard", tags=["approvals"])


# ── page ────────────────────────────────────────────────────────
_PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>AInterceptor \\u2014 Approvals</title>
<style>
  :root { color-scheme: dark; }
  * { box-sizing: border-box; }
  body { margin: 0; font-family: ui-sans-serif, system-ui, sans-serif;
         background: #0a0a0a; color: #e6e6e6; }
  .dashboard-nav { padding: 10px 20px; background: #0f0f0f;
                   border-bottom: 1px solid #1f1f1f; }
  .dashboard-nav a { color: #9a9a9a; text-decoration: none;
                     margin-right: 14px; font-size: 13px; }
  .dashboard-nav a.active { color: #fff; font-weight: 600; }
  .wrap { max-width: 980px; margin: 24px auto; padding: 0 20px; }
  h1 { font-size: 20px; margin: 0 0 6px; }
  p.sub { color: #888; margin: 0 0 20px; font-size: 13px; }
  table { width: 100%; border-collapse: collapse;
          background: #111; border: 1px solid #1f1f1f;
          border-radius: 8px; overflow: hidden; }
  th, td { padding: 10px 14px; text-align: left;
           font-size: 13px; border-bottom: 1px solid #1a1a1a;
           vertical-align: top; }
  th { background: #141414; color: #aaa; font-weight: 500; }
  tr:last-child td { border-bottom: 0; }
  code, pre { font-family: ui-monospace, SFMono-Regular, monospace;
              font-size: 12px; color: #c9d1d9; }
  pre { background: #0a0a0a; padding: 8px 10px; border-radius: 6px;
        border: 1px solid #1f1f1f; margin: 4px 0 0;
        max-height: 200px; overflow: auto; white-space: pre-wrap; }
  button { padding: 6px 12px; font-size: 12px; border-radius: 5px;
           border: 0; cursor: pointer; font-weight: 600; }
  button.allow { background: #16a34a; color: #fff; margin-right: 6px; }
  button.allow:hover { background: #15803d; }
  button.deny  { background: #dc2626; color: #fff; }
  button.deny:hover  { background: #b91c1c; }
  .empty { padding: 24px; text-align: center; color: #666;
           background: #111; border: 1px dashed #222;
           border-radius: 8px; font-size: 13px; }
  .age { color: #888; font-size: 12px; }
  .reason { color: #f59e0b; font-size: 12px; }
</style>
</head>
<body>
__NAV__
<div class="wrap">
  <h1>Pending approvals</h1>
  <p class="sub">The agent is waiting on a decision. Allow runs the
     tool; Deny returns a refusal to the agent. Timeout is
     enforced server-side.</p>
  <div id="pending"></div>

  <h1 style="margin-top:32px">Recent decisions</h1>
  <div id="history"></div>
</div>
<script>
async function refresh() {
  const p = await fetch('/dashboard/approvals.json').then(r => r.json());
  const h = await fetch('/dashboard/approvals/history.json').then(r => r.json());
  renderPending(p.pending || []);
  renderHistory(h.history || []);
}
function esc(s) {
  return String(s == null ? '' : s)
    .replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')
    .replace(/"/g,'&quot;');
}
function renderPending(items) {
  const el = document.getElementById('pending');
  if (!items.length) {
    el.innerHTML = '<div class="empty">No pending approvals. The agent is not blocked.</div>';
    return;
  }
  let html = '<table><thead><tr><th style="width:80px">Tool</th><th style="width:140px">Target</th><th>Arguments</th><th style="width:180px"></th></tr></thead><tbody>';
  for (const t of items) {
    html += '<tr>';
    html += '<td><code>' + esc(t.tool) + '</code></td>';
    html += '<td><code>' + esc(t.target) + '</code></td>';
    html += '<td><div class="reason">' + esc(t.reason) + '</div>';
    html += '<pre>' + esc(JSON.stringify(t.args, null, 2)) + '</pre>';
    html += '<div class="age">waiting ' + esc(t.age_s) + 's</div></td>';
    html += '<td><button class="allow" onclick="decide(\\'' + esc(t.ticket_id) + '\\', true)">Allow</button>';
    html += '<button class="deny" onclick="decide(\\'' + esc(t.ticket_id) + '\\', false)">Deny</button></td>';
    html += '</tr>';
  }
  html += '</tbody></table>';
  el.innerHTML = html;
}
function renderHistory(items) {
  const el = document.getElementById('history');
  if (!items.length) {
    el.innerHTML = '<div class="empty">No decisions yet.</div>';
    return;
  }
  let html = '<table><thead><tr><th>Tool</th><th>Target</th><th>Verdict</th><th>Reason</th></tr></thead><tbody>';
  for (const h of items.slice(0, 30)) {
    const v = h.verdict || {};
    const cls = v.allowed ? 'color:#16a34a' : 'color:#dc2626';
    html += '<tr><td><code>' + esc(h.tool) + '</code></td>';
    html += '<td><code>' + esc(h.target) + '</code></td>';
    html += '<td style="' + cls + '">' + (v.allowed ? 'allow' : 'deny') + '</td>';
    html += '<td class="age">' + esc(v.reason || '') + '</td></tr>';
  }
  html += '</tbody></table>';
  el.innerHTML = html;
}
async function decide(id, allow) {
  await fetch('/dashboard/approvals/' + id + '/' + (allow ? 'allow' : 'deny'),
              { method: 'POST' });
  refresh();
}
refresh();
setInterval(refresh, 3000);
</script>
</body>
</html>
"""


@router.get("/approvals", response_class=HTMLResponse)
async def approvals_page():
    nav = W.dashboard_nav("/dashboard/approvals")
    return HTMLResponse(_PAGE.replace("__NAV__", nav))


# ── JSON: pending ───────────────────────────────────────────────
@router.get("/approvals.json")
async def approvals_json():
    return JSONResponse({"pending": await aq.list_pending()})


@router.get("/approvals/history.json")
async def approvals_history_json():
    return JSONResponse({"history": await aq.history(100)})


@router.post("/approvals/{ticket_id}/allow")
async def approvals_allow(ticket_id: str):
    ok = await aq.decide(ticket_id, True, "approved via dashboard")
    if not ok:
        raise HTTPException(404, "ticket not found or already decided")
    return {"ok": True, "ticket_id": ticket_id, "decision": "allow"}


@router.post("/approvals/{ticket_id}/deny")
async def approvals_deny(ticket_id: str):
    ok = await aq.decide(ticket_id, False, "denied via dashboard")
    if not ok:
        raise HTTPException(404, "ticket not found or already decided")
    return {"ok": True, "ticket_id": ticket_id, "decision": "deny"}
