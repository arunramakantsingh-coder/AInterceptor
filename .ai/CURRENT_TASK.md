# .ai/CURRENT_TASK.md

## Current Milestone
**M1 — Single Provider Interception PoC**

## Status
M1.2 Provider Runtime Boundary is defined. No provider implementation is
being declared transport-compliant yet.

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

## Important Constraint
The existing Claude PoC uses page-side `fetch()` and buffers the complete
response before parsing. Treat it as transitional PoC code. Do not extend
that pattern as the final architecture. M1.3 must replace it with a real
transport/event interception implementation.

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
M1.3 — refactor the Claude provider runtime so browser/runtime objects remain
provider-local and provider communication is intercepted incrementally at the
transport/event layer. Do not perform live provider validation until synthetic
contract coverage exists.
