# BLUEPRINT.md — AInterceptor

**A Cisco-style AI Network Operating System.**
One endpoint. Many AI web interfaces. Zero provider APIs.

## Two Products
### Webapp (end users)
User opens our web UI, logs in, chats with any connected AI provider.
Can fan out one prompt to many providers, compare side by side, pick best.

### API (developers)
External apps authenticate with an AInterceptor key and call an
OpenAI-compatible endpoint. Router selects provider by capability,
enforces policy, returns result. Used by CareerOS.

Both share: session store, provider runtimes, routing engine, auth, billing.

## Core Concept
AInterceptor does NOT use provider APIs. It drives the real provider web
UI in an authenticated browser and captures network transport (SSE/WS)
at the browser's CDP boundary — Layer 6.

Provider Web App -> Browser -> CDP Network -> AInterceptor Transport
Capture -> Provider Parser -> StreamEvent -> Orchestrator -> Client.

## Architecture (summary)
Management Plane: CLI (Cisco-style), Web UI, SSH (admin), API.
Control Plane: config engine, NVRAM, policy, billing.
Orchestrator: routing, capability, fallback, rate limits.
Interceptor: provider runtimes, session lifecycle, transport capture.
Browser Runtime: Chromium (headless), CDP sessions, storage state.

## Supported Providers
Claude, DeepSeek, ChatGPT, Gemini, Mistral, Qwen, HuggingChat,
Perplexity, Grok, Poe.

Path A = direct HTTPS with harvested cookies (fast).
Path B = headless Chromium driving real UI (universal).
ChatGPT needs B. Others prefer A, fall back to B.

## Login Model
Default: airouter-agent on user's own machine opens real Chrome,
user logs in, agent captures storage state, uploads.
Power-user: manual cookie export.
Server never opens a browser for login.

## Deployment
Docker-first, Linux runtime, Postgres.
No Xvfb, no VNC, no visible Chrome on the server.

## Roadmap (summary)
1: API product + agent (ChatGPT E2E)
2: DeepSeek + Claude + Gemini via API
3: Orchestrator (capability, fallback, load balance)
4: Webapp (chat + comparison)
5: Billing, quotas, teams
6: Policy-based routing, cost optimization
7: Public launch, multi-tenant, Kubernetes

Full detail in PROJECT/ROADMAP.md.
