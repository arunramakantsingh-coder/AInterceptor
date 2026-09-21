# Future Work

Parking lot. Not committed to a phase.

## CLI / Admin
- `aproviders configure <name>` — edit existing provider's URL/markers (currently must edit 3 files by hand)
- `aroute show/set/fallback` — routing table per capability (needs routing engine)
- `arate show/set/cooldown` — per-provider rate limits (needs rate-limiter)
- `atoken create/list/revoke` — ephemeral bearer tokens for scripts (needs /v1)
- `akeys rotate <id>` — mint replacement with grace period
- `alogs` more sources (uvicorn access, chrome console, patchright)
- `astart --fg` foreground mode — verify behavior on Linux VM

## API
- `POST /v1/chat/completions` — OpenAI-compatible endpoint for CareerOS and external apps
- `GET /v1/models` — list providers as models
- Bearer auth via `sk-aint-*` keys

## Providers
- Add runtime files for: perplexity, and any of the 20 that are registered but incomplete
- Register orphaned `character` runtime
- Add agent-side login support for more than 4 providers
- Auto-detect session expiry and re-trigger login
- Non-invasive prober (tab title + DOM check, no messages)

## Routing
- Routing engine (Phase 4): fallback chains per capability (reasoning/coding/fast/vision)
- Rate limiter with per-account cooldown
- Load balancing across multiple accounts per provider
- Cost / usage tracking

## Long-term
- Governance dashboard (Phase 6) — GitHub-integrated, commit + roadmap + bug tracker
- Multi-tenant session storage
- Windows-native install path (currently Linux VM only)

## Agent E2E test (deferred)
Run `airouter-agent login claude` from a Windows laptop against the VM.
Proves the full user-side flow end-to-end. Deferred but highest-value
validation remaining.


## Tailscale publishing (future)

- Phase 2: MagicDNS hostname (tailnet-only, e.g. `http://ainterceptor:8000`)
- Phase 3: Tailscale Funnel (public HTTPS at `<tailnet>.ts.net`) +
  hardened auth for external users
- See `PROJECT/ARCHITECTURE_VNC_LOGIN.md` for the full plan


## CLI UX — Cisco IOS/Nexus-style interactive shell

Currently each `a*` command is a standalone script. Users asked for a
unified interactive shell with:

- `?` context help at any position
  (e.g. `aproviders ?` → lists subcommands; `aproviders enable ?` → lists providers)
- Tab completion for subcommands, provider names, config keys
- Command history (up-arrow) persisted to `.ainterceptor/cli_history`
- Context prompts like `AIRouter(config-ai-provider-claude)#`
- Inline `[OK]` / `[FAIL]` / next-step hints (already the convention)

Reference: Cisco IOS / Cisco Nexus CLI conventions.

This supersedes the per-command `--help` flags long-term, but does not
break them. Implementation candidates: Python `prompt_toolkit` or `cmd` module.

Parked until core functionality (login page, /v1 API) is stable.

## Scaling to thousands of users (not this week)

The VNC `/login/<provider>` page is an admin tool for 1-5 users. It does
NOT scale to thousands because:

  - One Chrome, one profile, one set of cookies per VM
  - One Xvfb desktop
  - One FastAPI process proxying WS bytes

The path to thousands of users is the agent-based flow:

  user's own browser  ->  agent captures storage_state
                     ->  POST /api/sessions/upload with API key
                     ->  server stores, routes via Path A (direct HTTP)

Thousands of users = no browsers on the server. Session JSONs + routing.

When Path B (browser-required providers: chatgpt, gemini, poe) needs
to scale, the architecture is:

  LB  ->  N x API servers
            ->  Redis / Postgres  (session + rate-limit state)
            ->  Path A workers  (direct HTTP, no browser)
            ->  Path B worker pool  (headless Chromes per tenant)

Path B pool options: Playwright-on-K8s, Steel.dev, Browserless.io.

See PROJECT/ARCHITECTURE_VNC_LOGIN.md


## Email delivery (deferred)

- SMTP provider (Sendgrid / Mailgun / Postmark)
- Invitation emails, password reset, "device connected" notifications
- Deferred: dashboard-only delivery for phase 1-4


## Admin: all-user session view

Currently each user only sees their own sessions (by design).
For admin diagnostics, add:

  /dashboard/admin/sessions   — list every user's sessions, admin-only
  /dashboard/admin/keys       — list every user's keys, admin-only

Gated by AINTERCEPTOR_ADMIN_EMAIL. Deferred until we have >1 real user.


## Tailscale admin CLI (future)

Wire tailscale operational commands into the admin CLI so they're
part of the same toolkit rather than memorized separately:

  ats status               tailscale status (peers)
  ats ip                   this node's Tailscale IP
  ats funnel on [port]     tailscale funnel --bg <port>
  ats funnel off           tailscale funnel --https=443 off
  ats funnel status        tailscale funnel status
  ats dns                  tailscale dns status

Read-only wrappers around `tailscale` where safe. Write ops
(funnel on/off) still require sudo; wrapper just prints the exact
command if sudo fails.

Parked until core product (/v1) is stable.


## Dashboard: strategy / todo board

In-product task list and strategic review board, so thinking lives in the
product not just in markdown. Suggested views:
  - TODO / WIP / DONE per area (CLI / accounts / providers / infra)
  - "Strategy" section (see .ai/STRATEGY.md for the current one)
  - Link a note to a phase or a commit

Backed by a simple `todos` table (id, user_id nullable, area, title,
body, status, created_at, done_at).

Deferred — product basics first.
