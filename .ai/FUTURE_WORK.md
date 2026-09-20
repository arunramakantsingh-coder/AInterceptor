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
