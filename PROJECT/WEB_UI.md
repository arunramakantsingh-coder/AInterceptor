# AInterceptor — Web UI Design

Status: proposal. Awaiting approval before build.

## Page tree

Public (no auth):

    /auth/login        email+password, Google button
    /auth/signup       same
    /login             VNC admin landing (existing)
    /login/<provider>  VNC provider page (existing)

User dashboard (cookie auth):

    /dashboard              overview — cards, recent activity, quick start
    /dashboard/keys         API keys (existing)
    /dashboard/sessions     sessions — enhance (see below)
    /dashboard/devices      devices — merge connect here
    /dashboard/agents       NEW: per-device agent commands & provider login
    /dashboard/providers    NEW: catalog, enable/disable, status
    /dashboard/usage        NEW: call history, tokens, provider breakdown
    /dashboard/settings     NEW: account, password, delete account

Admin dashboard (email in AINTERCEPTOR_ADMIN_EMAIL):

    /dashboard/admin/overview    all-users activity
    /dashboard/admin/sessions    all-user sessions (asessions --all view)
    /dashboard/admin/devices     all-user devices
    /dashboard/admin/logs        daemon / chrome / x11vnc tails

Future:

    /dashboard/routing      routing rules per capability (needs engine)
    /dashboard/billing      credits, usage limits (needs revenue model)
    /dashboard/docs         in-product docs viewer

## Page details

### /dashboard (overview)

  Welcome, <name>
  Four cards: API keys | Sessions | Devices | Calls this month
  Recent activity table (last 10 calls / uploads / logins)
  Quick start: 3 steps for a brand-new user

### /dashboard/keys

  (existing) list + create + revoke + PRG-safe one-time reveal
  Add: "regenerate" button per key (new token, same name, old revoked)

### /dashboard/sessions  — enhanced

  Table per row:
    provider  alias  status  created  last used  actions

  Actions per row:
    refresh   → runs `alogin <provider>` or shows agent command
    delete    → confirm, then remove from DB
    export    → download storage_state.json (masked values, or full?)

  Bulk:
    delete all expired (status != active)
    refresh all

  Columns we can add:
    "source"      — uploaded via agent or VNC
    "device"      — which device uploaded it
    "cookies"     — count
    "idb"         — databases captured

### /dashboard/devices

  (existing) plus:
    rename  — inline edit of device name
    revoke  — kill device token
    "Connect a new device" — moves HERE from /dashboard/connect
    Polling page for pending codes lives here too

### /dashboard/agents   — NEW, the ask

  A single place that tells a user EXACTLY what to run on their laptop.

  Top of page:
    Detected devices:  Aruns-Laptop (Windows), last seen 2m ago   [connected]
                       Macbook-Air, last seen 3d ago              [stale]

  Per device, expandable:

    Install (once):
      Windows   pip install airouter-agent
      macOS     pip install airouter-agent
      Linux     pip install airouter-agent
      (copy button per line)

    Connect (once):
      airouter-agent connect --server https://ainterceptor.<tailnet>.ts.net --code XXXX-XXXX
      [Generate device code] — inline, no need to visit /dashboard/devices

    Log into providers (per provider):
      ChatGPT    [Login]  →  airouter-agent login chatgpt
      Claude     [Login]  →  airouter-agent login claude
      DeepSeek   [Login]  →  airouter-agent login deepseek
      Gemini     [Login]  →  airouter-agent login gemini

      For each: shows if a session already exists for this user
      (read from user_sessions), last uploaded, device it came from.

      Copy-command button per provider. No CLI typing.

  Bottom: link to docs/AGENT_INSTALL.md

  What's NOT here: destructive ops (those are on /dashboard/devices)

### /dashboard/providers   — NEW

  Full catalog of 20 providers with state per user:

    PROVIDER      STATUS       SESSION        ACTION
    chatgpt       active       uploaded 2m    [disable] [login]
    claude        active       uploaded 2m    [disable] [login]
    gemini        active       uploaded 3m    [disable] [login]
    deepseek      active       uploaded 5m    [disable] [login]
    mistral       inactive     —              [enable]
    qwen          inactive     —              [enable]
    ...

  For admin users, "enable/disable" toggles the provider globally.
  For regular users, "enable/disable" only affects their own routing.

### /dashboard/usage   — NEW

  Table of /v1 calls:
    TIME  MODEL  TOKENS IN  TOKENS OUT  LATENCY  STATUS

  Filters: date range, provider, model, status
  Charts (lightweight): calls per day, latency p50/p95

  Read-only. No admin actions here.

### /dashboard/settings   — NEW

  Account:
    email (read-only or change-with-verify)
    name
    password (change)
    linked providers (google → link/unlink)
    delete account (danger zone, requires typed confirmation)

## Shared chrome

  Top bar:  [AInterceptor]  [Dashboard]  [email]  [Sign out]
  Nav bar:  Overview | API keys | Sessions | Devices | Agents | Providers | Usage | Settings
  Admin:    a subtle separator + "Admin" dropdown

  Same dark theme as current. No new dependencies (no React, no build
  step) — server-rendered HTML + small JS where necessary. This matches
  the current stack and keeps the daemon lightweight.

## Build order (per script)

  S1  Nav tree refactor — move connect into devices, add agents link
  S2  /dashboard/agents  (the ask)
  S3  /dashboard/sessions enhancements (kill, refresh, source columns)
  S4  /dashboard/providers
  S5  /dashboard/usage  (needs /v1 call logging table — mostly there)
  S6  /dashboard/settings
  S7  /dashboard/admin/* (all-user views)

Each script keeps existing pages working. No URL breaks.
