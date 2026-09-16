# .ai/CURRENT_TASK.md

## Current Milestone
**M2.0 — AIRouter NOS Control-Plane Foundation**

## Status
M1 provider-runtime boundary work remains the foundation. M2.0 establishes the Cisco-like AIRouter command/mode architecture without moving provider transport or session ownership into the CLI.

## M2.0 Implemented
- AIRouter NOS startup banner, version, hardware/runtime information and self-tests.
- User EXEC, privileged EXEC, global configuration, AI configuration and provider configuration modes.
- Cisco-style explicit Tab completion with `complete_while_typing=False`.
- Cisco-style unique command abbreviations and context-sensitive `?` help:
  - `conf t` / `con t` resolves to `configure terminal`.
  - `sh v` resolves to `show version`.
  - `en` resolves to `enable`.
  - `show v?` lists matching show commands.
  - `configure ?` lists `terminal`.
  - `model ?` lists model candidates.
  - ambiguous prefixes are rejected instead of guessed.
- Added `bootai` console entry point so the installed CLI can be launched directly.
- Added a runtime-neutral model catalog for ChatGPT, Claude, Gemini and DeepSeek. Catalog entries are not claims of web-session access; actual provider web availability is discovered by provider runtimes.
- Added model selection state through the AI configuration CLI.
- Added provider configuration commands for enable/disable/login/logout/session/model/health, with runtime ownership preserved.
- Added show surfaces for providers, models, routes, sessions, usage/counters and credits.

## Provider / Model Catalog Boundary
Provider model metadata is deliberately separated from web-session availability. A catalog entry may be known from the provider's current public model documentation while a particular account/session may not expose that model. Runtime discovery must be authoritative for actual web use.

## Architecture Boundary
```text
AIRouter CLI / Client
        |
        v
Gateway
        |
        v
Orchestrator
        |
        v
Interceptor
        |
        v
Provider Web Runtime
```

The CLI must not implement provider transport, browser scraping, provider-specific session mechanics, or provider inference APIs as the primary integration path.

## Next Milestone
**M2.1 — Provider lifecycle and shared orchestration contracts**

Implement provider/service lifecycle, model registry contracts, health state, session state, request accounting, and routing decision interfaces. Claude remains the reference runtime. Do not duplicate those mechanics in the CLI.

## Validation
1. Pull `feature/m1-provider-runtime-boundary-20260916`.
2. Install editable once for the direct command:
   `python -m pip install -e .`
3. Launch with:
   `bootai`
4. Verify:
   - `airouter`
   - `enable` / `en`
   - `configure terminal` / `conf t` / `con t`
   - `show version` / `show v`
   - `show v?`
   - `ai`
   - `provider claude`
   - `model ?`
   - `show models`
   - `chat claude`
5. Do not merge to `main`.
6. Do not rebuild/reset/destroy database or migrations.
7. Do not force-push or rewrite history.
