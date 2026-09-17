# AIRouter Gateway

Public API boundary for external applications such as CareerOS.

Initial endpoints:
- GET /v1/health
- GET /v1/providers
- GET /v1/models
- GET /v1/usage
- POST /v1/chat/completions

Chat requests use Bearer authentication. Local development uses the configured AIRouter API key.
The gateway delegates to the Orchestrator; provider browser and transport mechanics remain behind the Interceptor runtime boundary.
Claude is the first backed provider for this API milestone.
