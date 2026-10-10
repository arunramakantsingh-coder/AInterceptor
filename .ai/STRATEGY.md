# AInterceptor — Strategy Notes

Living document. Not code — thinking. Review quarterly.

## 2026-09-21 — The OpenRouter question

### The comparison

OpenRouter (valuation ~$1.3B, ~$140M annualized revenue, 90 employees):

| Dimension | OpenRouter | AInterceptor |
|---|---|---|
| Mechanism | Forwards to provider's **official API** | Intercepts provider's **web UI** |
| Auth | Paid API contracts with OpenAI/Anthropic/Google | Harvested browser session cookies |
| Cost model | Pays per-token upstream; 5.5% platform fee | Zero per-token cost (web tier) |
| Scale | 10T+ tokens/day | ~100–500 users per VM before flagging |
| Legitimacy | Fully sanctioned | Legally gray (ToS prohibits automated web access) |
| Business | Payment/routing layer between users and **official** APIs | Free access via web session harvesting |

OpenRouter is NOT doing what we do. They are a billing/routing layer on top
of real, paid, official APIs. Their whole moat is contracts + margin +
reliability. We have none of those.

### Real peers

Hobby-scale projects only:
- OpenClaw Zero Token — CDP + Playwright against web UIs
- clawapi — OpenAI-compatible wrapper around claude.ai web
- llm-router-proxy — Gemini free-tier web access

None are companies. None scaled. This is the tier we live in.

### The unavoidable fork

**Path 1 — stay web-layer**
- ✅ Free, no contracts
- ❌ Flags accounts at ~500 users
- ❌ Legally gray
- ❌ Providers break us monthly
- ❌ Cannot partner with upstream labs

**Path 2 — become an API router (OpenRouter-like)**
- ✅ Legitimate, scales
- ❌ Need real API keys for every provider
- ❌ Cost per token → need revenue model
- ❌ Competing with OpenRouter, LiteLLM, Portkey, etc.

### Questions to answer before choosing

1. Who is the customer? (CareerOS users? External devs? Just Arun?)
2. Free tier is a feature or an accident?
3. Revenue model — subscription, tokens, or nothing (personal tool)?
4. Acceptable legal risk (gray-zone ToS violation at scale)?
5. If scaling: which providers first, and what API contracts are needed?
6. Multi-account strategy per provider — how many before flagging?

### Current read (Arun + AI, 2026-09-21)

Treat AInterceptor as a **personal tool for CareerOS** unless proven otherwise.
Don't build scaling infrastructure (Redis, LB, K8s) until a real second user
appears. Focus on Path A (HTTP, no browser) because it's the only path that
scales at all — Path B stays a fallback for admin use.

Revisit when:
- CareerOS has paying users
- Or a second real user requests access
- Or a provider starts enforcing web-UI automation detection

### The dashboard scheduler idea

Arun suggested: build a task/todo system in the AInterceptor dashboard so
strategic items like this live in the product, not just in markdown.
Noted. Deferred until /v1 + product basics are stable.
See FUTURE_WORK.md → "Dashboard: strategy / todo board"
