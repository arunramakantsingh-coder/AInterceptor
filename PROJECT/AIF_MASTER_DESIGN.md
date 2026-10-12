# AIF — Master Design

Status: Living document. Update in place. Never recreate from scratch.
Last updated: 2026-10-03

## 1. What AIF is

AIF = AI Intelligence Fabric.
Applications request intelligence, not models. AIF resolves the request
into a policy-compliant execution path against a set of AI providers.

## 2. Naming

  AIF = AI Intelligence Fabric (the product)
  AIN = AI Execution Runtime (this repo: AInterceptor)
  AIR = Decision / Routing Engine
  AIO = Intelligence Orchestration
  AIM = MCP Server (capability interface for AI agents)
  AIP = AI Provider (ChatGPT, Claude, Gemini, DeepSeek, ...)

AIF is the product. AIN/AIR/AIO/AIM are internal subsystems.

## 3. Vertical modules

| Module | Role | Ships today? |
|---|---|---|
| AIN  | Execution runtime: Chrome, CDP, sessions, providers | YES |
| AIR  | Routing & eligibility | folded into AIN |
| AIO  | Orchestration: intent, capability, policy | folded into AIN |
| AIM  | MCP server | NOT YET |
| CLI  | Admin console (interactive + one-shot) | YES |
| Web  | Admin dashboard | YES |
| Platform | Auth, tenancy, metering, billing | partial |

Rules:
  - modules communicate over HTTP only
  - no cross-imports between engine and frontends
  - the CLI is a client of AIN, not part of it

## 4. What AIN owns

  - Chrome lifecycle, Xvfb, CDP
  - Per-provider transport (one file per provider)
  - Session storage & retrieval
  - Network-level response capture
  - Response normalization to StreamEvent
  - Public:  POST /v1/chat/completions (OpenAI-shaped)
  - Internal: POST /internal/dispatch (loopback, no auth)
  - Health:  GET /health, GET /v1/models

## 5. What CLI owns

  - Interactive REPL for chat + ops
  - One-shot commands (see CLI_COMMAND_SURFACE.md)
  - Live monitors and diagnostics
  - Talks to AIN over http://127.0.0.1:8000/internal/*
  - Never imports AIN modules
  - Never launches its own Chrome
  - Never knows provider details

## 6. What Web Dashboard owns

  - Same responsibilities as CLI, browser-delivered
  - Session listing, key management, provider status, usage view
  - Docs rendering (/dashboard/docs)
  - Talks to AIN over HTTPS /dashboard/*, /v1/*, /admin/*

## 7. Deferred (do not build yet)

  - AIM (MCP server)                 - until /v1 is stable and MCP is needed
  - Real AIR / AIO code              - until a second AIN node exists
  - Billing / credits / payment      - until a real second consumer
  - Multi-node AIF                   - until single node is bulletproof
  - A2A                              - future
  - User AI Workspace (Model 2)      - design-only; see section 11

## 8. Provider execution model

Every provider = one file. Each file declares:

  name, home_url, login_markers, response_markers,
  composer_selectors, parse(body)->str, pre_send(page), diagnose(page)

Dispatcher: `provider = registry[name]; async for delta in provider.execute(...)`.
No branches, no Path A/B, no fallback chain.

## 9. Session model

  Application Identity   (owned by the business app)
    ↓
  AIF Session            (logical continuity - deferred for V1)
    ↓
  AIF Request            (id: aifreq_...)
    ↓
  Execution              (id: aifexec_...)
    ↓
  Provider Account       (which AIF-owned account)
    ↓
  AIN Session            (browser context, tabs, cookies)
    ↓
  AIP Conversation       (the provider's own chat thread)

V1: implement AIN Session + AIP Conversation only.

## 10. Rules (locked)

  R-Provider-Isolation          one file per provider
  R-Performance-Priority        fastest response is priority 1
  R-Module-Split                AIN / CLI / Web talk HTTP only
  R-Surgical-Evolution          evolve, do not rewrite
  R-Simplify-Before-Extend      new features shrink the hot path
  R-Diagnose-Becomes-Command    diagnostics become commands
  R-Provider-Account-Registry   accounts are AIF-owned
  R-Docs-Are-Living             amend, never recreate

See `.ai/rules/*.md`.

## 11. Model 1 vs Model 2

Model 1 - Application Intelligence (IN scope)
  Business app → AIF → AIF-owned provider account → AIP
  User never sees a provider, never logs into AIF.

Model 2 - User AI Workspace (DEFERRED)
  User → portal → AIF → user-linked provider accounts → AIP
  Multi-AI chat, comparison. Not implemented.

## 12. Provider Account Registry, Vault, Session Manager

Three-layer subsystem. Owns every AIF provider account.

  Registry      (Postgres)     account_id, provider, region, status,
                               capacity, quota, health, expiry
  Vault         (AES-GCM)      cookies, localStorage, IndexedDB, tokens
  SessionManager (AIN)         health loop, rotation, re-auth queue

Bulk provisioning: parallel Playwright workers, Google OAuth.
Monitoring: light every 15 min, real every 1 h, full on demand.
Routing: sticky → capacity-weighted → relocate if sticky dead.

CLI (planned):
  aaccounts list / status / probe / reauth / provision / export / delete

Deferred until after harness integration. See rule 16.

## 13. Current state (2026-10-03)

  Branch:  fix/cli-chat-provider-gate-cisco-shell
  HEAD:    9d15018
  Snapshot: good-20261003-ain-fast (VBox)
  AIN:     deepseek + gemini CLI work, chatgpt/claude blocked on CF
  Runtime: getResponseBody capture (one-shot, not streaming)
  Next:    docs web view, then command surface, then harness

## 14. Governance

  Git (GitHub)     source of truth
  VM snapshots     safety net, named good-YYYYMMDD-<desc>
  .ai/ docs        design authority
  Chat transcripts context only
