"""Cisco-style AIRouter NOS interactive shell.

The shell is a control-plane UI. It never owns provider transport/session
mechanics; those remain in the Interceptor subsystem.
"""
from __future__ import annotations

import asyncio
from pathlib import Path

from prompt_toolkit import PromptSession
from prompt_toolkit.completion import Completer, Completion
from prompt_toolkit.history import FileHistory

from .chat import chat
from .nos import (
    Mode,
    NOSState,
    PROVIDERS,
    model_definition,
    model_definitions,
    prefix_matches,
    provider_definition,
    unique_prefix,
)
from .renderer import (
    banner,
    boot_console,
    bootstrap,
    counters_view,
    credits_view,
    help_view,
    model_help,
    models_view,
    provider_status_view,
    providers_status,
    routes_view,
    sessions_view,
    system_status,
    system_view,
    version_view,
)


SHOW_TOPICS = (
    "version", "system", "ai", "providers", "models", "routes",
    "sessions", "counters", "credits", "health",
)
SHOW_AI_TOPICS = (
    "providers", "models", "routes", "sessions", "usage", "credits",
    "prompts", "health",
)


class AIRouterCompleter(Completer):
    """Completion is explicit: Tab completes, typing alone does not open a menu."""

    COMMANDS = {
        Mode.BOOT: ("bootai", "airouter", "exit", "logout", "quit", "?"),
        Mode.USER_EXEC: ("enable", "show", "chat", "airouter", "logout", "exit", "?"),
        Mode.PRIVILEGED_EXEC: (
            "show", "chat", "configure", "clear", "disable", "exit", "logout", "?",
        ),
        Mode.CONFIG: ("ai", "exit", "end", "?"),
        Mode.CONFIG_AI: (
            "provider", "model", "route", "prompt", "session", "api", "exit", "end", "?",
        ),
        Mode.CONFIG_AI_PROVIDER: (
            "enable", "disable", "login", "logout", "session", "model", "health", "exit", "end", "?",
        ),
    }

    def __init__(self, state: NOSState) -> None:
        self.state = state

    def get_completions(self, document, complete_event):
        text = document.text_before_cursor.lower()
        word = document.get_word_before_cursor().lower()
        commands = self.COMMANDS.get(self.state.mode, ())

        if text.startswith("show "):
            topics = SHOW_AI_TOPICS if text.startswith("show ai ") else SHOW_TOPICS
            offset = 8 if text.startswith("show ai ") else 5
            prefix = text[offset:].split()[-1] if text[offset:].strip() else ""
            for item in topics:
                if item.startswith(prefix):
                    yield Completion(item, start_position=-len(prefix))
            return

        if text.startswith("chat "):
            prefix = text[5:].split()[-1] if text[5:].strip() else ""
            for item in (p.name for p in PROVIDERS):
                if item.startswith(prefix):
                    yield Completion(item, start_position=-len(prefix))
            return

        if text.startswith("provider ") and self.state.mode == Mode.CONFIG_AI:
            prefix = text[9:].split()[-1] if text[9:].strip() else ""
            for item in (p.name for p in PROVIDERS):
                if item.startswith(prefix):
                    yield Completion(item, start_position=-len(prefix))
            return

        if text.startswith("model ") and self.state.mode == Mode.CONFIG_AI:
            prefix = text[6:].split()[-1] if text[6:].strip() else ""
            for item in (m.model_id for m in model_definitions()):
                if item.startswith(prefix):
                    yield Completion(item, start_position=-len(prefix))
            return

        for command in commands:
            if command.startswith(word):
                yield Completion(command, start_position=-len(word))


class AIRouterShell:
    def __init__(self) -> None:
        self.state = NOSState()
        history_dir = Path(".ainterceptor")
        history_dir.mkdir(parents=True, exist_ok=True)
        history = FileHistory(str(history_dir / "cli_history"))
        self.session = PromptSession(
            history=history,
            completer=AIRouterCompleter(self.state),
            complete_while_typing=False,
        )
        self.chat_session = PromptSession(history=history, completer=None)

    @property
    def prompt(self) -> str:
        if self.state.mode == Mode.BOOT:
            return "AInterceptor-BOOT> "
        if self.state.mode == Mode.USER_EXEC:
            return "AIRouter> "
        if self.state.mode == Mode.PRIVILEGED_EXEC:
            return "AIRouter# "
        if self.state.mode == Mode.CONFIG:
            return "AIRouter(config)# "
        if self.state.mode == Mode.CONFIG_AI:
            return "AIRouter(config-ai)# "
        if self.state.mode == Mode.CONFIG_AI_PROVIDER:
            name = self.state.provider or "provider"
            return f"AIRouter(config-ai-provider-{name})# "
        return "AIRouter(chat)> "

    def _set_mode(self, mode: Mode) -> None:
        self.state.mode = mode
        self.session.completer = AIRouterCompleter(self.state)

    @staticmethod
    def _resolve(token: str, candidates: tuple[str, ...] | list[str]) -> str | None:
        exact = next((item for item in candidates if item.lower() == token.lower()), None)
        if exact:
            return exact
        return unique_prefix(token, candidates)

    @staticmethod
    def _prefix_help(prefix: str, candidates: tuple[str, ...] | list[str]) -> str:
        matches = prefix_matches(prefix, candidates)
        if not matches:
            return ""
        return "\n".join(f"  {item}" for item in matches)

    def _show(self, args: list[str]) -> str:
        if not args:
            return system_status()
        topic = self._resolve(args[0], SHOW_TOPICS)
        if topic == "version":
            return version_view()
        if topic == "system":
            return system_view()
        if topic == "ai":
            subtopic = self._resolve(args[1], SHOW_AI_TOPICS) if len(args) > 1 else None
            if subtopic in {"providers", "provider"}:
                return providers_status()
            if subtopic == "models":
                return models_view()
            if subtopic == "routes":
                return routes_view()
            if subtopic == "sessions":
                return sessions_view()
            if subtopic in {"usage", "counters"}:
                return counters_view(self.state.counters)
            if subtopic == "credits":
                return credits_view()
            return system_status()
        if topic == "health":
            return system_status()
        if topic in {"providers", "provider"}:
            return providers_status()
        if topic == "models":
            return models_view()
        if topic == "routes":
            return routes_view()
        if topic == "sessions":
            return sessions_view()
        if topic == "counters":
            return counters_view(self.state.counters)
        if topic == "credits":
            return credits_view()
        return f"% Unknown show topic: {args[0]}. Type show ?."

    def _context_help(self, raw: str) -> bool:
        """Implement Cisco-style `?` syntax; returns True when help was handled."""
        if "?" not in raw:
            return False

        attached = raw.rstrip().endswith("?") and not raw.rstrip().endswith(" ?")
        base = raw.rstrip()[:-1] if attached else raw.rstrip()
        parts = base.split()
        prefix = parts[-1] if attached and parts else ""

        if self.state.mode == Mode.BOOT:
            candidates = ("bootai", "airouter", "exit", "logout", "quit")
            print(self._prefix_help(prefix, candidates) or "  No matching commands.")
            return True

        if not parts:
            print(help_view(self.state.mode.value))
            return True

        first = parts[0].lower()
        commands = AIRouterCompleter.COMMANDS.get(self.state.mode, ())
        resolved_first = self._resolve(first, tuple(c for c in commands if c != "?"))

        if len(parts) == 1 and (first == "?" or not attached and raw.strip() == "?"):
            print(help_view(self.state.mode.value))
            return True

        if attached and len(parts) == 1:
            matches = prefix_matches(prefix, tuple(c for c in commands if c != "?"))
            print("\n".join(f"  {item}" for item in matches) or "  No matching commands.")
            return True

        if resolved_first is None:
            print("  No matching commands.")
            return True

        if resolved_first == "show":
            if len(parts) == 1:
                print("\n".join(f"  {item}" for item in SHOW_TOPICS))
                return True
            if parts[1].lower() == "ai" and len(parts) >= 2:
                prefix2 = parts[2] if len(parts) > 2 else ""
                if attached and len(parts) >= 3:
                    prefix2 = parts[-1]
                print(self._prefix_help(prefix2, SHOW_AI_TOPICS) or "  No matching show ai options.")
                return True
            prefix2 = parts[-1] if attached else ""
            print(self._prefix_help(prefix2, SHOW_TOPICS) or "  No matching show options.")
            return True

        if resolved_first == "configure":
            print("  terminal    Enter configuration from terminal")
            return True

        if resolved_first == "chat":
            print("\n".join(f"  {item}" for item in (p.name for p in PROVIDERS)))
            return True

        if resolved_first == "provider" and self.state.mode == Mode.CONFIG_AI:
            print("\n".join(f"  {item}" for item in (p.name for p in PROVIDERS)))
            return True

        if resolved_first == "model" and self.state.mode == Mode.CONFIG_AI:
            provider = None
            if len(parts) >= 2:
                provider = self._resolve(parts[1], tuple(p.name for p in PROVIDERS))
            print(model_help(provider))
            return True

        return False

    def _chat(self, provider: str, initial_prompt: str | None = None, return_mode: Mode = Mode.PRIVILEGED_EXEC) -> None:
        definition = provider_definition(provider)
        if definition is None:
            print(f"% Unknown provider: {provider}")
            return
        if provider != "claude":
            print(f"% {definition.display_name}: runtime is not implemented yet.")
            print("  Provider-specific runtime will be added behind the common Interceptor contract.")
            return

        self.state.chat_provider = provider
        self._set_mode(Mode.CHAT)
        print(f"\nConnected to {definition.display_name} chat context.")
        print("Type /exit, /back, or press Ctrl+C to return to AIRouter.\n")

        if initial_prompt:
            self._run_chat(provider, initial_prompt)

        while self.state.running and self.state.mode == Mode.CHAT:
            try:
                prompt = self.chat_session.prompt("AIRouter(chat)> ").strip()
            except (EOFError, KeyboardInterrupt):
                print()
                self._set_mode(return_mode)
                break
            if not prompt:
                continue
            if prompt.lower() in {"/exit", "/quit", "/back"}:
                self._set_mode(return_mode)
                print("Returning to AIRouter.")
                break
            self._run_chat(provider, prompt)

    def _run_chat(self, provider: str, prompt: str) -> None:
        try:
            self.state.counters["requests"] += 1
            print(f"\n{provider.title()}:")
            print("  ", end="", flush=True)

            def render_delta(delta: str) -> None:
                print(delta, end="", flush=True)

            asyncio.run(chat(provider, prompt, on_delta=render_delta))
            self.state.counters["success"] += 1
            print("\n")
        except Exception as exc:
            self.state.counters["failed"] += 1
            print(f"\n% {exc}\n")

    def _dispatch_boot(self, name: str, args: list[str]) -> None:
        resolved = self._resolve(name, ("bootai", "airouter", "exit", "logout", "quit"))
        if resolved == "bootai":
            print("\nAInterceptor boot mode ready. Type 'airouter' to initialize the NOS.\n")
            return
        if resolved == "airouter":
            print("\n" + banner())
            print()
            print(bootstrap())
            print(providers_status())
            print()
            print("AIRouter NOS initialized. Type ? for commands.\n")
            self._set_mode(Mode.USER_EXEC)
            return
        if resolved in {"exit", "quit", "logout"}:
            self.state.running = False
            return
        print(f"% Unknown boot command: {name}. Type ?.")

    def _dispatch_exec(self, name: str, args: list[str]) -> None:
        mode = self.state.mode
        commands = tuple(c for c in AIRouterCompleter.COMMANDS[mode] if c != "?")
        resolved = self._resolve(name, commands)
        if resolved is None:
            matches = prefix_matches(name, commands)
            if matches:
                print(f"% Ambiguous command: {name} ({', '.join(matches)})")
            else:
                print(f"% Unknown command: {name}. Type ?. ")
            return
        name = resolved

        if name == "show":
            print(self._show(args))
            return
        if name == "airouter":
            print("\n" + banner())
            return
        if name == "enable" and mode == Mode.USER_EXEC:
            self._set_mode(Mode.PRIVILEGED_EXEC)
            return
        if name == "disable" and mode == Mode.PRIVILEGED_EXEC:
            self._set_mode(Mode.USER_EXEC)
            return
        if name in {"exit", "logout", "quit"}:
            if mode == Mode.USER_EXEC:
                self.state.running = False
            elif mode == Mode.PRIVILEGED_EXEC:
                self._set_mode(Mode.USER_EXEC)
            return
        if name == "configure" and mode == Mode.PRIVILEGED_EXEC:
            if not args:
                print("Usage: configure terminal")
                return
            terminal = self._resolve(args[0], ("terminal",))
            if terminal is None:
                print("% Invalid configure option. Use configure ?")
                return
            print("Enter configuration commands, one per line. End with 'end'.")
            self._set_mode(Mode.CONFIG)
            return
        if name == "clear" and mode == Mode.PRIVILEGED_EXEC:
            if not args or self._resolve(args[0], ("counters",)) is None:
                print("Usage: clear counters")
                return
            for key in self.state.counters:
                self.state.counters[key] = 0
            print("Counters cleared.")
            return
        if name == "chat":
            if not args:
                print("Usage: chat <provider> [initial prompt]")
                return
            provider = self._resolve(args[0], tuple(p.name for p in PROVIDERS))
            if provider is None:
                print(f"% Unknown or ambiguous provider: {args[0]}")
                return
            initial = " ".join(args[1:]) or None
            self._chat(provider, initial, return_mode=mode)
            return

    def _dispatch_config(self, name: str, args: list[str]) -> None:
        commands = tuple(c for c in AIRouterCompleter.COMMANDS[self.state.mode] if c != "?")
        resolved = self._resolve(name, commands)
        if resolved is None:
            matches = prefix_matches(name, commands)
            if matches:
                print(f"% Ambiguous command: {name} ({', '.join(matches)})")
            else:
                print(f"% Unknown command: {name}. Type ?. ")
            return
        name = resolved

        if name == "exit":
            if self.state.mode == Mode.CONFIG:
                self._set_mode(Mode.PRIVILEGED_EXEC)
            elif self.state.mode == Mode.CONFIG_AI:
                self._set_mode(Mode.CONFIG)
            elif self.state.mode == Mode.CONFIG_AI_PROVIDER:
                self._set_mode(Mode.CONFIG_AI)
            return
        if name == "end":
            self._set_mode(Mode.PRIVILEGED_EXEC)
            return
        if self.state.mode == Mode.CONFIG and name == "ai":
            self._set_mode(Mode.CONFIG_AI)
            return
        if self.state.mode == Mode.CONFIG_AI and name == "provider":
            if not args:
                print("Usage: provider <chatgpt|claude|gemini|deepseek>")
                return
            provider = self._resolve(args[0], tuple(p.name for p in PROVIDERS))
            if provider is None:
                print(f"% Unknown or ambiguous provider: {args[0]}")
                return
            self.state.provider = provider
            self._set_mode(Mode.CONFIG_AI_PROVIDER)
            return
        if self.state.mode == Mode.CONFIG_AI and name == "model":
            if not args:
                print(model_help())
                return
            provider = None
            model_token = args[0]
            if len(args) >= 2:
                provider = self._resolve(args[0], tuple(p.name for p in PROVIDERS))
                if provider is not None:
                    model_token = args[1]
            model = model_definition(model_token, provider)
            if model is None:
                print(f"% Unknown or ambiguous model: {model_token}. Type model ?")
                return
            self.state.selected_model = model.model_id
            print(f"Model policy selected: {model.model_id} ({model.display_name})")
            print("  Availability: catalog candidate; provider web discovery will validate session access.")
            return
        if self.state.mode == Mode.CONFIG_AI and name in {"route", "prompt", "session", "api"}:
            print(f"% {name} configuration submode is reserved for the next orchestration milestone.")
            return
        if self.state.mode == Mode.CONFIG_AI_PROVIDER:
            provider = self.state.provider or "provider"
            if name in {"enable", "disable"}:
                self.state.config.setdefault("providers", {})[provider] = name == "enable"
                print(f"{provider}: routing policy {'enabled' if name == 'enable' else 'disabled'}.")
                return
            if name in {"session", "health"}:
                print(provider_status_view(provider))
                return
            if name == "model":
                print(models_view(provider))
                return
            if name in {"login", "logout"}:
                print(f"{provider}: authentication/session workflow remains owned by the Interceptor runtime.")
                return

    def dispatch(self, raw: str) -> None:
        command = raw.strip()
        if not command:
            return
        if self._context_help(command):
            return
        parts = command.split()
        name = parts[0].lower()
        args = parts[1:]
        if self.state.mode == Mode.BOOT:
            self._dispatch_boot(name, args)
        elif self.state.mode in {Mode.USER_EXEC, Mode.PRIVILEGED_EXEC}:
            self._dispatch_exec(name, args)
        elif self.state.mode in {Mode.CONFIG, Mode.CONFIG_AI, Mode.CONFIG_AI_PROVIDER}:
            self._dispatch_config(name, args)

    def run(self) -> None:
        print(boot_console())
        print()
        while self.state.running:
            try:
                raw = self.session.prompt(self.prompt)
            except (EOFError, KeyboardInterrupt):
                print()
                break
            self.dispatch(raw)


def main() -> None:
    AIRouterShell().run()
