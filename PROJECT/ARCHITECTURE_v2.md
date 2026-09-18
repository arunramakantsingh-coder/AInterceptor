# AInterceptor - Architecture v2

Status: DRAFT - awaiting owner approval
Date: 2026-09-19
Supersedes: ARCHITECTURE_LLD.md v1.0
Scope: Product 2 (API for external apps like CareerOS). Single user. Windows dev.

## 1. Locked Decisions

| ID  | Decision |
|-----|----------|
| D1c | Submit: try page.evaluate(fetch) first, fall back to composer click |
| D2a | Reply capture: CDP network (Layer 6), never DOM |
| D3b | Stealth: Patchright (Playwright fork, patches CDP leaks) |
| D4a | Daemon: build now (fixes popups + repeated login) |
| D5b | Health: per-provider x per-path circuit breaker + background probes |
| D6b | Session: persistent Chrome profile + periodic storageState JSON export |

## 2. System Overview

    CLI / CareerOS / webapp
              | HTTP
              v
    AInterceptor daemon (persistent)
      FastAPI :8000
        /v1/chat/completions
        /api/auth /api/keys /api/sessions
        /health
      Orchestrator
        provider selection
        circuit breaker per path
        fallback chains
      Interceptor (dispatcher)
        Path A (direct HTTP)
        Path B (browser + CDP)
      Browser Supervisor
        Patchright
        1 Chrome, N tabs
        off-screen forever
        PID watchdog
      Postgres :5432 (Docker sidecar)

## 3. Daemon Lifecycle

START (run-windows.ps1)
  1. Load env, verify Postgres
  2. Launch Patchright Chrome (persistent profile, off-screen)
  3. Open one tab per configured provider
  4. For each tab: restore session from storageState JSON
  5. Start uvicorn (FastAPI) on 127.0.0.1:8000
  6. Start background threads:
       Chrome PID watchdog (10s)
       Off-screen watchdog (3s)
       Health prober (60s)
       Session exporter (5min)
  7. Serve requests

The daemon never exits unless you stop it.

## 4. Unified Execution Pipeline

For every provider: request -> pick tab -> submit -> capture -> parse -> return

### 4.1 Submit (D1c)

    Try page.evaluate(fetch(internal_endpoint, body))
       2xx -> wait for SSE chunks
       error -> fall through
    Fall back to composer:
       find composer (provider-specific selectors)
       type prompt, press Enter
       wait for SSE chunks

### 4.2 Capture (D2a)

Before submission, attach CDP Network.dataReceived listener:

    CDP session on tab
      Network.enable with maxTotalBufferSize=0 (disable buffering)
      Network.setBypassServiceWorker(bypass=true)
      on dataReceived -> route bytes to parser queue
      on loadingFinished -> close stream

Never read the DOM for the reply. DOM is only for finding the composer.

### 4.3 Parse

Each provider has one parser module. It receives raw SSE/WS bytes and
yields StreamEvents. The parser is the ONLY provider-specific code.

## 5. Browser Supervisor (D3b, D4a)

- Engine: Patchright (Playwright fork, patches CDP fingerprints)
- Chrome: one process, persistent --user-data-dir profile
- Tabs: one per provider, kept alive across requests
- Position: --window-position=-32000,-32000
- PID watchdog: if Chrome dies, relaunch + restore from JSON
- Off-screen watchdog: every 3s, push any Chrome window back
- Human behavior: Patchright adds realistic timing by default

## 6. Session Persistence (D6b)

Two layers:

| Layer | Mechanism                     | Survives Chrome upgrade | Speed         |
|-------|-------------------------------|-------------------------|---------------|
| Hot   | Persistent --user-data-dir    | No                      | Instant       |
| Cold  | storageState JSON every 5min  | Yes                     | 2-3s restore  |

On login: save JSON immediately + update profile.
On startup: load profile if valid; else restore from latest JSON.

## 7. Health / Circuit Breakers (D5b)

Per provider x path, track:

    state in { CLOSED, OPEN, HALF_OPEN }
    failures, successes in sliding 60s window
    last state change
    next probe time

### 7.1 State transitions

    CLOSED
      failure rate > 50% over 60s window -> OPEN
      normal traffic flows

    OPEN
      all requests short-circuit to fallback
      after backoff -> HALF_OPEN

    HALF_OPEN
      send ONE probe
        success -> CLOSED
        fail -> OPEN with backoff x2 (max 30min)
      no user traffic

### 7.2 Background prober (every 60s)

For each provider, for each path (A, B):
  send lightweight probe (one-char prompt, 5s timeout)
  record latency + success/fail
  update circuit breaker
  emit event if state changed

### 7.3 /health endpoint

Returns daemon health, chrome status, per-provider per-path state.
This is the CLI's 'show health' source of truth.

## 8. CLI Surface (Cisco-style)

    AIRouter# show health
    AIRouter# show providers
    AIRouter# show sessions
    AIRouter# show circuits
    AIRouter# show probes
    AIRouter# debug provider claude on
    AIRouter# chat claude

## 9. Postgres / Session Store

Unchanged from v1.0:
- Tables: users, api_keys, user_sessions, usage_events
- Sessions encrypted: HKDF(master_key, user_id) + AES-GCM
- Agent uploads to /api/sessions/upload

## 10. Login Flows

Flow A (default, Phase 1): user-side agent
    airouter-agent login <provider> -> captures state -> uploads

Flow B (Phase 4): in-container via webapp (noVNC)

## 11. What This Fixes vs Current WIP

| Problem in current WIP           | How v2 fixes it                              |
|----------------------------------|----------------------------------------------|
| Browser pops up during chat      | Daemon launches Chrome once; CLI is HTTP-only |
| Claude fails via generic Path B  | Claude uses own runtime; dispatcher routes    |
| Character loss in replies        | CDP network capture, not DOM read             |
| Repeated login prompts           | Persistent profile + JSON export              |
| No health visibility             | Circuit breakers + /health + show health      |
| Cloudflare blocks on headless    | Patchright patches CDP leaks                  |

## 12. Non-Goals (this iteration)

- Multi-tenant scale
- Webapp UI
- Billing
- Kubernetes
- Linux deployment (Phase 3)

Build Windows dev daemon first. Linux port comes after Phase 1 acceptance.

## 13. Migration from Current WIP

Keep unchanged:
  backend/app/interception/claude.py, claude_transport.py, chrome_auth.py
  backend/app/interception/chatgpt.py, gemini.py, deepseek.py
  backend/app/crypto/, auth.py, deps.py, api/*, db/*
  agent/
  docker-compose.yml (as backup)
  all documentation

Replace:
  backend/app/runtime/path_b.py  -> CDP-capture version
  backend/app/runtime/dispatcher.py -> route Claude to ClaudeRuntime
  run-windows.ps1 -> start daemon

Add:
  backend/app/runtime/daemon.py
  backend/app/runtime/browser_supervisor.py
  backend/app/runtime/circuit_breaker.py
  backend/app/runtime/prober.py
  backend/app/runtime/session_exporter.py
  backend/app/runtime/watchdog.py

Archive:
  old path_b.py -> scripts/archive/

Never touch (host):
  portproxy rules, firewall rules

## 14. Approval Checklist

Before any code is written, owner confirms:

- [ ] Daemon model accepted
- [ ] Patchright accepted
- [ ] CDP network capture accepted
- [ ] Circuit breaker accepted
- [ ] Session JSON export + persistent profile accepted
- [ ] Migration plan accepted

End of Architecture v2 - DRAFT
