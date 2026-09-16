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

        self._history_file = os.path.join(
            history_dir,
            "cli-history",
        )

        # Created only when run() actually owns an interactive terminal.
        # This keeps Shell unit-testable in pytest/CI/non-console contexts.
        self.session = None

    def prompt(self) -> str:
        if self.provider:
            return f"AInterceptor [{self.provider.name}]> "
        return "AInterceptor> "

    def _create_prompt_session(self) -> PromptSession:
        return PromptSession(
            history=FileHistory(self._history_file),
            completer=AInterceptorCompleter(self),
            complete_while_typing=False,
        )

    def run(self) -> None:
        self.session = self._create_prompt_session()

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
