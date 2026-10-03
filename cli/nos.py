"""AIRouter NOS state, provider registry and persistent configuration metadata."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import ctypes
import importlib
import os
import platform
from typing import Any, Iterable

from .config_store import load_startup_config, provider_session_state, provider_storage_path, save_startup_config


class Mode(str, Enum):
    BOOT = "boot"
    USER_EXEC = "user-exec"
    PRIVILEGED_EXEC = "privileged-exec"
    CONFIG = "config"
    CONFIG_AI = "config-ai"
    CONFIG_AI_PROVIDER = "config-ai-provider"
    CHAT = "chat"


@dataclass(frozen=True)
class ProviderDefinition:
    name: str
    display_name: str
    transport_kind: str
    capabilities: tuple[str, ...]
    runtime_path: str


@dataclass(frozen=True)
class ModelDefinition:
    provider: str
    model_id: str
    display_name: str
    capabilities: tuple[str, ...]
    catalog_source: str


PROVIDERS: tuple[ProviderDefinition, ...] = (
    ProviderDefinition("chatgpt", "ChatGPT Web", "web", ("reasoning", "coding", "research", "general"), "app.interception.chatgpt.ChatGPTRuntime"),
    ProviderDefinition("claude", "Claude Web", "web", ("reasoning", "coding", "long_context", "documents"), "app.interception.claude.ClaudeRuntime"),
    ProviderDefinition("gemini", "Gemini Web", "web", ("multimodal", "research", "documents", "general"), "app.interception.gemini.GeminiRuntime"),
    ProviderDefinition("deepseek", "DeepSeek Web", "web", ("reasoning", "coding", "math", "structured_output"), "app.interception.deepseek.DeepSeekRuntime"),
)

MODEL_CATALOG: tuple[ModelDefinition, ...] = (
    ModelDefinition("chatgpt", "gpt-5.6-sol", "GPT-5.6 Sol", ("reasoning", "coding", "research", "cybersecurity"), "OpenAI product catalog"),
    ModelDefinition("chatgpt", "gpt-5.6-luna", "GPT-5.6 Luna", ("speed", "general", "coding"), "OpenAI product catalog"),
    ModelDefinition("chatgpt", "gpt-6-pro", "GPT-6 Pro", ("reasoning", "coding", "research"), "OpenAI product catalog"),
    ModelDefinition("claude", "claude-opus-4-8", "Claude Opus 4.8", ("reasoning", "coding", "long_context"), "Anthropic model catalog"),
    ModelDefinition("claude", "claude-sonnet-5", "Claude Sonnet 5", ("reasoning", "coding", "general"), "Anthropic model catalog"),
    ModelDefinition("claude", "claude-sonnet-4-6", "Claude Sonnet 4.6", ("reasoning", "coding", "long_context"), "Anthropic model catalog"),
    ModelDefinition("claude", "claude-haiku-4-5-20251001", "Claude Haiku 4.5", ("speed", "coding", "general"), "Anthropic model catalog"),
    ModelDefinition("gemini", "gemini-3.6-flash", "Gemini 3.6 Flash", ("speed", "reasoning", "multimodal", "agentic"), "Google Gemini model catalog"),
    ModelDefinition("gemini", "gemini-3.5-flash", "Gemini 3.5 Flash", ("reasoning", "coding", "multimodal"), "Google Gemini model catalog"),
    ModelDefinition("gemini", "gemini-3.5-flash-lite", "Gemini 3.5 Flash-Lite", ("speed", "cost", "multimodal"), "Google Gemini model catalog"),
    ModelDefinition("gemini", "gemini-3.1-pro-preview", "Gemini 3.1 Pro", ("reasoning", "coding", "agentic", "multimodal"), "Google Gemini model catalog"),
    ModelDefinition("deepseek", "deepseek-flash", "DeepSeek V4.1 Flash", ("reasoning", "coding", "math", "vision", "structured_output"), "DeepSeek model catalog"),
    ModelDefinition("deepseek", "deepseek-v4-pro", "DeepSeek V4 Pro", ("reasoning", "coding", "math", "structured_output"), "DeepSeek model catalog"),
)


@dataclass
class NOSState:
    mode: Mode = Mode.BOOT
    provider: str | None = None
    chat_provider: str | None = None
    selected_model: str | None = None
    running: bool = True
    counters: dict[str, int] = field(default_factory=lambda: {"requests": 0, "success": 0, "failed": 0, "fallbacks": 0})
    config: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.config:
            self.config = load_startup_config()
        self.selected_model = self.config.get("ai", {}).get("selected_model") or self.selected_model

    @property
    def provider_definition(self) -> ProviderDefinition | None:
        return provider_definition(self.provider)

    def save_startup(self) -> None:
        self.config.setdefault("ai", {})["selected_model"] = self.selected_model
        save_startup_config(self.config)


def provider_definition(name: str | None) -> ProviderDefinition | None:
    if not name:
        return None
    return next((item for item in PROVIDERS if item.name == name.lower()), None)


def runtime_available(name: str) -> bool:
    item = provider_definition(name)
    if item is None:
        return False
    module_name, _, class_name = item.runtime_path.rpartition(".")
    try:
        module = importlib.import_module(module_name)
        return hasattr(module, class_name)
    except Exception:
        return False


def provider_configured(name: str) -> bool:
    return provider_storage_path(name).exists() or bool(os.getenv(f"AINTERCEPTOR_{name.upper()}_CDP_URL"))


def provider_status(name: str) -> str:
    if provider_configured(name):
        return "CONFIGURED"
    if runtime_available(name):
        return "RUNTIME AVAILABLE"
    return "NOT AVAILABLE"


def provider_session_status(name: str) -> str:
    return provider_session_state(name)


def model_definitions(provider: str | None = None) -> tuple[ModelDefinition, ...]:
    if provider is None:
        return MODEL_CATALOG
    return tuple(item for item in MODEL_CATALOG if item.provider == provider.lower())


def model_definition(model_id: str, provider: str | None = None) -> ModelDefinition | None:
    candidates = model_definitions(provider)
    exact = next((item for item in candidates if item.model_id == model_id.lower()), None)
    if exact:
        return exact
    matches = [item for item in candidates if item.model_id.startswith(model_id.lower())]
    return matches[0] if len(matches) == 1 else None


def unique_prefix(value: str, candidates: Iterable[str]) -> str | None:
    matches = [candidate for candidate in candidates if candidate.lower().startswith(value.lower())]
    return matches[0] if len(matches) == 1 else None


def prefix_matches(value: str, candidates: Iterable[str]) -> list[str]:
    return [candidate for candidate in candidates if candidate.lower().startswith(value.lower())]


def _memory_gb() -> str:
    try:
        if os.name == "nt":
            class MemoryStatus(ctypes.Structure):
                _fields_ = [("length", ctypes.c_ulong), ("memory_load", ctypes.c_ulong), ("total_phys", ctypes.c_ulonglong), ("avail_phys", ctypes.c_ulonglong), ("total_page", ctypes.c_ulonglong), ("avail_page", ctypes.c_ulonglong), ("total_virtual", ctypes.c_ulonglong), ("avail_virtual", ctypes.c_ulonglong), ("avail_extended", ctypes.c_ulonglong)]
            status = MemoryStatus(); status.length = ctypes.sizeof(MemoryStatus)
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
                return f"{status.total_phys / (1024 ** 3):.1f} GB"
        return f"{os.sysconf('SC_PHYS_PAGES') * os.sysconf('SC_PAGE_SIZE') / (1024 ** 3):.1f} GB"
    except Exception:
        return "unknown"


def system_info() -> dict[str, str]:
    return {"hostname": platform.node() or "unknown", "os": f"{platform.system()} {platform.release()}", "arch": platform.machine() or "unknown", "cpu": str(os.cpu_count() or "unknown"), "memory": _memory_gb(), "python": platform.python_version(), "browser": "Chromium/CDP"}


def self_tests() -> list[tuple[str, str]]:
    tests: list[tuple[str, str]] = []
    try:
        import prompt_toolkit  # noqa: F401
        tests.append(("CLI control plane", "PASS"))
    except Exception as exc:
        tests.append(("CLI control plane", f"FAIL ({exc.__class__.__name__})"))
    tests.append(("Provider registry", "PASS" if all(runtime_available(p.name) for p in PROVIDERS) else "DEGRADED"))
    tests.append(("Model catalog", "PASS" if MODEL_CATALOG else "FAIL"))
    tests.append(("Persistent NVRAM store", "READY"))
    tests.append(("Orchestrator boundary", "READY"))
    tests.append(("Interceptor boundary", "READY"))
    return tests
