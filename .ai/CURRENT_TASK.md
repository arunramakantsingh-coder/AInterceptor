# .ai/CURRENT_TASK.md

## Current Milestone
**M2.1 — Provider Lifecycle / Web Runtime Expansion**

## Status
M2.0 established the AIRouter NOS control-plane foundation. M2.1 now extends the existing Interceptor boundary to ChatGPT Web, Gemini Web and DeepSeek Web while keeping provider transport/session mechanics outside the CLI.

## M2.1 Implemented
- Added a shared `BrowserWebRuntime` boundary for browser-backed providers.
- Browser automation is limited to provider session establishment, authentication recovery and prompt submission.
- Provider response extraction remains transport-level network interception; rendered provider DOM is not used as the response source.
- Added `ChatGPTRuntime` with ChatGPT Web transport matching and SSE/backend response normalization.
- Added `GeminiRuntime` with Gemini Web `StreamGenerate` transport matching and tolerant framed-response normalization.
- Added `DeepSeekRuntime` with DeepSeek Web completion transport matching and SSE normalization.
- Added interactive `login` workflow for the three new provider runtimes using isolated local browser profiles and persisted Playwright storage state.
- Wired CLI `chat <provider>` through the shared runtime registry instead of hard-coding Claude.
- Added `show run` / `show running-config` rendering of the current AIRouter control-plane configuration.
- Added regression tests for `show run` and provider runtime imports.
- Added `.ainterceptor/` to `.gitignore` because it contains local CLI history and provider browser/session state.

## Important Runtime Boundary
The provider runtimes are deliberately thin and provider-specific. The Orchestrator must not depend on URL formats, SSE schemas, browser selectors, cookies, tokens, or provider-specific session details. Those belong below the Interceptor runtime boundary.

The new web runtimes use transport observations rather than DOM answer extraction. Their network contracts are private web-interface contracts and may drift; live account validation is therefore required before marking a provider `READY`.

## Cisco-style Running Configuration
`show run` is a first-class operational command. It must eventually represent the complete effective AIRouter configuration, including:
- provider enable/disable policy;
- selected model policy;
- routing/service-group policy;
- prompt profiles;
- session policy;
- API clients;
- security policy;
- future MOTD/banner configuration.

Secrets, cookies, browser storage and private credentials must never be rendered into `show run`.

## Next Work
1. Live-validate ChatGPT, Gemini and DeepSeek login/session recovery on the user's machine.
2. Fix provider-specific transport drift discovered by those tests rather than weakening the transport boundary.
3. Implement shared provider lifecycle/health/session/accounting contracts in the Orchestrator.
4. Connect runtime-discovered model availability to the model registry; catalog metadata must never be treated as account access.
5. Add provider counters, usage/credit semantics and route decisions.
6. Expand `show run` into a complete IOS-style effective configuration renderer.

## Validation
1. Pull `feature/m1-provider-runtime-boundary-20260916`.
2. Install editable once:
   `python -m pip install -e .`
3. Launch:
   `bootai`
4. Verify NOS commands:
   - `airouter`
   - `en`
   - `conf t`
   - `show run`
   - `show v?`
   - `ai`
   - `model ?`
5. For each provider:
   - `provider chatgpt` / `provider gemini` / `provider deepseek`
   - `login`
   - `session`
   - `chat <provider>`
6. Do not merge to `main`.
7. Do not rebuild/reset/destroy database or migrations.
8. Do not force-push or rewrite history.
