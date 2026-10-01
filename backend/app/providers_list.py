"""Canonical provider list.

ALL_PROVIDERS is derived from the single catalog in
app.control_plane.state.ALL_KNOWN so the dispatcher gate and the UI
catalog can never disagree again. (They previously did: the gate listed
10 providers while the UI advertised 20, so requests to the other 10
failed with a misleading "unknown provider".)
"""
from __future__ import annotations

from app.control_plane.state import ALL_KNOWN

# Every catalog provider is dispatchable. A provider whose interception
# module is absent raises a precise error at dispatch time rather than
# being silently rejected here.
ALL_PROVIDERS: list[str] = list(ALL_KNOWN)

# Providers whose interception module is not implemented yet. Kept
# explicit so the CLI can report "no runtime" honestly.
NO_RUNTIME_MODULE: list[str] = ["perplexity"]

# Providers with a direct-HTTP streamer implemented (Path A)
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
