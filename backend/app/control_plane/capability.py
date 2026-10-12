"""Capability registry: which provider is good at what.

Scores are 1-5 (higher = better). Used by the router to pick a provider
for a declared capability (reasoning, coding, fast, long_context, vision,
tools).

Edit CAPABILITIES to tune. No code changes needed for scoring changes.
"""
from __future__ import annotations


CAPABILITIES = ["reasoning", "coding", "fast", "long_context", "vision", "tools"]


# Provider x capability scores.
# vision/tools: True/False. Numeric: 1-5. "meta": pass-through (Poe).
SCORES: dict[str, dict] = {
    "claude":      {"reasoning": 5, "coding": 4, "fast": 3, "long_context": 5, "vision": True,  "tools": True},
    "chatgpt":     {"reasoning": 5, "coding": 5, "fast": 4, "long_context": 4, "vision": True,  "tools": True},
    "gemini":      {"reasoning": 4, "coding": 4, "fast": 5, "long_context": 5, "vision": True,  "tools": True},
    "deepseek":    {"reasoning": 4, "coding": 5, "fast": 4, "long_context": 3, "vision": False, "tools": True},
    "mistral":     {"reasoning": 3, "coding": 4, "fast": 4, "long_context": 3, "vision": False, "tools": True},
    "lechat":      {"reasoning": 3, "coding": 4, "fast": 4, "long_context": 3, "vision": False, "tools": True},
    "qwen":        {"reasoning": 3, "coding": 4, "fast": 4, "long_context": 4, "vision": False, "tools": True},
    "kimi":        {"reasoning": 4, "coding": 4, "fast": 4, "long_context": 5, "vision": False, "tools": True},
    "yi":          {"reasoning": 3, "coding": 3, "fast": 4, "long_context": 3, "vision": False, "tools": True},
    "glm":         {"reasoning": 4, "coding": 4, "fast": 4, "long_context": 4, "vision": False, "tools": True},
    "doubao":      {"reasoning": 3, "coding": 3, "fast": 5, "long_context": 3, "vision": False, "tools": False},
    "huggingchat": {"reasoning": 3, "coding": 3, "fast": 4, "long_context": 3, "vision": False, "tools": True},
    "perplexity":  {"reasoning": 3, "coding": 3, "fast": 5, "long_context": 3, "vision": True,  "tools": False},
    "you":         {"reasoning": 3, "coding": 3, "fast": 5, "long_context": 3, "vision": True,  "tools": False},
    "phind":       {"reasoning": 3, "coding": 5, "fast": 4, "long_context": 3, "vision": False, "tools": True},
    "grok":        {"reasoning": 4, "coding": 4, "fast": 4, "long_context": 4, "vision": True,  "tools": True},
    "meta":        {"reasoning": 3, "coding": 3, "fast": 4, "long_context": 4, "vision": False, "tools": True},
    "copilot":     {"reasoning": 4, "coding": 4, "fast": 5, "long_context": 4, "vision": True,  "tools": True},
    "character":   {"reasoning": 2, "coding": 2, "fast": 4, "long_context": 2, "vision": False, "tools": False},
    "poe":         {"reasoning": 3, "coding": 3, "fast": 3, "long_context": 3, "vision": False, "tools": False},
}


def score(provider: str, capability: str) -> float:
    """Return 0.0-1.0 score for a provider-capability pair."""
    entry = SCORES.get(provider.lower(), {})
    v = entry.get(capability)
    if v is True:
        return 1.0
    if v is False or v is None:
        return 0.0
    try:
        return float(v) / 5.0
    except (TypeError, ValueError):
        return 0.0


def providers_for(capability: str, min_score: float = 0.5) -> list[str]:
    """Return providers sorted by score for a capability (best first)."""
    rows = []
    for provider in SCORES:
        s = score(provider, capability)
        if s >= min_score:
            rows.append((provider, s))
    rows.sort(key=lambda x: x[1], reverse=True)
    return [p for p, _ in rows]


def all_capabilities() -> list[str]:
    return list(CAPABILITIES)
