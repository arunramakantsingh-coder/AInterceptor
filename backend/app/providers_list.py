"""Canonical provider list. Single source of truth."""
from __future__ import annotations

ALL_PROVIDERS: list[str] = [
    "claude",
    "chatgpt",
    "gemini",
    "deepseek",
    "mistral",
    "qwen",
    "huggingchat",
    "perplexity",
    "grok",
    "poe",
]

# Providers with a direct-HTTP streamer implemented
PATH_A_SUPPORTED: list[str] = [
    "deepseek",
    "claude",
    "mistral",
    "qwen",
    "huggingchat",
    "perplexity",
    "grok",
]

# Providers that require a headless browser (ChatGPT PoW, Gemini page tokens, Poe GraphQL)
PATH_B_REQUIRED: list[str] = [
    "chatgpt",
    "gemini",
    "poe",
]
