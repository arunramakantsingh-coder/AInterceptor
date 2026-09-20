# User Accounts, Dashboard, and Agent Onboarding

Status: DRAFT — awaiting approval
Author: design pass 2026-09-21
Supersedes: none
Related: PROJECT/ARCHITECTURE_VNC_LOGIN.md

## 1. Goals

- Let **thousands of users** sign up and connect their own AI-provider sessions
- Let users generate and manage **API keys** for their own apps (CareerOS etc.)
- Let users connect a **device (agent)** on their laptop with one click
- Give every user a **dashboard** showing their providers, keys, and devices
- Keep the current VNC login page as an **admin-only** emergency tool

## 2. Non-goals

- VNC login for end users (does not scale — see ARCHITECTURE_VNC_LOGIN.md)
- Minting provider session tokens server-side (impossible — see §3)
- Email delivery (parked — see FUTURE_WORK.md)
- Billing, quotas, teams (later)

## 3. What is technically impossible

AIntercepor cannot create a Claude/ChatGPT/Gemini session for a user.
Provider sessions are `HttpOnly` cookies set only by the provider's own
servers after that user authenticates with them. Only Anthropic, OpenAI,
Google etc. can mint those cookies.

Therefore: the user MUST log into each provider themselves, on their own
machine, via a real browser. Our job is to make that step smooth — not
to eliminate it.

## 4. Identity model

  User            one row in `users` (already exists)
  UserSession     provider cookies captured by a user's agent (already
                  exists, keyed by user_id + provider + alias)
  ApiKey          long-lived bearer token for that user's apps
                  (already exists, keyed by user_id)
  Device          NEW — a user's laptop that has airouter-agent installed

New table: `devices`

    id                uuid pk
    user_id           fk users
    name              user-provided (e.g. "Arun's Windows laptop")
    token_hash        argon2 of a long random device token
    token_prefix      first 16 chars, for lookup
    last_seen_at      timestamp
    created_at        timestamp
    revoked_at        timestamp nullable

New table: `device_codes` (short-lived, for the connect flow)

    code              6-char alphanumeric, e.g. "HK4P-QR7W"
    user_id           who clicked "Connect device"
    device_name       optional, user can fill later
    expires_at        now + 10 minutes
    consumed_at       nullable — set once exchanged
    created_at        timestamp

## 5. Signup and login

Two flows. Both land on the same session cookie.

### 5.1 Email + password

  POST /auth/signup  { email, password, name? }
    - validate email format, password >= 10 chars
    - reject if user exists (no user enumeration beyond that)
    - create user (argon2 hash)
    - set session cookie, redirect /dashboard

  POST /auth/login   { email, password }
    - verify argon2
    - set session cookie, redirect /dashboard

  POST /auth/logout
    - clear cookie

  GET  /auth/login   → HTML login page
  GET  /auth/signup  → HTML signup page

### 5.2 Google OAuth (Phase 5 — requires external setup)

  GET /auth/google           redirect to Google
  GET /auth/google/callback  exchange code, create-or-find user, set cookie

Needs a Google Cloud project with an OAuth 2.0 Client ID. The redirect
URI must be exactly:

  https://<host>/auth/google/callback

### 5.3 Session cookie

Reuse existing JWT infra (`app/auth.py` — `make_jwt`, `read_jwt`).

    name:     aint_session
    httpOnly: true
    secure:   true (once we're behind https; false for plain Tailscale IP)
    sameSite: lax
    path:     /
    ttl:      7 days

## 6. Dashboard

  /dashboard              overview: providers, keys, devices, quick actions
  /dashboard/keys         list, create, revoke API keys
  /dashboard/sessions     list uploaded provider sessions (masked)
  /dashboard/devices      list connected devices, revoke
  /dashboard/connect      "Connect a new device" — see §7
  /dashboard/account      change password, email (later)
  /dashboard/admin/*      admin-only (existing VNC login lives here)

All routes require the `aint_session` cookie. Unauthenticated → redirect
to `/auth/login?next=<original>`.

## 7. Agent onboarding (device code flow — primary)

Why device code: the user has an agent on laptop A but is logged into
the dashboard on browser B. The two need to meet. Device codes are the
proven pattern (gh, gcloud, tailscale).

Flow:

  1. User on dashboard clicks "Connect a device"
  2. Server generates a code: "HK4P-QR7W" (10 min TTL, one-use)
  3. Dashboard shows:
       [ HK4P-QR7W ]  [copy]
       Run on your laptop:
         airouter-agent connect --server https://<host> --code HK4P-QR7W
  4. User opens terminal, runs the command
  5. Agent:
       - POST /api/devices/exchange  { code, device_name, os }
       - server verifies, marks code consumed, creates Device row,
         returns a long-lived device token (sk-dev-<40 chars>)
       - agent saves it in ~/.airouter/config.json
  6. Dashboard polls /dashboard/connect/status every 2s; when consumed,
     shows "Device connected ✓ — you can close this page"
  7. From then on, the agent's `login <provider>` uses the device token

### 7.1 Optional — localhost handshake (nice-to-have, later)

If we want to skip copy/paste of the code, the agent can advertise a
port on localhost. The dashboard then POSTs the token directly.

    agent listens on http://127.0.0.1:45231/connect
    dashboard page POSTs { token, server } to that URL (with CORS
    restricted to the dashboard origin)
    agent saves token, responds 200

Pros: no code to copy. Cons: agent must already be running, port
discovery needs a fallback, CORS is fiddly. Ship device-code first.

## 8. API keys (unchanged conceptually)

Same as today, but now per-user (already true — `ApiKey.user_id`).

    POST /api/keys  { name }  →  { id, key: "sk-aint-...", prefix, name }
    GET  /api/keys
    DELETE /api/keys/{id}

The dashboard adds a UI on top of these endpoints. No API change.

## 9. Provider sessions (unchanged conceptually, now multi-user)

    POST /api/sessions/upload   file + provider + alias
      - authenticated by either sk-aint-* (app) or sk-dev-* (agent)
      - stores in user_sessions for the calling user
      - CDP-injects into the *shared VM browser* only for the admin user
        (for regular users, the session is stored and used by Path A —
         no VM browser involvement)

### 9.1 Important scoping note

The CDP-inject path only makes sense for the admin (who owns the VM's
Chrome). For regular users, sessions are used by Path A (direct HTTP
with harvested cookies) — no browser on the server. That's what makes
thousands of users possible.

Implementation: the `_inject_to_live` call inside `/api/sessions/upload`
becomes conditional on `user.id == ADMIN_USER_ID`. For everyone else,
the upload just stores.

## 10. DB schema additions

  + devices
  + device_codes
  ~ users          (add: name nullable, provider nullable for OAuth)
  ~ api_keys       (already user-scoped, no change)
  ~ user_sessions  (already user-scoped, no change)

## 11. Phase plan

  Phase 1  User accounts
           signup/login/logout, session cookie, /dashboard shell
           ~1-2 days

  Phase 2  Dashboard: my API keys
           list/create/revoke via UI
           ~1 day

  Phase 3  Dashboard: my sessions
           list, delete
           ~0.5 day

  Phase 4  Device code flow + agent `connect` subcommand
           ~1 day

  Phase 5  Google OAuth
           ~0.5 day + external setup

  Phase 6  User-scoped session upload (drop CDP-inject for non-admins)
           ~0.5 day

## 12. Security notes

  - Passwords: argon2 (already in app/auth.py)
  - Session cookies: httpOnly, SameSite=Lax, no local-storage
  - Device tokens: sk-dev-<40 random>, argon2 hashed at rest
  - Device codes: 6 chars, single-use, 10-minute TTL
  - API keys: sk-aint-<40 random>, argon2 hashed at rest (existing)
  - Login POST: rate-limited (10 attempts / 15 min / IP — phase 2)
  - CSRF: rely on SameSite=Lax + same-origin POST
  - Email enumeration: signup returns generic "check your email"
    if we add email confirmation later; for now, "account created"

## 13. Open questions

  1. Do we allow a user to have multiple active sessions per provider
     (aliases)? Yes — schema already supports it.
  2. Do we let users share an API key across devices? Yes — keys are
     user-scoped, not device-scoped.
  3. What happens when a user deletes their account? Cascade delete
     user_sessions, api_keys, devices. Confirm with a dialog.
  4. Do we need admin roles? For now: `users.is_admin` boolean,
     only the original admin has it.
  5. Do we expose /dashboard publicly? Later, after Funnel + TLS.

## 14. What stays the same

  - Admin VNC login page (unchanged, still admin-only)
  - Admin CLI commands (a* family)
  - Agent binary (gains a `connect` subcommand)
  - /v1/chat/completions (when built, uses sk-aint-* only)
  - Session storage format (storage_state JSON, encrypted at rest)
