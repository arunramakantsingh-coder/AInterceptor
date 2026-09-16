# .ai/CURRENT_TASK.md

## Current Milestone
**M1 — Single Provider Interception PoC**

## Status
M1.3 Claude transport interceptor implementation is staged. Synthetic tests are added but have not yet been executed in a local environment.

## Goal
Validate one provider end-to-end through the AInterceptor web-layer
interception boundary:

1. establish/validate a provider web session;
2. control/observe the provider web application's communication transport;
3. capture streaming events incrementally;
4. normalize those events into the AInterceptor stream/event contract;
5. expose the normalized stream to the Orchestrator without leaking provider transport details;
6. show the live normalized interception stream on the `/intercept` UI.

## Completed M1.2
- Reconciled the current `ProviderAdapter` source against the governance
  statement without inventing a fifth method.
- Defined `ProviderRuntime` as the M1 typed execution boundary.
- Restored the M1 Transport/Event Contract on the current `main` lineage;
  the earlier contract commit was not an ancestor of current `main`.
- Recorded ADR-0007 for the runtime/legacy-adapter boundary.

## M1.3 Implementation Staged
- Replaced Claude's page-side response `fetch()` and full-response buffering.
- Added a provider-local Chromium CDP Network transport observer.
- Added incremental SSE parsing for split UTF-8/network frames.
- Kept Playwright limited to session lifecycle and prompt submission.
- Added explicit session-expiry/recovery and stream-failure events.
- Preserved `ClaudeInterceptor` as a compatibility facade for the legacy adapter.
- Added synthetic parser tests; no live Claude request is part of this change.
- Recorded ADR-0008 for the CDP streaming mechanism.

## Important Constraint
`Network.streamResourceContent` is an experimental Chromium DevTools Protocol
capability. M1.3 therefore establishes the implementation boundary but does
not claim live transport compliance until the installed Chromium runtime and
actual Claude web transport are validated.

## Acceptance
- M1 architecture boundary is demonstrably respected.
- No provider inference API is used as the primary integration path.
- DOM scraping is not the core extraction path.
- Session expiry/failure is represented explicitly.
- Synthetic contract tests cover stream normalization and failure paths.
- No secrets are committed or logged.
- Validation produces PASS/FAIL evidence.
- Milestone completion follows the repository's milestone commit/checkpoint procedure.

## Next Procedure
M1.4 — execute synthetic contract tests, fix any failures, then prepare the
local pull checkpoint. Do not perform live provider validation until M1.4 is
PASS.
