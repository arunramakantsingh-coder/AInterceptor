# .ai/CURRENT_TASK.md

## Current Milestone
**M1 — Single Provider Interception PoC**

## Status
M0.1 Architecture & Requirements Reconciliation is complete as a documentation baseline. No provider implementation is being declared compliant yet.

## Goal
Validate one provider end-to-end through the AInterceptor web-layer interception boundary:

1. establish/validate a provider web session;
2. control/observe the provider web application's communication transport;
3. capture streaming events incrementally;
4. normalize those events into the AInterceptor stream/event contract;
5. expose the normalized stream to the Orchestrator without leaking provider transport details;
6. show the live normalized interception stream on the `/intercept` UI.

## Important Constraint
The existing Claude PoC uses page-side `fetch()` and buffers the complete response before parsing. Treat it as transitional PoC code. Do not extend that pattern as the final architecture. M1 must validate a true transport/event interception mechanism.

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
Inspect the existing Claude PoC, provider contract, interception abstractions and test scaffolding; diagnose the smallest coherent implementation required for M1 before changing provider code.
