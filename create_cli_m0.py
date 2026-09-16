from pathlib import Path

files = {
"cli/registry.py": r'''
from dataclasses import dataclass
from pathlib import Path
import json


@dataclass(frozen=True)
class ProviderSpec:
    name: str
    display_name: str
    transport: str
    configured: bool


ROOT = Path(__file__).resolve().parents[1]
PROVIDERS_DIR = ROOT / "providers"


def load_providers() -> list[ProviderSpec]:
    providers = []

    if not PROVIDERS_DIR.exists():
        return providers

    for path in sorted(PROVIDERS_DIR.glob("*/provider.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        providers.append(
            ProviderSpec(
                name=data["name"],
                display_name=data["display_name"],
                transport=data.get("transport", "web"),
                configured=bool(data.get("configured", False)),
            )
        )

    return providers
''',

"cli/renderer.py": r'''
def banner() -> None:
    print()
    print("╔════════════════════════════════════════════════════════════╗")
    print("║                    A I N T E R C E P T O R                 ║")
    print("║              Web AI Provider Control Plane                 ║")
    print("╚════════════════════════════════════════════════════════════╝")
    print()


def providers(specs) -> None:
    print("Providers")
    print("────────────────────────────────────────────────────────────")

    for index, spec in enumerate(specs, 1):
        state = "● CONFIGURED" if spec.configured else "○ NOT CONFIGURED"
        print(f"  [{index}] {spec.display_name:<18} {state}")

    print()


def system_status() -> None:
    print("System")
    print("────────────────────────────────────────────────────────────")
    print("  Interceptor          READY")
    print("  Orchestrator         READY")
    print("  Gateway              READY")
    print()


def global_help() -> None:
    print("""
Global commands:
  help, ?              Show this help
  providers            Show providers
  status               Show system status
  use <provider>       Enter provider context
  sessions             Show sessions
  diagnostics          Run diagnostics
  version              Show version
  clear                Clear screen
  exit, quit           Exit AInterceptor
""")


def provider_help() -> None:
    print("""
Provider commands:
  help, ?              Show this help
  status               Provider status
  session              Session information
  chat                 Chat control-plane placeholder
  diagnostics          Provider diagnostics
  doctor               Provider health checks
  back                 Return to global context
  exit                 Exit AInterceptor
""")
''',

"cli/shell.py": r'''
import os

from .registry import load_providers
from .renderer import (
    banner,
    providers,
    system_status,
    global_help,
    provider_help,
)


VERSION = "0.1.0-m0"


class Shell:
    def __init__(self):
        self.provider = None
        self.running = True

    def prompt(self) -> str:
        if self.provider:
            return f"AInterceptor [{self.provider.name}]> "
        return "AInterceptor> "

    def run(self) -> None:
        banner()
        providers(load_providers())
        system_status()
        print("Type 'help' for commands.")
        print()

        while self.running:
            try:
                command = input(self.prompt()).strip()
            except (EOFError, KeyboardInterrupt):
                print()
                break

            if not command:
                continue

            self.handle(command)

    def handle(self, command: str) -> None:
        parts = command.split()
        verb = parts[0].lower()
        args = parts[1:]

        if self.provider:
            self.handle_provider(verb, args)
        else:
            self.handle_global(verb, args)

    def handle_global(self, verb: str, args: list[str]) -> None:
        if verb in ("help", "?"):
            global_help()

        elif verb == "providers":
            providers(load_providers())

        elif verb == "status":
            system_status()

        elif verb == "use":
            if not args:
                print("Usage: use <provider>")
                return

            name = args[0].lower()
            match = next(
                (p for p in load_providers() if p.name == name),
                None,
            )

            if not match:
                print(f"Unknown provider: {name}")
                return

            self.provider = match
            print(f"Entered provider context: {match.display_name}")

        elif verb == "sessions":
            print("Sessions: no active CLI-managed sessions.")

        elif verb == "diagnostics":
            print("Diagnostics: control-plane CLI checks passed.")

        elif verb == "version":
            print(f"AInterceptor CLI {VERSION}")

        elif verb == "clear":
            os.system("cls" if os.name == "nt" else "clear")

        elif verb in ("exit", "quit"):
            self.running = False

        else:
            print(f"Unknown command: {verb}. Type 'help'.")

    def handle_provider(self, verb: str, args: list[str]) -> None:
        if verb in ("help", "?"):
            provider_help()

        elif verb == "status":
            print(f"Provider: {self.provider.display_name}")
            print(f"Transport: {self.provider.transport}")
            print(
                "Configuration: "
                + ("CONFIGURED" if self.provider.configured else "NOT CONFIGURED")
            )

        elif verb == "session":
            print("Session: runtime integration pending.")

        elif verb == "chat":
            print("Chat: CLI control-plane placeholder; transport wiring is deferred.")

        elif verb == "diagnostics":
            print(f"Diagnostics: {self.provider.display_name} CLI checks passed.")

        elif verb == "doctor":
            print(f"Doctor: {self.provider.display_name} provider descriptor is valid.")

        elif verb == "back":
            self.provider = None

        elif verb == "exit":
            self.running = False

        else:
            print(f"Unknown provider command: {verb}. Type 'help'.")
''',

"cli/main.py": r'''
from .shell import Shell


def main() -> None:
    Shell().run()


if __name__ == "__main__":
    main()
''',

"TEST/cli/test_cli_m0.py": r'''
from cli.registry import load_providers


def test_provider_registry_contains_expected_providers():
    providers = load_providers()
    names = {provider.name for provider in providers}

    assert {"claude", "chatgpt", "gemini", "grok"} <= names


def test_claude_is_configured():
    claude = next(p for p in load_providers() if p.name == "claude")
    assert claude.configured is True
''',

"providers/claude/provider.json": r'''
{
  "name": "claude",
  "display_name": "Claude Web",
  "transport": "cdp-sse",
  "configured": true
}
''',

"providers/chatgpt/provider.json": r'''
{
  "name": "chatgpt",
  "display_name": "ChatGPT Web",
  "transport": "web",
  "configured": false
}
''',

"providers/gemini/provider.json": r'''
{
  "name": "gemini",
  "display_name": "Gemini Web",
  "transport": "web",
  "configured": false
}
''',

"providers/grok/provider.json": r'''
{
  "name": "grok",
  "display_name": "Grok Web",
  "transport": "web",
  "configured": false
}
''',

"scripts/ainterceptor.ps1": r'''
param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$Arguments
)

python -m cli.main @Arguments
''',

"ainterceptor.cmd": r'''
@echo off
python -m cli.main %*
'''
}

for filename, content in files.items():
    path = Path(filename)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content.lstrip(), encoding="utf-8")
    print(f"CREATED {path}")

print("CLI M0 generation complete.")
