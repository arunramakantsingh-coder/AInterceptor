# AInterceptor — Web Interception Architecture Rules

Status: M0 GOVERNANCE FOUNDATION

## 1. Purpose

This document defines the architectural meaning of web-layer interception in AInterceptor. It is mandatory reading before changing provider runtimes, sessions, transport handling, streaming, or provider adapters.

## 2. Core Principle

AInterceptor is a web-layer AI router. It does not use provider inference APIs as the primary integration mechanism.

The provider's public web application is the communication surface. AInterceptor's interception runtime controls and observes the communication path used by an authenticated provider web session.

## 3. Web UI Is Not the Business Contract

Do not make DOM scraping of provider response pages the core integration contract.

Browser automation may be used to establish, authenticate, maintain, or recover a provider session. Provider UI structure must not become AInterceptor's canonical response interface.

Preferred abstraction:

```text
Provider Web Application
        |
        | browser/web transport
        v
Interception Boundary
        |
        v
Provider transport events
        |
        v
AInterceptor normalization contract
```

## 4. Provider Runtime Boundary

Each provider runtime owns provider-specific details:

- session establishment;
- authentication/session state handling;
- transport discovery;
- request interception;
- response/event interception;
- streaming protocol handling;
- provider-specific normalization;
- session health and recovery.

The Orchestrator must not contain provider-specific transport logic.

## 5. Interceptor vs Orchestrator

### Interceptor

Owns communication with provider web sessions and transport events.

### Orchestrator

Owns provider selection, routing policy, capability matching, fallback, rate limiting, request lifecycle and the application-facing gateway contract.

Cross-boundary communication occurs through explicit typed interfaces.

## 6. Event Model

The interception layer should represent communication as structured events where practical:

```text
SESSION_CREATED
SESSION_READY
REQUEST_INTERCEPTED
REQUEST_FORWARDED
STREAM_STARTED
STREAM_DELTA
STREAM_COMPLETED
STREAM_FAILED
SESSION_EXPIRED
SESSION_RECOVERY_REQUIRED
```

The exact event schema is a design artifact and must be versioned before becoming a shared contract.

## 7. Provider Adapter Rule

A provider adapter must not expose raw browser objects to the Orchestrator. It must expose the stable AInterceptor interception contract.

Provider-specific assumptions remain inside the provider runtime.

## 8. No Hidden API Aggregation

Do not introduce provider API keys, provider inference endpoints, or API-specific SDK calls merely to make a provider integration easier. Any exception requires an ADR and explicit approval because it changes the core product boundary.

## 9. Streaming

Streaming is a first-class requirement. The design must account for incremental provider events, cancellation, disconnects, retries, backpressure and normalization without requiring rendered-page extraction.

## 10. Security

Treat provider sessions and session material as sensitive. Never log cookies, authentication headers, tokens, session identifiers, or equivalent secrets. Session persistence, encryption, rotation and revocation must be explicitly designed.

## 11. Legal / Terms Boundary

Provider-specific implementation must be reviewed against applicable provider terms, authentication requirements, rate limits, privacy requirements and applicable law before production use. The project must not assume that a technically possible interception method is automatically permitted.

## 12. Definition of Done

A provider interception milestone is complete only when:

- the communication boundary is documented;
- session lifecycle is understood;
- request and streaming behavior is captured by tests;
- provider-specific logic remains isolated;
- no provider inference API has been introduced without an approved exception;
- secrets are protected;
- failure/recovery behavior is tested;
- normalized output is validated against the AInterceptor contract;
- GitHub checkpoint and documentation are updated.
