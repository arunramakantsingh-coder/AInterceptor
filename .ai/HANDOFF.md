# AInterceptor — Session Handoff

Saved: 2026-09-21
Branch: fix/nonclaude-three-providers-20260917
Session type: extended feature + integration build

## What this session accomplished

### Infrastructure (VM)
- Linux daemon stable: Chrome on Xvfb :99, CDP on 9222, 4 tabs
- Cross-platform `_chrome_helpers`, `run-linux.sh` launcher
- `astart`/`arestart`/`astop` with `--fg` mode
- `/health` endpoint returns supervisor/exporter snapshot

### CLI toolkit (19 commands)
- `astatus`, `aprobe`, `atest`, `asessions [--all]`
- `alogin` (agent-first, `--vnc` fallback), `alogout`, `ashow`, `ahide`
- `astart`, `arestart`, `astop`
- `aconfig [show/list/get/set]`, `aconfig-reset`
- `akeys [list/create/current/revoke]`
- `aproviders [list/enable/disable/info/test/status/validate/add/remove]`
- `ahealth`, `aversion`, `alogs`, `aevidence`
- `abootstrap`, `asave`
- `asession`, `aprogress`, `sync_docs` (automation)
- Chat: `chatgpt`, `claude`, `deepseek`, `gemini`

### Web dashboard (all pages)
- `/auth/login`, `/auth/signup`, Google OAuth
- `/login` (VNC admin), `/login/<provider>`
- `/dashboard` (overview, cards)
- `/dashboard/agents` (one-click provider login via local helper)
- `/dashboard/sessions` (kill/refresh/last-used)
- `/dashboard/devices` (inline connect-code generator)
- `/dashboard/providers` (20-provider catalog, admin toggle)
- `/dashboard/usage` (call history + summary cards)
- `/dashboard/keys` (create/list/revoke)
- `/dashboard/settings` (account, password, danger zone)

### Public HTTPS
- Tailscale Funnel: https://ainterceptor.taila2310c.ts.net
- Google OAuth working (client ID configured)
- Admin password gate on VNC pages

### Multi-user
- User accounts (email+password, Google OAuth)
- API keys per user (`sk-aint-*`)
- Device tokens per user (`sk-dev-*`)
- Sessions in DB keyed by user_id
- Admin-only CDP-inject (Phase F)
- Per-user data isolation

### Agent (user-side)
- `airouter-agent connect` (device code exchange)
- `airouter-agent login <provider>` (real Chrome + upload)
- `airouter-agent serve` (local helper on 127.0.0.1:45231)
- `airouter-agent status` (config + server reachability)
- Web UI detects local agent, runs logins with one click

### API
- `/v1/chat/completions` — OpenAI-compatible
- `stream=true` → SSE
- `stream=false` → JSON
- Auth: `sk-aint-*` API keys
- Path A (HTTP, no VM browser) — verified with PONG from deepseek

### Automation
- `asession` — append decision to `.ai/SESSION_LOG.md`
- `aprogress` — regenerate `.ai/PROGRESS.md` from git log
- `sync_docs` — parse commit tags, update docs
- Post-commit hook — auto-syncs docs on every commit

## Architecture decisions (see .ai/SESSION_LOG.md for full log)

- Path A primary (HTTP, scales), Path B fallback (browser, admin-only)
- VNC login is admin-only; agent is the product for users
- Agent exposes localhost helper for web UI
- Google OAuth via Tailscale Funnel (HTTPS required)
- Admin-only CDP-inject (regular users' sessions stay in DB)

## Verified working

- 3/4 providers chat via CLI: chatgpt, claude, deepseek
- 4 provider sessions in DB for arunramakantsingh@gmail.com
- Google login → dashboard → API keys → copy → use key
- `/v1/chat/completions` returns PONG for deepseek
- Agent device flow works on Windows (DESKTOP-9S3SKGC)
- Agent local helper works (port 45231)

## Known issues

- B002: Gemini blocked at Google account level (needs different account)
- Perplexity: listed but no runtime file
- Character: runtime file exists but not registered
- ChatGPT: no Path A HTTP path (PoW required) — CLI-only
- Leaked key `sk-aint-68mCn67GPMNaxoCqt9NO09w7HAr63hUDGGk41tUS` — rotate via dashboard

## CareerOS integration — in progress

Target: `C:\Projects\v0.2-global-job-intelligence`, branch `feature/intelligence-provider-gateway-20260912`.

Done:
- `backend/app/intelligence/provider_catalog.py` patched: added `ainterceptor` entry
- `services/intelligence/providers.py` patched: added `ainterceptor` defaults
- `.env` has `AI_PROVIDER=ainterceptor`, `AINTERCEPTOR_BASE_URL`, `AINTERCEPTOR_API_KEY`, `AINTERCEPTOR_MODEL`
- Backend restarts cleanly, routing engine recognizes the provider

Blocker:
- Provider registry cards (9 tiles at /project-control/intelligence) — hardcoded list missing `ainterceptor` as 10th card

Next:
- Find and patch the frontend/backend provider card list
- Test end-to-end: CareerOS → AInterceptor /v1 → deepseek → reply

## Next session priorities

1. Fix CareerOS frontend provider registry cards
2. End-to-end CareerOS test with a real AI flow
3. Rotate the leaked API key
4. (Optional) `/dashboard/admin/*` all-user views
5. (Optional) Cisco-style interactive CLI shell

## Reference docs

- `.ai/RULES.md` — project rules (R1-R7)
- `.ai/SESSION_LOG.md` — decision log
- `.ai/PROGRESS.md` — milestone progress
- `.ai/FUTURE_WORK.md` — parking lot
- `.ai/STRATEGY.md` — OpenRouter comparison, scaling
- `PROJECT/AUTOMATION.md`, `PROJECT/WEB_UI.md`, `PROJECT/ARCHITECTURE_VNC_LOGIN.md`, `PROJECT/ARCHITECTURE_ACCOUNTS.md`
- `docs/COMMANDS.md`, `docs/AGENT_INSTALL.md`

## How to resume

1. On VM: `astatus`, `aprobe`, `asessions --all`
2. Check CareerOS branch: `cd C:\\Projects\\v0.2-global-job-intelligence && git log --oneline -5`
3. Read `.ai/PROGRESS.md` and `.ai/SESSION_LOG.md`
4. Pick a next-session priority above
