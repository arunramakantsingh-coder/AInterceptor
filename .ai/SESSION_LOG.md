# AInterceptor — Session Log

Durable record of decisions, drifts, and options considered.
Not a chat transcript — a summary. One entry per meaningful decision.

## Format

  Title    — short name
  Context  — why this came up
  Options  — what was on the table
  Chosen   — what we picked
  Why      — one sentence
  Drift    — what changed vs. earlier plan, or "none"
  Impact   — files / phases / docs affected

Newest first. Append via `asession` command once built. Manual edits ok.

---

## 2026-09-21 — Path A primary, Path B fallback

  Context: Needed a scalable routing story. Path B (VM Chrome) works for one
           user; Path A (HTTP) scales.
  Options: (a) Path B primary, (b) Path A primary + B fallback, (c) both always
  Chosen:  (b)
  Why:     B costs a browser per user; A uses harvested cookies over HTTP.
  Drift:   Original handoff treated A and B as equals. A is now canonical.
  Impact:  dispatcher, runtime priority, /v1 design

---

## 2026-09-21 — VNC admin-only, agent is the product

  Context: VNC-browser login works but one Chrome = one user.
  Options: (a) scale VNC to all users, (b) VNC admin, agent for users
  Chosen:  (b)
  Why:     One Chrome per VM cannot multi-tenant.
  Drift:   VNC page was originally pitched as user-facing. Scoped to admin.
  Impact:  /login/<provider> stays; user onboarding via agent

---

## 2026-09-21 — noVNC embedded (not VNC client, not extension)

  Context: How does a user log in without installing anything?
  Options: (a) ship a VNC client, (b) noVNC page, (c) browser extension
  Chosen:  (b)
  Why:     HttpOnly cookies rule out (c); hard install rules out (a).
  Drift:   none
  Impact:  /login/<provider>, x11vnc bound to 127.0.0.1

---

## 2026-09-21 — OpenRouter comparison; AInterceptor is not a router company

  Context: "How does OpenRouter scale?"
  Chosen:  Document the fork (.ai/STRATEGY.md). Treat AInterceptor as a
           personal tool for CareerOS unless a second real user appears.
  Drift:   none
  Impact:  No infra investment until proven needed

---

## 2026-09-21 — Google OAuth via Tailscale Funnel

  Context: Google rejects plain-HTTP redirect URIs.
  Options: (a) skip Google, (b) Funnel, (c) real cert + reverse proxy
  Chosen:  (b)
  Why:     5-minute setup, auto-TLS, works today.
  Drift:   Funnel exposes the app publicly. Mitigation: admin password.
  Impact:  https://ainterceptor.taila2310c.ts.net is public host
