"""Shared HTML chrome + helpers for web pages (signup, login, dashboard)."""
from __future__ import annotations

CSS = """
:root { color-scheme: dark; }
* { box-sizing: border-box; }
body { margin: 0; min-height: 100vh;
       font-family: ui-sans-serif, system-ui, -apple-system, sans-serif;
       background: #0a0a0a; color: #e6e6e6; }
a { color: #60a5fa; text-decoration: none; }
a:hover { text-decoration: underline; }
h1 { margin: 0; font-size: 18px; font-weight: 600; letter-spacing: .3px; }
h2 { margin: 0 0 8px; font-size: 22px; font-weight: 600; }
h3 { margin: 0 0 8px; font-size: 15px; font-weight: 600; color: #bbb; }
label { display: block; font-size: 12px; color: #999; margin: 14px 0 5px; }
input[type=email], input[type=password], input[type=text] {
  width: 100%; padding: 11px 13px; font-size: 14px;
  background: #0a0a0a; color: #fff; border: 1px solid #333;
  border-radius: 6px; outline: none; }
input:focus { border-color: #1d4ed8; }
button, .btn { display: inline-block; padding: 11px 18px; font-size: 14px;
  font-weight: 600; border: 0; border-radius: 6px; cursor: pointer;
  background: #1d4ed8; color: #fff; font-family: inherit; }
button:hover, .btn:hover { background: #2563eb; text-decoration: none; }
.btn-secondary { background: #222; color: #ccc; }
.btn-secondary:hover { background: #2a2a2a; }
.err { color: #f87171; font-size: 13px; margin-top: 14px; }
.ok  { color: #4ade80; font-size: 13px; margin-top: 14px; }
.muted { color: #888; font-size: 13px; }
.topbar { padding: 14px 20px; border-bottom: 1px solid #1f1f1f;
  display: flex; align-items: center; gap: 14px; background: #0f0f0f; }
.topbar .badge { background: #1d4ed8; color: #fff; font-size: 11px;
  font-weight: 700; padding: 3px 8px; border-radius: 4px;
  text-transform: uppercase; }
.topbar h1 { font-size: 15px; }
.topbar .spacer { flex: 1; }
.topbar a { font-size: 13px; color: #888; margin-left: 14px; }
.topbar a:hover { color: #fff; }
.auth-wrap { max-width: 380px; margin: 8vh auto 0; padding: 0 20px; }
.card { background: #111; border: 1px solid #222; border-radius: 10px;
        padding: 28px; }
.container { max-width: 960px; margin: 0 auto; padding: 32px 24px; }
.row { display: flex; gap: 12px; align-items: center; }
.grid { display: grid; gap: 14px; }
.dashboard-nav { display: flex; gap: 4px; padding: 0 20px; background: #0f0f0f; border-bottom: 1px solid #1f1f1f; }
.dashboard-nav a { padding: 10px 14px; font-size: 13px; color: #999; border-bottom: 2px solid transparent; }
.dashboard-nav a:hover { color: #fff; text-decoration: none; }
.dashboard-nav a.active { color: #fff; border-bottom-color: #1d4ed8; }
"""


def page(title: str, body: str, bar: str = "") -> str:
    return (
        '<!doctype html>\n'
        '<html lang="en">\n'
        '<head>\n'
        '<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width,initial-scale=1">\n'
        f'<title>{esc(title)} — AInterceptor</title>\n'
        f'<style>{CSS}</style>\n'
        '</head>\n'
        '<body>\n'
        f'{bar}\n'
        f'{body}\n'
        '</body>\n'
        '</html>\n'
    )


def topbar(email: str | None = None) -> str:
    if email:
        right = (
            f'<span class="muted">{esc(email)}</span>'
            '<a href="/dashboard">Dashboard</a>'
            '<a href="/auth/logout">Sign out</a>'
        )
    else:
        right = (
            '<a href="/auth/login">Sign in</a>'
            '<a href="/auth/signup">Sign up</a>'
        )
    return (
        '<div class="topbar">'
        '<span class="badge">AInterceptor</span>'
        '<h1>Dashboard</h1>'
        '<div class="spacer"></div>'
        f'{right}'
        '</div>'
    )


def esc(s: str | None) -> str:
    if s is None:
        return ""
    return (str(s).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))

def dashboard_nav(current: str = "") -> str:
    items = [
        ("/dashboard", "Overview"),
        ("/dashboard/agents", "Agents"),
        ("/dashboard/sessions", "Sessions"),
        ("/dashboard/devices", "Devices"),
        ("/dashboard/keys", "API keys"),
        ("/login", "Admin (VNC)"),
    ]
    parts = ['<div class="dashboard-nav">']
    for href, label in items:
        cls = "active" if href == current else ""
        parts.append(f'<a href="{href}" class="{cls}">{label}</a>')
    parts.append("</div>")
    return "".join(parts)
