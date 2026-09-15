# ARCHITECTURE.md

Client -> Routing Engine -> Provider Adapters -> Interception Layer ->
Provider Web UIs.

## Data
Session { provider, cookies, tokens, csrf, expiry } -> sessions/ (git-ignored)
Chunk { provider, delta, finish_reason, meta }
ProviderHealth { provider, status, last_success, error_rate, latency_ms }

## Interfaces
/v1/chat/completions (OpenAI JSON)
/health/providers (JSON)
/api/github/* (dashboard)

## Trust
Browser sandbox. Encrypted session vault. OAuth device flow for GitHub.
