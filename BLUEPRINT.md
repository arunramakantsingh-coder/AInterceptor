# BLUEPRINT.md — AInterceptor

Unified OpenAI-compatible gateway routing across AI providers via
web-layer interception (no provider APIs).

## Phases
| Phase | Name | Goal |
|---|---|---|
| 1 | Single Provider PoC | Intercept Claude or Gemini end-to-end |
| 2 | Session Harvesting + Direct HTTP | Fast path without browser |
| 3 | Multi-Provider Adapters | ChatGPT, DeepSeek, Qwen |
| 4 | Routing Engine | Fallback, load balancing, rate limits |
| 5 | OpenAI-Compatible API | /v1/chat/completions |
| 6 | Governance Dashboard | GitHub-integrated project UI |

## Legal Boundary
Personal, non-commercial, educational use only.
