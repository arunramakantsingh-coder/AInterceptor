"""Provider registry — single source of truth for CDP port, session, transport.

Every provider has its own CDP endpoint so multiple providers can run in
parallel. Adding a provider = adding one entry here.
"""
from __future__ import annotations
import os, pathlib
from dataclasses import dataclass, field


@dataclass(frozen=True)
class ProviderEntry:
    name: str
    home_url: str
    transport: str                # "sse" (Claude) | "cdp" (non-Claude)
    cdp_port: int                 # fixed port so providers never collide
    session_env: str              # env var to override storage_state path
    login_markers: tuple[str, ...] = ()
    response_markers: tuple[str, ...] = ()
    request_markers: tuple[str, ...] = ()
    default_model: str = ""
    composer_selectors: tuple[str, ...] = ()
    extra: dict = field(default_factory=dict)


REGISTRY: dict[str, ProviderEntry] = {
    "claude": ProviderEntry(
        name="claude",
        home_url="https://claude.ai/",
        transport="sse",
        cdp_port=9222,
        session_env="AINTERCEPTOR_CLAUDE_STORAGE_STATE",
        login_markers=("/login", "/auth", "/signin"),
        response_markers=("/api/organizations/", "/completion"),
        request_markers=("/api/organizations/", "/completion"),
        default_model="claude-web",
        composer_selectors=('div[contenteditable="true"]', "textarea"),
    ),
    "deepseek": ProviderEntry(
        name="deepseek",
        home_url="https://chat.deepseek.com/",
        transport="cdp",
        cdp_port=9223,
        session_env="AINTERCEPTOR_DEEPSEEK_STORAGE_STATE",
        login_markers=("/login", "/auth", "/sign_in", "/signin"),
        response_markers=("/api/v0/chat/completion",),
        request_markers=("/api/v0/chat/completion",),
        default_model="deepseek-flash",
        composer_selectors=(
            'textarea[placeholder*="Message"]',
            'textarea[placeholder*="message"]',
            "textarea",
            '[contenteditable="true"]',
            '[role="textbox"]',
        ),
    ),
    "chatgpt": ProviderEntry(
        name="chatgpt",
        home_url="https://chatgpt.com/",
        transport="cdp",
        cdp_port=9224,
        session_env="AINTERCEPTOR_CHATGPT_STORAGE_STATE",
        login_markers=("/auth/login",),
        response_markers=("/backend-api/conversation",),
        request_markers=("/backend-api/conversation",),
        default_model="chatgpt-web",
        composer_selectors=("#prompt-textarea", 'div[contenteditable="true"]', "textarea"),
    ),
    "gemini": ProviderEntry(
        name="gemini",
        home_url="https://gemini.google.com/",
        transport="cdp",
        cdp_port=9225,
        session_env="AINTERCEPTOR_GEMINI_STORAGE_STATE",
        login_markers=("/accounts/", "signin"),
        response_markers=("StreamGenerate", "/assistant.lamda"),
        request_markers=("StreamGenerate",),
        default_model="gemini-web",
        composer_selectors=('div[contenteditable="true"]', "textarea"),
    ),
}


def get(provider: str) -> ProviderEntry:
    p = provider.lower()
    if p not in REGISTRY:
        raise KeyError(f"unknown provider: {provider}; known: {list(REGISTRY)}")
    return REGISTRY[p]


def cdp_url(provider: str) -> str | None:
    """Return CDP URL for this provider, or None if env forces fallback."""
    entry = get(provider)
    env_override = os.environ.get(f"AINTERCEPTOR_{provider.upper()}_CDP_URL")
    if env_override == "":
        return None
    if env_override:
        return env_override
    return f"http://127.0.0.1:{entry.cdp_port}"


def session_path(provider: str) -> pathlib.Path:
    entry = get(provider)
    env_override = os.environ.get(entry.session_env)
    if env_override:
        return pathlib.Path(env_override)
    return pathlib.Path(".ainterceptor") / provider / "storage_state.json"


def all_providers() -> list[str]:
    return list(REGISTRY)
