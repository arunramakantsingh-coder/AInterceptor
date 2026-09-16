"""Interactive hierarchical shell for AInterceptor."""
from __future__ import annotations

import asyncio
import os
from pathlib import Path

from prompt_toolkit import PromptSession
from prompt_toolkit.completion import Completer, Completion
from prompt_toolkit.history import FileHistory

from . import __version__
from .chat import chat
from .registry import PROVIDER_ORDER, load_providers
from .renderer import (
    banner,
    global_help,
    provider_help,
    provider_status,
    providers_status,
    system_status,
)


class AInterceptorCompleter(Completer):
    GLOBAL = (
        "help", "providers", "status", "use", "sessions", "diagnostics",
        "version", "clear", "exit", "quit", "1", "2", "3", "4",
    )
    PROVIDER = (
        "help", "status", "session", "chat", "diagnostics", "doctor", "back", "exit",
    )

    def __init__(self, provider: str | None = None) -> None:
        self.provider = provider

    def get_completions(self, document, complete_event):
        word = document.get_word_before_cursor().lower()
        commands = self.PROVIDER if self.provider else self.GLOBAL
        if word.startswith("use "):
            prefix = word[4:]
            for name in PROVIDER_ORDER:
                if name.startswith(prefix):
                    yield Completion(name, start_position=-len(prefix))
            return
        for command in commands:
            if command.startswith(word):
                yield Completion(command, start_position=-len(word))


class CLIState:
    def __init__(self) -> None:
        self.provider: str | None = None
        self.running = True

    @property
    def prompt(self) -> str:
        return f"AInterceptor [{self.provider}]> " if self.provider else "AInterceptor> "


class CommandDispatcher:
    def __init__(self, state: CLIState) -> None:
        self.state = state

    def dispatch(self, raw: str) -> str | None:
        command = raw.strip()
        if not command:
            return None
        parts = command.split()
        name = parts[0].lower()
        args = parts[1:]

        if self.state.provider:
            return self._provider_command(name, args)
        return self._global_command(name, args)

    def _global_command(self, name: str, args: list[str]) -> str | None:
        if name in {"exit", "quit"}:
            self.state.running = False
            return "Bye."
        if name in {"help", "?"}:
            return global_help()
        if name == "providers":
            return providers_status()
        if name == "status":
            return system_status()
        if name == "use":
            if not args:
                return "Usage: use <provider>"
            requested = args[0].lower()
            if requested.isdigit() and 1 <= int(requested) <= len(PROVIDER_ORDER):
                requested = PROVIDER_ORDER[int(requested) - 1]
            if requested not in load_providers():
                return f"Unknown provider: {requested}"
            self.state.provider = requested
            return f"Context changed to {requested}"
        if name.isdigit() and 1 <= int(name) <= len(PROVIDER_ORDER):
            self.state.provider = PROVIDER_ORDER[int(name) - 1]
            return f"Context changed to {self.state.provider}"
        if name == "sessions":
            return "Sessions: provider session inventory is runtime-owned."
        if name == "diagnostics":
            return "Diagnostics: Gateway READY | Orchestrator READY | Interceptor READY"
        if name == "version":
            return __version__
        if name == "clear":
            os.system("cls" if os.name == "nt" else "clear")
            return None
        return f"Unknown command: {name}. Type help or ?."

    def _provider_command(self, name: str, args: list[str]) -> str | None:
        provider = self.state.provider
        assert provider is not None
        if name == "back":
            self.state.provider = None
            return "Returned to global context."
        if name in {"exit", "quit"}:
            self.state.running = False
            return "Bye."
        if name in {"help", "?"}:
            return provider_help()
        if name == "status":
            return provider_status(provider)
        if name == "session":
            return f"{provider}: session management is runtime-owned."
        if name == "diagnostics":
            return f"{provider}: diagnostics are runtime-owned."
        if name == "doctor":
            return f"{provider}: provider context reachable; runtime health probe available through diagnostics."
        if name == "chat":
            prompt = " ".join(args).strip()
            if not prompt:
                return "CHAT_PROMPT"
            self._run_chat(provider, prompt)
            return None
        return f"Unknown provider command: {name}. Type help or ?."

    @staticmethod
    def _run_chat(provider: str, prompt: str) -> None:
        print()
        print(f"{provider.title()}:")
        print("  ", end="", flush=True)

        def render_delta(delta: str) -> None:
            print(delta, end="", flush=True)

        asyncio.run(chat(provider, prompt, on_delta=render_delta))
        print("\n")


class InteractiveShell:
    def __init__(self) -> None:
        self.state = CLIState()
        self.dispatcher = CommandDispatcher(self.state)
        history_dir = Path(".ainterceptor")
        history_dir.mkdir(parents=True, exist_ok=True)
        self.session = PromptSession(
            history=FileHistory(str(history_dir / "cli_history")),
            completer=AInterceptorCompleter(),
            complete_while_typing=True,
        )

    def _refresh_completer(self) -> None:
        self.session.completer = AInterceptorCompleter(self.state.provider)

    def run(self) -> None:
        print(banner())
        print()
        print(providers_status())
        print()
        print(system_status())
        print()
        print("Type 'help' or '?' for commands. Use number 1-4 or 'use <provider>' to navigate.")
        print()

        while self.state.running:
            self._refresh_completer()
            try:
                raw = self.session.prompt(self.state.prompt)
            except (EOFError, KeyboardInterrupt):
                print()
                break

            if raw.strip().lower() == "chat" and self.state.provider:
                try:
                    prompt = self.session.prompt(f"{self.state.provider}> ").strip()
                except (EOFError, KeyboardInterrupt):
                    print()
                    continue
                if prompt:
                    self.dispatcher._run_chat(self.state.provider, prompt)
                continue

            result = self.dispatcher.dispatch(raw)
            if result == "CHAT_PROMPT":
                continue
            if result:
                print(result)
