# .ai/CURRENT_TASK.md

## Current Milestone
**M2.0 — AIRouter NOS Control-Plane Foundation**

## Status
M1 provider-runtime boundary work remains the foundation. M2.0 now establishes the Cisco-like AIRouter command/mode architecture without moving provider transport or session ownership into the CLI.

## Goal
Turn the existing AInterceptor CLI prototype into a real AIRouter NOS control plane:

1. require explicit `airouter` initialization;
2. expose user EXEC, privileged EXEC and configuration modes;
3. provide Cisco-style prompts, `?` help and explicit Tab completion;
4. establish AI provider metadata and lifecycle configuration commands;
5. establish shared model, routing, session, usage and credit control-plane views;
6. keep provider transport/session mechanics behind the Interceptor boundary;
7. retain persistent provider chat as a runtime-backed operation rather than a CLI scraping mechanism.

## M2.0 Implemented
- Added `cli/nos.py` for NOS mode/state, provider metadata, real local system information and self-test reporting.
- Replaced the prototype shell with AIRouter NOS modes:
  - `AIRouter>` user EXEC
  - `AIRouter#` privileged EXEC
  - `AIRouter(config)#` global configuration
  - `AIRouter(config-ai)#` AI subsystem configuration
  - `AIRouter(config-ai-provider-<name>)#` provider configuration
- Added explicit `airouter` bootstrap and NOS banner.
- Added `show version`, `show system`, `show ai`, `show providers`, `show models`, `show routes`, `show sessions`, `show counters`, and `show credits` control-plane views.
- Added provider configuration commands for enable/disable/login/logout/session/model/health, with runtime ownership preserved.
- Added ChatGPT, Claude, Gemini and DeepSeek to the initial provider registry. Only Claude has an implemented runtime at this milestone.
- Added model-registry and routing-table placeholders so future orchestration has stable CLI surfaces without inventing provider model availability.
- Kept completion explicit (`complete_while_typing=False`) and chat input free of command autocomplete.
- Updated CLI tests for the new mode hierarchy.

## Architecture Boundary
The existing M1 architecture remains authoritative:

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

Implement the provider/service lifecycle, model registry contracts, health state, session state, request accounting, and routing decision interfaces. Claude remains the reference runtime. Do not duplicate those mechanics in the CLI.

## Validation
- Pull the feature branch locally.
- Run the existing CLI/unit test suite.
- Start `python -m cli.main` and verify:
  - `airouter`
  - `enable`
  - `configure terminal`
  - `ai`
  - `provider claude`
  - `show ...`
  - `chat claude`
- Do not merge to `main`.
- Do not rebuild/reset/destroy database or migrations.
- Do not force-push or rewrite history.
