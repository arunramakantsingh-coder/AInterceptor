# AInterceptor — Web UI Design

Status: proposal. Awaiting green-light before build.

## Page tree

Public:
    /auth/login           email+password, Google button
    /auth/signup          same
    /login                VNC admin landing
    /login/<provider>     VNC per-provider (admin)

User dashboard (cookie auth):
    /dashboard            overview — cards, recent activity, quick start
    /dashboard/keys       API keys (existing)
    /dashboard/sessions   sessions (enhanced — see below)
    /dashboard/devices    devices + connect (merged)
    /dashboard/agents     NEW — the agent page (commands, per-provider login)
    /dashboard/providers  NEW — 20-provider catalog with per-user status
    /dashboard/usage      NEW — /v1 call history
    /dashboard/settings   NEW — account, password, delete

Admin (email == AINTERCEPTOR_ADMIN_EMAIL):
    /dashboard/admin/overview
    /dashboard/admin/sessions
    /dashboard/admin/devices
    /dashboard/admin/logs

Future:
    /dashboard/routing    (needs routing engine)
    /dashboard/billing    (needs revenue model)
    /dashboard/docs       (in-product docs)

## Enhanced pages

### /dashboard/sessions
  Columns: provider | alias | status | source | device | cookies | idb | created | last used
  Actions: refresh | delete | export
  Bulk:  delete expired, refresh all

### /dashboard/devices
  Inline rename, revoke, "Connect a new device" moves HERE (from /connect)

### /dashboard/agents  (NEW — the ask)
  Top: detected devices (name, OS, last seen, status)
  Per device:
    Install (per OS, copy-button)
    Connect (inline code generator, copy-button)
    Login commands per provider — ChatGPT / Claude / DeepSeek / Gemini
    Each with status: "uploaded 2m ago" vs "not logged in yet"
  Bottom: link to docs/AGENT_INSTALL.md

### /dashboard/providers  (NEW)
  All 20 providers with per-user status.
  Admin: enable/disable globally.
  User: enable/disable affects their own routing only.

### /dashboard/usage  (NEW)
  /v1 call history table + light charts (calls/day, latency p50/p95).
  Filters: date, provider, model, status. Read-only.

### /dashboard/settings  (NEW)
  email, name, change password, linked providers, delete account.

## Shared chrome

  Top bar:  [AInterceptor] Dashboard   email  Sign out
  Nav bar:  Overview | API keys | Sessions | Devices | Agents | Providers | Usage | Settings
  Admin:    separate section

Same dark theme. No new dependencies (no React, no build step).
Server-rendered HTML + tiny inline JS.

## Build order (each = one script)

  S1  Nav tree refactor — merge connect into devices, add Agents link
  S2  /dashboard/agents
  S3  /dashboard/sessions enhancement
  S4  /dashboard/providers
  S5  /dashboard/usage
  S6  /dashboard/settings
  S7  /dashboard/admin/*
