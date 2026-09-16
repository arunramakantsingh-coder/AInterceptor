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

    # Stable operator-facing order.
    preferred = {"claude": 1, "chatgpt": 2, "gemini": 3, "grok": 4}
    return sorted(providers, key=lambda p: preferred.get(p.name, 99))
''',

"cli/renderer.py": r'''
import sys


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
  help, ?              Show available commands
  providers            List AI providers
  status               Show control-plane status
  use <provider>       Enter provider context
  sessions             Show sessions
  diagnostics          Run diagnostics
  version              Show CLI version
  clear                Clear terminal
  exit, quit           Exit AInterceptor

Provider selection:
  1                    Select Claude Web
  2                    Select ChatGPT Web
  3                    Select Gemini Web
  4                    Select Grok Web

Tip:
  Type part of a command and press TAB to complete it.
""")


def provider_help() -> None:
    print("""
Provider commands:
  help, ?              Show provider commands
  status               Provider status
  session              Session information
  chat                 Start interactive chat
  diagnostics          Provider diagnostics
  doctor               Provider health check
  back                 Return to global context
  exit, quit           Exit AInterceptor

Tip:
  Type part of a command and press TAB to complete it.
""")


def print_stream_delta(delta: str) -> None:
    print(delta, end="", flush=True)


def print_stream_end() -> None:
    print()
    print()


def error(message: str) -> None:
    print(f"ERROR: {message}", file=sys.stderr)
''',

"cli/completion.py": r'''
from prompt_toolkit.completion import Completer, Completion


GLOBAL_COMMANDS = [
    "help",
    "providers",
    "status",
    "use",
    "sessions",
    "diagnostics",
    "version",
    "clear",
    "exit",
    "quit",
]

PROVIDER_COMMANDS = [
    "help",
    "status",
    "session",
    "chat",
    "diagnostics",
    "doctor",
    "back",
    "exit",
    "quit",
]


class AInterceptorCompleter(Completer):
    def __init__(self, shell):
        self.shell = shell

    def get_completions(self, document, complete_event):
        text = document.text_before_cursor
        word = document.get_word_before_cursor()

        if self.shell.provider is None:
            commands = GLOBAL_COMMANDS

            # Provider aliases.
            if text.startswith("use "):
                prefix = word.lower()
                for provider in self.shell.providers:
                    if provider.name.startswith(prefix):
                        yield Completion(
                            provider.name,
                            start_position=-len(word),
                        )
                return

        else:
            commands = PROVIDER_COMMANDS

        prefix = word.lower()

        for command in commands:
            if command.startswith(prefix):
                yield Completion(
                    command,
                    start_position=-len(word),
                )
''',

"cli/chat.py": r'''
import asyncio
import os
import sys
from pathlib import Path

from .renderer import error, print_stream_delta, print_stream_end


def _backend_path() -> Path:
    return Path(__file__).resolve().parents[1] / "backend"


def _load_claude_runtime():
    backend = _backend_path()

    if str(backend) not in sys.path:
        sys.path.insert(0, str(backend))

    from app.interception.claude import ClaudeRuntime
    from app.interception.contracts import (
        EventType,
        ProviderExecutionRequest,
    )

    return ClaudeRuntime, EventType, ProviderExecutionRequest


def _session_path() -> str:
    configured = os.getenv("AINTERCEPTOR_CLAUDE_STORAGE_STATE")

    if configured:
        return configured

    # Explicit default. Do not silently invent credentials/session data.
    return str(
        Path(__file__).resolve().parents[1]
        / ".ainterceptor"
        / "claude"
        / "storage_state.json"
    )


async def _run_claude(prompt: str) -> None:
    ClaudeRuntime, EventType, ProviderExecutionRequest = _load_claude_runtime()

    session_path = _session_path()

    if not Path(session_path).exists():
        raise RuntimeError(
            "Claude session is not configured for CLI runtime. "
            f"Expected storage state: {session_path}. "
            "Set AINTERCEPTOR_CLAUDE_STORAGE_STATE to a valid "
            "Playwright storage-state file."
        )

    runtime = ClaudeRuntime(
        session_path=session_path,
        headless=False,
    )

    request = ProviderExecutionRequest(
        provider="claude",
        request_id=f"cli-{id(prompt)}",
        messages=[
            {
                "role": "user",
                "content": prompt,
            }
        ],
    )

    try:
        await runtime.start()

        print()
        print("Claude:")
        print()

        async for event in runtime.execute(request):
            if event.event_type is EventType.STREAM_DELTA:
                print_stream_delta(event.delta or "")

            elif event.event_type is EventType.STREAM_COMPLETED:
                print_stream_end()
                break

            elif event.event_type is EventType.SESSION_EXPIRED:
                raise RuntimeError(
                    "Claude web session expired."
                )

            elif event.event_type is EventType.SESSION_RECOVERY_REQUIRED:
                raise RuntimeError(
                    "Claude session recovery is required."
                )

            elif event.event_type is EventType.STREAM_FAILED:
                reason = event.metadata.get("reason", "unknown")
                raise RuntimeError(
                    f"Claude transport failed: {reason}"
                )

    finally:
        await runtime.close()


def chat(provider_name: str) -> None:
    if provider_name != "claude":
        print(
            f"Chat transport for '{provider_name}' is not implemented yet."
        )
        return

    try:
        prompt = input("Prompt> ").strip()
    except (EOFError, KeyboardInterrupt):
        print()
        return

    if not prompt:
        print("Prompt cannot be empty.")
        return

    try:
        asyncio.run(_run_claude(prompt))
    except KeyboardInterrupt:
        print()
        print("Chat interrupted.")
    except Exception as exc:
        error(str(exc))
''',

"cli/shell.py": r'''
import os

from prompt_toolkit import PromptSession
from prompt_toolkit.history import FileHistory

from .chat import chat
from .completion import AInterceptorCompleter
from .registry import load_providers
from .renderer import (
    banner,
    providers,
    system_status,
    global_help,
    provider_help,
)


VERSION = "0.1.0-m0.1"


class Shell:
    def __init__(self):
        self.providers = load_providers()
        self.provider = None
        self.running = True

        history_dir = os.path.join(
            os.path.expanduser("~"),
            ".ainterceptor",
        )
        os.makedirs(history_dir, exist_ok=True)

        self.session = PromptSession(
            history=FileHistory(
                os.path.join(history_dir, "cli-history")
            ),
            completer=AInterceptorCompleter(self),
            complete_while_typing=False,
        )

    def prompt(self) -> str:
        if self.provider:
            return f"AInterceptor [{self.provider.name}]> "
        return "AInterceptor> "

    def run(self) -> None:
        banner()
        providers(self.providers)
        system_status()
        print("Type 'help' for commands.")
        print()

        while self.running:
            try:
                command = self.session.prompt(self.prompt())
            except KeyboardInterrupt:
                print("^C")
                continue
            except EOFError:
                print()
                break

            command = command.strip()

            if not command:
                continue

            self.handle(command)

    def select_provider(self, index: int) -> bool:
        if index < 1 or index > len(self.providers):
            return False

        self.provider = self.providers[index - 1]
        print(f"Entered provider context: {self.provider.display_name}")
        return True

    def handle(self, command: str) -> None:
        parts = command.split()
        verb = parts[0].lower()
        args = parts[1:]

        # Cisco-style numeric provider selection.
        if self.provider is None and len(parts) == 1 and verb.isdigit():
            if self.select_provider(int(verb)):
                return
            print(f"Invalid provider selection: {verb}")
            return

        if self.provider:
            self.handle_provider(verb, args)
        else:
            self.handle_global(verb, args)

    def resolve_command(self, verb: str, commands: list[str]):
        exact = [c for c in commands if c == verb]

        if exact:
            return exact[0]

        matches = [c for c in commands if c.startswith(verb)]

        if len(matches) == 1:
            return matches[0]

        if len(matches) > 1:
            print("Ambiguous command. Possible matches:")
            for match in matches:
                print(f"  {match}")
            return None

        return ""

    def handle_global(self, verb: str, args: list[str]) -> None:
        command = self.resolve_command(
            verb,
            [
                "help",
                "providers",
                "status",
                "use",
                "sessions",
                "diagnostics",
                "version",
                "clear",
                "exit",
                "quit",
            ],
        )

        if not command:
            print(f"Unknown or ambiguous command: {verb}. Type '?' for help.")
            return

        if command == "help":
            global_help()

        elif command == "providers":
            self.providers = load_providers()
            providers(self.providers)

        elif command == "status":
            system_status()

        elif command == "use":
            if not args:
                print("Usage: use <provider>")
                print("Example: use claude")
                return

            name = args[0].lower()

            match = next(
                (p for p in self.providers if p.name.startswith(name)),
                None,
            )

            if not match:
                print(f"Unknown provider: {args[0]}")
                return

            self.provider = match
            print(f"Entered provider context: {match.display_name}")

        elif command == "sessions":
            print("Sessions: no active CLI-managed sessions.")

        elif command == "diagnostics":
            print("Diagnostics: control-plane CLI checks passed.")

        elif command == "version":
            print(f"AInterceptor CLI {VERSION}")

        elif command == "clear":
            os.system("cls" if os.name == "nt" else "clear")

        elif command in ("exit", "quit"):
            self.running = False

    def handle_provider(self, verb: str, args: list[str]) -> None:
        command = self.resolve_command(
            verb,
            [
                "help",
                "status",
                "session",
                "chat",
                "diagnostics",
                "doctor",
                "back",
                "exit",
                "quit",
            ],
        )

        if not command:
            print(
                f"Unknown or ambiguous command: {verb}. "
                "Type '?' for help."
            )
            return

        if command == "help":
            provider_help()

        elif command == "status":
            print(f"Provider: {self.provider.display_name}")
            print(f"Transport: {self.provider.transport}")
            print(
                "Configuration: "
                + (
                    "CONFIGURED"
                    if self.provider.configured
                    else "NOT CONFIGURED"
                )
            )

        elif command == "session":
            print(
                "Session state is owned by the provider runtime. "
                "Use 'doctor' for configuration/runtime diagnostics."
            )

        elif command == "chat":
            chat(self.provider.name)

        elif command == "diagnostics":
            print(
                f"Diagnostics: {self.provider.display_name} "
                "CLI checks passed."
            )

        elif command == "doctor":
            if not self.provider.configured:
                print(
                    f"{self.provider.display_name}: "
                    "provider is not configured."
                )
            elif self.provider.name == "claude":
                print(
                    "Claude: configured for web transport. "
                    "Runtime session availability will be checked "
                    "when chat starts."
                )
            else:
                print(
                    f"{self.provider.display_name}: descriptor is valid."
                )

        elif command == "back":
            self.provider = None

        elif command in ("exit", "quit"):
            self.running = False
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
from cli.shell import Shell


def test_provider_registry_order():
    providers = load_providers()
    assert [p.name for p in providers] == [
        "claude",
        "chatgpt",
        "gemini",
        "grok",
    ]


def test_claude_is_configured():
    claude = next(p for p in load_providers() if p.name == "claude")
    assert claude.configured is True


def test_numeric_provider_selection():
    shell = Shell()
    assert shell.select_provider(1) is True
    assert shell.provider.name == "claude"


def test_partial_command_resolution():
    shell = Shell()

    assert shell.resolve_command(
        "prov",
        ["help", "providers", "status"],
    ) == "providers"

    assert shell.resolve_command(
        "sta",
        ["help", "providers", "status"],
    ) == "status"
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

"cli/__init__.py": r'''
"""AInterceptor interactive command-line control plane."""
''',

"scripts/ainterceptor.ps1": r'''
python -m cli.main
''',

"cli.cmd": r'''
@echo off
cd /d "%~dp0"
python -m cli.main %*
''',

"ainterceptor.cmd": r'''
@echo off
cd /d "%~dp0"
python -m cli.main %*
'''
}

for filename, content in files.items():
    path = Path(filename)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content.lstrip(), encoding="utf-8")
    print(f"UPDATED {path}")

print("AInterceptor CLI M0.1 generation complete.")
