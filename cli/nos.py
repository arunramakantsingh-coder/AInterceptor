"""AIRouter NOS state and runtime-neutral metadata.

This module owns CLI/control-plane state only. Provider transport, session,
and authentication mechanics remain in the Interceptor subsystem.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import ctypes
import os
import platform
import sys
from typing import Any


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
    runtime_path: str | None = None


PROVIDERS: tuple[ProviderDefinition, ...] = (
    ProviderDefinition(
        "chatgpt", "ChatGPT Web", "web", ("reasoning", "coding", "research", "general"),
    ),
    ProviderDefinition(
        "claude", "Claude Web", "web", ("reasoning", "coding", "long_context", "documents"),
        "backend.app.interception.claude.ClaudeRuntime",
    ),
    ProviderDefinition(
        "gemini", "Gemini Web", "web", ("multimodal", "research", "documents", "general"),
    ),
    ProviderDefinition(
        "deepseek", "DeepSeek Web", "web", ("reasoning", "coding", "math", "structured_output"),
    ),
)


@dataclass
class NOSState:
    mode: Mode = Mode.BOOT
    provider: str | None = None
    chat_provider: str | None = None
    running: bool = True
    counters: dict[str, int] = field(default_factory=lambda: {
        "requests": 0,
        "success": 0,
        "failed": 0,
        "fallbacks": 0,
    })
    config: dict[str, Any] = field(default_factory=dict)

    @property
    def provider_definition(self) -> ProviderDefinition | None:
        return provider_definition(self.provider)


def provider_definition(name: str | None) -> ProviderDefinition | None:
    if not name:
        return None
    name = name.lower()
    return next((item for item in PROVIDERS if item.name == name), None)


def provider_configured(name: str) -> bool:
    """Return only what can be determined without touching provider sessions."""
    if name == "claude":
        return bool(os.getenv("AINTERCEPTOR_CLAUDE_CDP_URL")) or os.path.exists(
            os.getenv("AINTERCEPTOR_CLAUDE_STORAGE_STATE", "")
        )
    return False


def provider_status(name: str) -> str:
    if provider_configured(name):
        return "CONFIGURED"
    if name == "claude":
        return "RUNTIME AVAILABLE"
    return "NOT CONFIGURED"


def _memory_gb() -> str:
    try:
        if os.name == "nt":
            class MemoryStatus(ctypes.Structure):
                _fields_ = [("length", ctypes.c_ulong), ("memory_load", ctypes.c_ulong),
                            ("total_phys", ctypes.c_ulonglong), ("avail_phys", ctypes.c_ulonglong),
                            ("total_page", ctypes.c_ulonglong), ("avail_page", ctypes.c_ulonglong),
                            ("total_virtual", ctypes.c_ulonglong), ("avail_virtual", ctypes.c_ulonglong),
                            ("avail_extended", ctypes.c_ulonglong)]
            status = MemoryStatus()
            status.length = ctypes.sizeof(MemoryStatus)
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
                return f"{status.total_phys / (1024 ** 3):.1f} GB"
        pages = os.sysconf("SC_PHYS_PAGES")
        page_size = os.sysconf("SC_PAGE_SIZE")
        return f"{pages * page_size / (1024 ** 3):.1f} GB"
    except Exception:
        return "unknown"


def system_info() -> dict[str, str]:
    return {
        "hostname": platform.node() or "unknown",
        "os": f"{platform.system()} {platform.release()}",
        "arch": platform.machine() or "unknown",
        "cpu": str(os.cpu_count() or "unknown"),
        "memory": _memory_gb(),
        "python": platform.python_version(),
        "browser": "Chromium/CDP" if os.getenv("AINTERCEPTOR_CLAUDE_CDP_URL") else "not attached",
    }


def self_tests() -> list[tuple[str, str]]:
    tests: list[tuple[str, str]] = []
    try:
        import prompt_toolkit  # noqa: F401
        tests.append(("CLI control plane", "PASS"))
    except Exception as exc:
        tests.append(("CLI control plane", f"FAIL ({exc.__class__.__name__})"))
    tests.append(("Provider registry", "PASS" if PROVIDERS else "FAIL"))
    tests.append(("Orchestrator boundary", "READY"))
    tests.append(("Interceptor boundary", "READY"))
    return tests
