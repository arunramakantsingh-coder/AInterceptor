# ROADMAP.md — AInterceptor

## Current Status

Phase: 1 — API product + agent
Status: IN PROGRESS (documentation complete, implementation next)
Branch: fix/nonclaude-three-providers-20260917
Next Gate: Docker + API + agent build

## Phase Overview

| Phase | Name | Status |
|---|---|---|
| 0 | Framework bootstrap | COMPLETE (v0.1.0) |
| 1 | API product + agent | IN PROGRESS |
| 2 | Multi-provider E2E (DeepSeek, Claude, Gemini) | PENDING |
| 3 | Orchestrator (capability, fallback, load balance) | PENDING |
| 4 | Webapp (chat + comparison) | PENDING |
| 5 | Billing, quotas, teams | PENDING |
| 6 | Policy-based routing, cost optimization | PENDING |
| 7 | Public launch, multi-tenant scale | PENDING |

## Phase 1 — API Product + Agent

Goal: an OpenRouter-compatible API endpoint, working end-to-end with
ChatGPT, with an agent that lets a user upload a session once.

Deliverables:
- docker/ + docker-compose.yml (Postgres + API)
- backend/app/api/ (auth, keys, sessions, chat endpoints)
- backend/app/db/ (SQLAlchemy models + Alembic)
- backend/app/crypto/ (HKDF + AES-GCM for session blobs)
- backend/app/runtime/ (Path A/B dispatcher)
- agent/ (airouter-agent login <provider>)
- /v1/chat/completions endpoint
- /api/auth, /api/keys, /api/sessions endpoints

Acceptance Criteria:
- docker compose up starts cleanly
- signup + login + API key generation works
- agent login chatgpt uploads a session
- POST /v1/chat/completions with a key returns ChatGPT reply, streamed
- Session persists across container restart
- No browser window ever appears on server

## Phase 2 — Multi-Provider E2E

Goal: DeepSeek, Claude, Gemini work through the same API.

Deliverables:
- DeepSeek working via Path A (direct HTTPS)
- Claude working via Path A
- Gemini working via Path A
- Per-provider parser tests
- Per-provider E2E tests (opt-in)

## Phase 3 — Orchestrator

Goal: capability routing, fallback, load balancing.

Deliverables:
- Orchestrator engine (capability registry, selection algorithm)
- Fallback chain execution
- Rate-limit tracking + cooldown
- Quota enforcement
- Selection observability events

## Phase 4 — Webapp

Goal: end-user chat UI, multi-AI comparison.

Deliverables:
- Login/signup flow
- Provider list, connect buttons
- Chat UI per provider
- Fan-out comparison view
- Session management UI
- API key management UI

## Phase 5 — Billing

Goal: usage tracking, quotas, tiers.

Deliverables:
- usage_events storage
- Tier definitions (free, pro, enterprise)
- Quota enforcement
- Usage dashboard
- Stripe integration (optional)

## Phase 6 — Policy-Based Routing

Goal: cost optimization, admin-tunable routing.

Deliverables:
- Policy DSL
- Cost model refinement
- Per-user policy overrides
- Admin routing dashboard

## Phase 7 — Scale

Goal: multi-tenant at scale.

Deliverables:
- Chromium context pool
- Horizontal scaling
- Kubernetes manifests
- Health/autoscaling
- Observability stack

## Phase 1 Gate

| Gate | Status |
|---|---|
| Implementation | PENDING |
| Local Validation | PENDING |
| Security Review | PENDING |
| Git Diff Review | PENDING |
| Commit | PENDING |
| Push | PENDING |
| Remote Verify | PENDING |
| Documentation | UPDATED |
| Milestone | IN PROGRESS |

## Phase 1 — API Product + Agent — COMPLETE (2026-09-18)

- Docker Compose stack (api + postgres) running
- Auth: signup, login, JWT
- API keys: generate, list, revoke
- Sessions: encrypted upload (HKDF + AES-GCM), list, delete
- OpenAI-compatible POST /v1/chat/completions with SSE stream + [DONE]
- Agent: airouter-agent login <provider> using real Chrome, uploads storage_state
- Verified end-to-end: signup → API key → agent upload → curl chat

Next: Phase 2 — DeepSeek/Claude/Gemini real streaming (Path A/B).
