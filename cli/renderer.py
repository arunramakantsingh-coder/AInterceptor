"""Terminal rendering for the AIRouter NOS control plane."""
from __future__ import annotations

from . import __version__
from .nos import PROVIDERS, provider_status, self_tests, system_info

WIDTH = 68
RULE = "─" * WIDTH


def boot_console() -> str:
    return "\n".join((
        "╔════════════════════════════════════════════════════════════════════╗",
        "║                         AInterceptor                              ║",
        "║                    AI Router Control Console                      ║",
        "╚════════════════════════════════════════════════════════════════════╝",
        "",
        "Type 'airouter' to initialize the AIRouter NOS.",
    ))


def banner() -> str:
    return "\n".join((
        "╔════════════════════════════════════════════════════════════════════╗",
        "║                          A I R O U T E R                           ║",
        "║                AI ROUTER OPERATING SYSTEM                         ║",
        "║                     AInterceptor Project                           ║",
        "╚════════════════════════════════════════════════════════════════════╝",
    ))


def bootstrap() -> str:
    lines = [
        f"AIRouter Software, Version {__version__}",
        "AI ROUTER OPERATING SYSTEM",
        "Copyright (c) 2026 AInterceptor Project",
        "",
        "Initializing AI Routing Subsystem ............... done",
        "Initializing Provider Interceptor Engine ........ done",
        "Initializing Session Manager .................... done",
        "Initializing Model Registry ...................... ready",
        "Initializing Usage & Credit Engine .............. ready",
        "Initializing Orchestrator ....................... ready",
        "",
        "Hardware:",
    ]
    info = system_info()
    lines.extend((
        f"  Hostname  : {info['hostname']}",
        f"  OS        : {info['os']}",
        f"  CPU cores : {info['cpu']}",
        f"  Memory    : {info['memory']}",
        f"  Runtime   : Python {info['python']}",
        f"  Browser   : {info['browser']}",
        "",
        "Self-tests:",
    ))
    lines.extend(f"  {name:<28} {status}" for name, status in self_tests())
    lines.append("")
    return "\n".join(lines)


def providers_status() -> str:
    lines = ["AI Providers", RULE]
    for index, item in enumerate(PROVIDERS, 1):
        status = provider_status(item.name)
        marker = "●" if status in {"CONFIGURED", "READY"} else "○"
        lines.append(f"  [{index}] {item.display_name:<18} {marker} {status}")
    return "\n".join(lines)


def provider_status_view(provider: str) -> str:
    item = next((p for p in PROVIDERS if p.name == provider), None)
    if item is None:
        return f"% Unknown provider: {provider}"
    return "\n".join((
        f"Provider:     {item.display_name}",
        f"Status:       {provider_status(provider)}",
        f"Transport:    {item.transport_kind}",
        f"Capabilities: {', '.join(item.capabilities)}",
        f"Runtime:      {item.runtime_path or 'not implemented'}",
    ))


def system_status() -> str:
    return "\n".join((
        "System Status",
        RULE,
        "  Gateway              READY",
        "  Orchestrator         READY",
        "  Interceptor          READY",
        "  Session Manager      READY",
        "  Model Registry       READY",
        "  Usage/Credit Engine  READY",
    ))


def version_view() -> str:
    return "\n".join((
        f"AIRouter Software, Version {__version__}",
        "AIRouter NOS control plane",
        "AInterceptor web-layer AI routing project",
    ))


def system_view() -> str:
    info = system_info()
    return "\n".join(f"{key:<12}: {value}" for key, value in info.items())


def models_view() -> str:
    return "Model Registry\n" + RULE + "\n  No provider models have been discovered yet."


def sessions_view() -> str:
    return "Session Manager\n" + RULE + "\n  Session inventory is runtime-owned."


def counters_view(counters: dict[str, int]) -> str:
    return "\n".join((
        "AI Request Counters", RULE,
        f"  Requests    : {counters['requests']}",
        f"  Success     : {counters['success']}",
        f"  Failed      : {counters['failed']}",
        f"  Fallbacks   : {counters['fallbacks']}",
    ))


def credits_view() -> str:
    return "\n".join((
        "AI Credit Ledger", RULE,
        "  No provider credit/balance data has been collected yet.",
        "  Provider accounting semantics will be preserved per provider.",
    ))


def routes_view() -> str:
    return "\n".join((
        "AI Routing Table", RULE,
        "  No routing policies configured yet.",
        "  Capability-based routing contracts are initialized.",
    ))


def help_view(mode: str) -> str:
    if mode == "user-exec":
        return "\n".join((
            "User EXEC commands:",
            "  enable                 Enter privileged EXEC mode",
            "  show ?                 Show available show commands",
            "  show version           Show software version",
            "  show system            Show system information",
            "  show ai                Show AI subsystem status",
            "  airouter               Re-display NOS banner",
            "  logout                 Exit the console",
            "  ?                      Show this help",
        ))
    if mode == "privileged-exec":
        return "\n".join((
            "Privileged EXEC commands:",
            "  show <topic>            Show operational state",
            "  configure terminal      Enter global configuration",
            "  clear counters          Clear in-memory counters",
            "  disable                 Return to user EXEC",
            "  exit                    Exit the console",
            "  ?                       Show this help",
        ))
    if mode == "config":
        return "\n".join((
            "Global configuration commands:",
            "  ai                      Enter AI subsystem configuration",
            "  exit                    Return to privileged EXEC",
            "  end                     Return to privileged EXEC",
            "  ?                       Show this help",
        ))
    if mode == "config-ai":
        return "\n".join((
            "AI subsystem configuration commands:",
            "  provider <name>         Configure a provider",
            "  model <name>            Configure model policy (registry-backed later)",
            "  route <name>            Configure routing policy (later milestone)",
            "  prompt <name>           Configure prompt profile (later milestone)",
            "  session                 Configure session policy (later milestone)",
            "  api                     Configure application API clients (later milestone)",
            "  exit                    Return to global configuration",
        ))
    if mode == "config-ai-provider":
        return "\n".join((
            "AI provider configuration commands:",
            "  enable                  Enable provider in routing policy",
            "  disable                 Disable provider in routing policy",
            "  login                   Enter provider authentication workflow",
            "  logout                  End provider session",
            "  session                 Show session state",
            "  model                   Show provider model policy",
            "  health                  Show provider health",
            "  exit                    Return to AI configuration",
        ))
    return "Type ? for commands."
