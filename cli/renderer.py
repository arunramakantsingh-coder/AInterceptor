"""Cisco-style operational views for AIRouter."""
from __future__ import annotations

from . import __version__
from .config_store import STARTUP_CONFIG, load_startup_config, provider_session_status
from .nos import MODEL_CATALOG, PROVIDERS, model_definitions, provider_status, runtime_available, self_tests, system_info

WIDTH = 72
RULE = "─" * WIDTH


def boot_console() -> str:
    return "\n".join(("╔════════════════════════════════════════════════════════════════════════╗", "║                              AInterceptor                              ║", "║                       AI Router Control Console                         ║", "╚════════════════════════════════════════════════════════════════════════╝", "", "Type 'bootai' to enter AInterceptor-BOOT mode."))


def banner() -> str:
    return "\n".join(("╔════════════════════════════════════════════════════════════════════════╗", "║                            A I R O U T E R                             ║", "║                    AI ROUTER OPERATING SYSTEM                          ║", "║                         AInterceptor Project                            ║", "╚════════════════════════════════════════════════════════════════════════╝"))


def bootstrap() -> str:
    info = system_info()
    cfg = load_startup_config()
    lines = [f"AIRouter Software, Version {__version__}", "AI ROUTER OPERATING SYSTEM", "Copyright (c) 2026 AInterceptor Project", "", "Subsystem status:", "  CLI control plane                  PASS", "  Provider registry                  PASS" if all(runtime_available(p.name) for p in PROVIDERS) else "  Provider registry                  DEGRADED", "  Interceptor runtimes               " + ("PASS" if all(runtime_available(p.name) for p in PROVIDERS) else "DEGRADED"), "  Gateway                            SCAFFOLD", "  Orchestrator                       SCAFFOLD", "  Session/NVRAM store                READY", "  Model registry                     READY", "  Usage/Credit engine                NOT IMPLEMENTED", "", "Hardware:"]
    lines.extend(f"  {key.title():<10}: {value}" for key, value in info.items())
    lines.extend(("", f"  Startup config : {STARTUP_CONFIG}", f"  Config register: {cfg.get('config_register', '0x2102')}"))
    lines.append("")
    lines.append("Self-tests:")
    lines.extend(f"  {name:<30} {status}" for name, status in self_tests())
    return "\n".join(lines)


def providers_status() -> str:
    lines = ["AI Providers", RULE, "  ID                 STATUS              RUNTIME / SESSION"]
    for item in PROVIDERS:
        status = provider_status(item.name)
        session = provider_session_status(item.name)
        runtime = "AVAILABLE" if runtime_available(item.name) else "UNAVAILABLE"
        marker = "●" if status == "CONFIGURED" else "○"
        lines.append(f"  {item.name:<18} {marker} {status:<18} {runtime} / {session}")
    return "\n".join(lines)


def provider_status_view(provider: str) -> str:
    item = next((p for p in PROVIDERS if p.name == provider), None)
    if item is None:
        return f"% Unknown provider: {provider}"
    storage = f".ainterceptor/{provider}/storage_state.json"
    return "\n".join((f"Provider:     {item.display_name}", f"Status:       {provider_status(provider)}", f"Runtime:      {'AVAILABLE' if runtime_available(provider) else 'UNAVAILABLE'}", f"Session:      {provider_session_status(provider)}", f"Storage:      {storage}", f"Transport:    {item.transport_kind}", f"Capabilities: {', '.join(item.capabilities)}", f"Runtime Path: {item.runtime_path}"))


def system_status() -> str:
    info = system_info()
    interceptor = "READY" if all(runtime_available(p.name) for p in PROVIDERS) else "DEGRADED"
    return "\n".join(("System Status", RULE, "  CLI Control Plane      READY", "  Gateway                SCAFFOLD", "  Orchestrator           SCAFFOLD", f"  Interceptor            {interceptor}", "  Session/NVRAM Manager  READY", "  Model Registry         READY", "  Usage/Credit Engine    NOT IMPLEMENTED", f"  Hostname               {info['hostname']}", f"  OS                     {info['os']}", f"  CPU                    {info['cpu']}", f"  Memory                 {info['memory']}", f"  Python                 {info['python']}"))


def version_view() -> str:
    cfg = load_startup_config()
    return "\n".join((f"AIRouter Software, Version {__version__}", "AIRouter NOS control plane", "AInterceptor web-layer AI routing project", f"Configuration register: {cfg.get('config_register', '0x2102')}", f"Startup configuration: {STARTUP_CONFIG}", "Boot source: persistent startup configuration"))


def system_view() -> str:
    return "\n".join(f"{key:<12}: {value}" for key, value in system_info().items())


def models_view(provider: str | None = None) -> str:
    models = model_definitions(provider)
    cfg = load_startup_config()
    selected = cfg.get("ai", {}).get("selected_model")
    title = "Model Registry" if provider is None else f"Model Registry — {provider}"
    lines = [title, RULE, f"  Selected policy: {selected or 'none'}", "  ID                              Provider       Status"]
    for item in models:
        active = "SELECTED" if item.model_id == selected else "CATALOG"
        lines.append(f"  {item.model_id:<31} {item.provider:<14} {active}")
    lines.append("")
    lines.append("  CATALOG = known model metadata; WEB availability is session-discovered.")
    return "\n".join(lines)


def model_help(provider: str | None = None) -> str:
    return "\n".join(["Available model candidates:"] + [f"  {item.model_id:<31} {item.display_name}" for item in model_definitions(provider)])


def routes_view() -> str:
    routes = load_startup_config().get("ai", {}).get("routes", {})
    lines = ["AI Routing Table", RULE]
    if not routes:
        lines.append("  No routing policies configured.")
    else:
        for name, value in routes.items():
            lines.append(f"  route {name} -> {value}")
    return "\n".join(lines)


def sessions_view() -> str:
    lines = ["Session Manager", RULE, "  PROVIDER           SESSION             STORAGE"]
    for item in PROVIDERS:
        lines.append(f"  {item.name:<18} {provider_session_status(item.name):<19} .ainterceptor/{item.name}/storage_state.json")
    return "\n".join(lines)


def counters_view(counters: dict[str, int]) -> str:
    return "\n".join(("AI Request Counters", RULE, f"  Requests    : {counters['requests']}", f"  Success     : {counters['success']}", f"  Failed      : {counters['failed']}", f"  Fallbacks   : {counters['fallbacks']}"))


def credits_view() -> str:
    return "\n".join(("AI Credit Ledger", RULE, "  Provider credit/balance collection: NOT IMPLEMENTED", "  No fabricated balances are displayed."))


def health_view() -> str:
    lines = ["AIRouter Health", RULE]
    for item in PROVIDERS:
        lines.append(f"  {item.name:<18} runtime={'UP' if runtime_available(item.name) else 'DOWN':<4} session={provider_session_status(item.name)}")
    return "\n".join(lines)


def boot_view() -> str:
    cfg = load_startup_config()
    return "\n".join(("Boot Variables", RULE, f"  CONFIG_FILE      {cfg.get('boot', {}).get('config_file', 'nvram:startup-config.json')}", f"  CONFIG_REGISTER  {cfg.get('config_register', '0x2102')}", f"  STARTUP_CONFIG   {STARTUP_CONFIG}", "  BOOT_SOURCE      persistent NVRAM configuration"))


def help_view(mode: str) -> str:
    if mode == "user-exec":
        return "\n".join(("User EXEC commands:", "  enable                 Enter privileged EXEC mode", "  show ?                 Show available show commands", "  chat <provider>        Enter persistent provider chat", "  airouter               Re-display NOS banner", "  logout                 Exit the console", "  ?                      Show this help"))
    if mode == "privileged-exec":
        return "\n".join(("Privileged EXEC commands:", "  show <topic>            Show operational state", "  configure terminal      Enter global configuration", "  copy running-config startup-config   Save running config", "  write memory            Save running config", "  clear counters          Clear in-memory counters", "  disable                 Return to user EXEC", "  exit                    Exit the console", "  ?                       Show this help"))
    if mode == "config":
        return "\n".join(("Global configuration commands:", "  ai                      Enter AI subsystem configuration", "  exit                    Return to privileged EXEC", "  end                     Return to privileged EXEC", "  ?                       Show this help"))
    if mode == "config-ai":
        return "\n".join(("AI subsystem configuration commands:", "  provider <name>         Configure a provider", "  model <name>            Select a model", "  route <name>            Configure routing policy", "  prompt <name>           Configure prompt profile", "  session                 Configure session policy", "  api                     Configure application API clients", "  exit                    Return to global configuration"))
    if mode == "config-ai-provider":
        return "\n".join(("AI provider configuration commands:", "  enable                  Enable provider in routing policy", "  disable                 Disable provider in routing policy", "  login                   Enter provider authentication workflow", "  logout                  End provider session", "  session                 Show provider session", "  model                   Show provider models", "  health                  Show provider health", "  exit                    Return to AI configuration"))
    return "Type ? for commands."
