"""Terminal rendering for the AInterceptor CLI control plane."""
from __future__ import annotations

from .registry import PROVIDER_ORDER


WIDTH = 60
RULE = "─" * WIDTH


def banner() -> str:
    return "\n".join(
        (
            "╔════════════════════════════════════════════════════════════╗",
            "║                    A I N T E R C E P T O R                 ║",
            "║              Web AI Provider Control Plane                 ║",
            "╚════════════════════════════════════════════════════════════╝",
        )
    )


def system_status() -> str:
    return "\n".join(
        (
            RULE,
            "  Interceptor          READY",
            "  Orchestrator         READY",
            "  Gateway              READY",
            RULE,
        )
    )


def providers_status() -> str:
    lines = ["Providers", RULE]
    for index, name in enumerate(PROVIDER_ORDER, 1):
        display = {
            "chatgpt": "ChatGPT Web",
            "claude": "Claude Web",
            "gemini": "Gemini Web",
            "grok": "Grok Web",
        }.get(name, name.title())
        status = "READY" if name == "claude" else "NOT CONFIGURED"
        marker = "●" if status == "READY" else "○"
        lines.append(f"  [{index}] {display:<16} {marker} {status}")
    return "\n".join(lines)


def provider_status(provider: str) -> str:
    display = {
        "chatgpt": "ChatGPT Web",
        "claude": "Claude Web",
        "gemini": "Gemini Web",
        "grok": "Grok Web",
    }.get(provider, provider.title())
    status = "READY" if provider == "claude" else "NOT CONFIGURED"
    session = "AUTHENTICATED" if provider == "claude" else "NOT AUTHENTICATED"
    runtime = (
        "backend.app.interception.claude.ClaudeRuntime"
        if provider == "claude"
        else "not-configured"
    )
    return "\n".join(
        (
            f"Provider: {display}",
            f"Status:   {status}",
            f"Session:  {session}",
            f"Runtime:  {runtime}",
        )
    )


def global_help() -> str:
    return "\n".join(
        (
            "Global commands:",
            "  help / ?             Show this help",
            "  providers            Show provider status",
            "  status               Show system status",
            "  use <provider>       Enter provider context",
            "  sessions             Show sessions",
            "  diagnostics          Show diagnostics",
            "  version              Show CLI version",
            "  clear                Clear screen",
            "  exit / quit          Exit AInterceptor",
        )
    )


def provider_help() -> str:
    return "\n".join(
        (
            "Provider commands:",
            "  help / ?             Show this help",
            "  status               Show provider status",
            "  session              Show provider session",
            "  chat [prompt]        Chat through provider runtime",
            "  diagnostics          Provider diagnostics",
            "  doctor               Provider health check",
            "  back                 Return to global context",
            "  exit                 Exit AInterceptor",
        )
    )
