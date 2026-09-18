
"""AInterceptor provider registry.

All providers share ONE Chrome instance on CDP port 9222 (shared
profile). Each provider owns a tab URL. The runtime selects the tab
matching the provider's home_url.
"""
from __future__ import annotations
import os, pathlib
from dataclasses import dataclass

SHARED_PORT = 9222
SHARED_PROFILE = pathlib.Path(".ainterceptor") / "chrome-profile-shared"


@dataclass(frozen=True)
class ProviderEntry:
    name: str
    home_url: str
    tab_url_prefix: str
    transport: str = "cdp"
    default_model: str = ""
    composer_selectors: tuple[str, ...] = ()
    login_markers: tuple[str, ...] = ()
    response_markers: tuple[str, ...] = ()
    request_markers: tuple[str, ...] = ()


REGISTRY: dict[str, ProviderEntry] = {
    "chatgpt": ProviderEntry(
        name="chatgpt",
        home_url="https://chatgpt.com/",
        tab_url_prefix="chatgpt.com",
        default_model="chatgpt-web",
        composer_selectors=("#prompt-textarea", 'div[contenteditable="true"]', "textarea"),
        login_markers=("/auth/login",),
        response_markers=("/backend-api/conversation",),
        request_markers=("/backend-api/conversation",),
    ),
    "claude": ProviderEntry(
        name="claude",
        home_url="https://claude.ai/",
        tab_url_prefix="claude.ai",
        default_model="claude-web",
        composer_selectors=('div[contenteditable="true"]', "textarea"),
        login_markers=("/login", "/auth", "/signin"),
        response_markers=("/api/organizations/", "/completion"),
        request_markers=("/api/organizations/", "/completion"),
    ),
    "gemini": ProviderEntry(
        name="gemini",
        home_url="https://gemini.google.com/",
        tab_url_prefix="gemini.google.com",
        default_model="gemini-web",
        composer_selectors=('div[contenteditable="true"]', "textarea"),
        login_markers=("/accounts/", "signin"),
        response_markers=("StreamGenerate", "/assistant.lamda"),
        request_markers=("StreamGenerate",),
    ),
    "deepseek": ProviderEntry(
        name="deepseek",
        home_url="https://chat.deepseek.com/",
        tab_url_prefix="chat.deepseek.com",
        default_model="deepseek-flash",
        composer_selectors=(
            'textarea[placeholder*="Message"]',
            'textarea[placeholder*="message"]',
            "textarea",
            '[contenteditable="true"]',
            '[role="textbox"]',
        ),
        login_markers=("/login", "/auth", "/sign_in", "/signin"),
        response_markers=("/api/v0/chat/completion",),
        request_markers=("/api/v0/chat/completion",),
    ),
}


def get(provider: str) -> ProviderEntry:
    p = provider.lower()
    if p not in REGISTRY:
        raise KeyError(f"unknown provider: {provider}; known: {list(REGISTRY)}")
    return REGISTRY[p]


def cdp_url(provider: str) -> str | None:
    """Return the shared CDP URL. Env override respected."""
    env = os.environ.get(f"AINTERCEPTOR_{provider.upper()}_CDP_URL")
    if env == "":
        return None
    if env:
        return env
    return f"http://127.0.0.1:{SHARED_PORT}"


def session_path(provider: str) -> pathlib.Path:
    env = os.environ.get(f"AINTERCEPTOR_{provider.upper()}_STORAGE_STATE")
    if env:
        return pathlib.Path(env)
    return SHARED_PROFILE / "storage_state.json"


def all_providers() -> list[str]:
    return list(REGISTRY)
