# AInterceptor — Session Log

Durable record of decisions, drifts, and options considered.

## 2026-09-21 — Path A primary, Path B fallback
Context: Needed a scalable routing story.
Options: (a) Path B primary, (b) Path A primary + B fallback, (c) both always
Chosen:  (b)
Why:     B costs a browser per user; A uses harvested cookies over HTTP.
Drift:   Original handoff treated A and B as equals. A is now canonical.
Impact:  dispatcher, runtime priority, /v1 design

## 2026-09-21 — VNC admin-only, agent is the product
Context: VNC-browser login works but one Chrome = one user.
Options: (a) scale VNC, (b) VNC for admin + agent for users
Chosen:  (b)
Drift:   VNC page originally pitched as user-facing. Scoped to admin.
Impact:  /login/<provider> stays; user onboarding via agent

## 2026-09-21 — noVNC embedded (not VNC client, not extension)
Context: How does a user log in without installing anything?
Options: (a) VNC client, (b) noVNC page, (c) browser extension
Chosen:  (b)
Why:     HttpOnly cookies rule out (c); hard install rules out (a).
Impact:  /login/<provider>, x11vnc bound to 127.0.0.1

## 2026-09-21 — OpenRouter comparison
Chosen:  Document the fork (.ai/STRATEGY.md). Treat AInterceptor as a personal
         tool for CareerOS unless a second real user appears.
Impact:  No infra investment until proven needed

## 2026-09-21 — Google OAuth via Tailscale Funnel
Chosen:  Funnel (5-min setup, auto-TLS).
Drift:   Funnel exposes the app publicly. Mitigation: admin password.
Impact:  https://ainterceptor.taila2310c.ts.net is public host

## 2026-09-21 — S3 + S4 — page rebuild (one page = one file)

Chosen:  Sessions and devices pages moved to their own modules
         (sessions_ui.py, devices_ui.py). No more in-place patching of
         large HTML-heavy functions in dashboard_routes.py.
Why:     First S3 attempt broke Python syntax (nested f-string quotes).
         Treating each dashboard page as a standalone module removes the
         risk entirely. Each file < 200 lines, easy to rewrite whole.
Impact:  backend/app/api/sessions_ui.py, devices_ui.py; dashboard_routes.py
         now only handles overview + keys.

## 2026-09-21 — S2 — agents page runs commands live (localhost helper)

Chosen:  Agent exposes http://127.0.0.1:45231 with CORS locked to
         AInterceptor origins. Agents page detects it; Login buttons
         spawn `airouter-agent login <p>` on the user's laptop.
Why:     Browsers cannot run local commands. A localhost helper is the
         pattern used by Docker Desktop / Tailscale / 1Password.
Impact:  agent/airouter_agent/serve.py, /dashboard/agents, nav.

## 2026-09-21 — UI build S1-S3 before CareerOS integration
Chosen:  Build the agent page + sessions enhancement first.
Why:     User judged the agent page as the centerpiece of onboarding.
Impact:  CareerOS integration deferred to next session.
