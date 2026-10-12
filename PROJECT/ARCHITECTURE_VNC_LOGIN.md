# VNC-Browser Login — Architecture

Status: in-progress (Batch 1/4 complete)
Owner: AInterceptor admin
Last updated: 2026-09-21

## Purpose

Let a user log into any AI provider (ChatGPT, Claude, Gemini, DeepSeek,
etc.) using nothing but their own web browser — no VNC client, no Python
install, no cookie extraction. The user opens a URL, sees a Chrome window,
logs in normally, closes the tab.

## Why not "just a URL with cookie extraction"

Every target provider sets its session credential as an **HttpOnly cookie**.
JavaScript running on any origin cannot read HttpOnly cookies, by design.

  ChatGPT  __Secure-next-auth.session-token    HttpOnly  yes
  Claude   sessionKey                          HttpOnly  yes
  Gemini   SECURE_1PSID, SECURE_1PSIDTS        HttpOnly  yes
  DeepSeek ds_session_id                       HttpOnly  yes

So a client-side page (bookmarklet, DevTools snippet, extension-less
JS) cannot extract the session. The only ways to read it are:

  1. A process that owns the browser (Playwright, an extension)
  2. A process that sees raw HTTP (a proxy)

We chose option 1 — but on the VM, where the browser is *ours*, and we
present it to the user through noVNC (a WebSocket-based VNC client that
runs entirely inside a browser).

## Architecture

    user's browser
         │
         ▼   https://<host>/login/<provider>
    ┌──────────────────────────────────────────────────┐
    │  FastAPI  (port 8000)                            │
    │    GET  /login/<provider>       branded page     │
    │    POST /login/<provider>/auth  admin password   │
    │    GET  /login/<provider>/static/*  noVNC assets │
    │    WS   /login/<provider>/ws    proxy to websockify │
    └──────────────────────────────────────────────────┘
         │  (internal 127.0.0.1 only)
         ▼
    ┌──────────────────────────────────────────────────┐
    │  websockify     127.0.0.1:6080  (noVNC assets)   │
    └──────────────────────────────────────────────────┘
         │
         ▼
    ┌──────────────────────────────────────────────────┐
    │  x11vnc         127.0.0.1:5900                   │
    └──────────────────────────────────────────────────┘
         │
         ▼
    ┌──────────────────────────────────────────────────┐
    │  Xvfb :99                                        │
    │    └── Chrome (CDP 9222)                         │
    │          tab: chatgpt / claude / gemini / etc.   │
    └──────────────────────────────────────────────────┘

## Security model

Layers, in order:

1. **Network boundary**: today, Tailscale. Ports 5900 and 6080 bind to
   127.0.0.1 only; port 8000 also binds 127.0.0.1 in the current
   `run-linux.sh`. Nothing is reachable except over the Tailscale
   interface on 100.82.62.82.

2. **Admin password gate** (to be built, Batch 2): the `/login/<provider>`
   page requires a password set via `aconfig set AINTERCEPTOR_WEB_LOGIN_PASSWORD`.
   A short-lived signed cookie unlocks the iframe.

3. **VNC password** (already in place): x11vnc requires
   `~/.vnc/passwd`. The password is embedded in the iframe URL via
   `?password=...` — which is safe because the page itself is behind
   the admin password gate and the URL never leaves the user's browser.

4. **Single-tab focus** (to be built, Batch 2): before serving the iframe,
   the FastAPI route calls the supervisor to bring the target provider's
   Chrome tab to front and move Chrome on-screen. Nothing else on the
   Xvfb desktop is visible or clickable.

## Publishing outside Tailscale (future)

Today's URL is only reachable on the Tailscale network. When we're ready
to expose this to external users, we do NOT open ports on the VM. Instead:

### Option A — Tailscale Funnel (recommended)

Exposes a single HTTPS endpoint publicly, managed by Tailscale, with
automatic TLS. One command on the VM:

    sudo tailscale funnel --bg 8000

Tailscale returns a stable hostname like:

    https://ainterceptor.<tailnet>.ts.net

This hostname is public. The admin password gate (Batch 2) becomes the
authentication boundary. Funnel only exposes the one port (8000).
Ports 5900/6080 remain bound to 127.0.0.1 — they are never reachable
from outside.

### Option B — Tailscale MagicDNS (tailnet-only)

    http://ainterceptor:8000
    http://ainterceptor.<tailnet>.ts.net:8000

Only devices that have joined the tailnet can resolve and reach this.
No public exposure at all.

### What we choose when

  Phase 1 (now)        Tailscale IP + admin password
  Phase 2              MagicDNS hostname (nicer URLs, same access model)
  Phase 3 (external)   Tailscale Funnel + hardened auth
  Phase 4 (scale)      Real reverse proxy (Caddy/nginx) + auth provider
                       (OAuth, SAML) if user count justifies it

## What this replaces / does not replace

  Replaces       the manual "ssh in, run alogin, connect a VNC client"
                 workflow for admins.
  Does not replace the agent-based flow (airouter-agent) for users who
                 can install Python. That flow stays as-is; both
                 coexist.

  Two flows, one codebase:
    - Admins / no-install users  →  /login/<provider>  (noVNC)
    - CareerOS / external apps   →  API key + /v1/...  (to be built)

## Failure modes and how they surface

  x11vnc down          →  502 on the iframe WS
  websockify down      →  502 on the iframe WS
  Chrome not running   →  /login/<provider> shows "browser not ready"
                          with a link to restart
  Provider tab missing →  fastapi moves to home_url and retries once
  Password wrong       →  form error, no cookie set
  VNC password wrong   →  noVNC prints its own error inside the iframe

## Files

  backend/app/api/login_routes.py         FastAPI routes (Batch 2)
  backend/app/api/templates/login.html    branded page (Batch 2)
  /opt/noVNC                              noVNC client assets
  ~/.vnc/passwd                           VNC password (already exists)
  ~/.vnc/x11vnc.log                       x11vnc log
  ~/.vnc/websockify.log                   websockify log

## Open items

  - Decide password rotation policy for AINTERCEPTOR_WEB_LOGIN_PASSWORD
  - Rate-limit the /auth POST (batch 2)
  - Decide cookie lifetime (default 8h; enough for one login session)
  - Decide whether to lock Xvfb to fullscreen Chrome for extra realism
