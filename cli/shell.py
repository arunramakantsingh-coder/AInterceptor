"""Cisco-style AIRouter NOS interactive shell."""
from __future__ import annotations

import asyncio
from pathlib import Path

from prompt_toolkit import PromptSession
from prompt_toolkit.completion import Completer, Completion
from prompt_toolkit.history import FileHistory

from .chat import chat, login_provider
from .config_store import STARTUP_CONFIG, provider_session_status, startup_config_text
from .nos import Mode, NOSState, PROVIDERS, model_definition, model_definitions, prefix_matches, provider_definition, unique_prefix
from .renderer import banner, boot_console, boot_view, bootstrap, counters_view, credits_view, health_view, help_view, model_help, models_view, provider_status_view, providers_status, routes_view, sessions_view, system_status, system_view, version_view

SHOW_TOPICS = ("version", "system", "ai", "providers", "models", "routes", "sessions", "counters", "credits", "health", "boot", "running-config", "startup-config")
SHOW_AI_TOPICS = ("providers", "models", "routes", "sessions", "usage", "credits", "prompts", "health")


class AIRouterCompleter(Completer):
    COMMANDS = {
        Mode.BOOT: ("bootai", "airouter", "exit", "logout", "quit", "?"),
        Mode.USER_EXEC: ("enable", "show", "chat", "airouter", "logout", "exit", "?"),
        Mode.PRIVILEGED_EXEC: ("show", "chat", "configure", "copy", "write", "clear", "disable", "exit", "logout", "?"),
        Mode.CONFIG: ("ai", "exit", "end", "?"),
        Mode.CONFIG_AI: ("provider", "model", "route", "prompt", "session", "api", "exit", "end", "?"),
        Mode.CONFIG_AI_PROVIDER: ("enable", "disable", "login", "logout", "session", "model", "health", "exit", "end", "?"),
    }

    def __init__(self, state: NOSState) -> None:
        self.state = state

    def get_completions(self, document, complete_event):
        text = document.text_before_cursor.lower()
        word = document.get_word_before_cursor().lower()
        if text.startswith("show "):
            topics = SHOW_AI_TOPICS if text.startswith("show ai ") else SHOW_TOPICS
            offset = 8 if text.startswith("show ai ") else 5
            prefix = text[offset:].split()[-1] if text[offset:].strip() else ""
            for item in topics:
                if item.startswith(prefix):
                    yield Completion(item, start_position=-len(prefix))
            return
        if text.startswith("chat ") or (text.startswith("provider ") and self.state.mode == Mode.CONFIG_AI):
            offset = 5 if text.startswith("chat ") else 9
            prefix = text[offset:].split()[-1] if text[offset:].strip() else ""
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
        for command in self.COMMANDS.get(self.state.mode, ()):
            if command.startswith(word):
                yield Completion(command, start_position=-len(word))


class AIRouterShell:
    def __init__(self) -> None:
        self.state = NOSState()
        history_dir = Path(".ainterceptor")
        history_dir.mkdir(parents=True, exist_ok=True)
        history = FileHistory(str(history_dir / "cli_history"))
        self.session = PromptSession(history=history, completer=AIRouterCompleter(self.state), complete_while_typing=False)
        self.chat_session = PromptSession(history=history, completer=None)

    @property
    def prompt(self) -> str:
        mode = self.state.mode
        if mode == Mode.BOOT: return "AInterceptor-BOOT> "
        if mode == Mode.USER_EXEC: return "AIRouter> "
        if mode == Mode.PRIVILEGED_EXEC: return "AIRouter# "
        if mode == Mode.CONFIG: return "AIRouter(config)# "
        if mode == Mode.CONFIG_AI: return "AIRouter(config-ai)# "
        if mode == Mode.CONFIG_AI_PROVIDER: return f"AIRouter(config-ai-provider-{self.state.provider or 'provider'})# "
        return "AIRouter(chat)> "

    def _set_mode(self, mode: Mode) -> None:
        self.state.mode = mode
        self.session.completer = AIRouterCompleter(self.state)

    @staticmethod
    def _resolve(token: str, candidates: tuple[str, ...] | list[str]) -> str | None:
        exact = next((x for x in candidates if x.lower() == token.lower()), None)
        return exact or unique_prefix(token, candidates)

    def _running_config(self) -> str:
        cfg = self.state.config
        ai = cfg.setdefault("ai", {})
        providers = ai.setdefault("providers", {})
        lines = ["!", "! AIRouter running configuration", "!", f"version {cfg.get('software_version', '0.2.0-m2')}", f"hostname {cfg.get('hostname', 'AIRouter')}", f"config-register {cfg.get('config_register', '0x2102')}", "", "ai"]
        if self.state.selected_model:
            lines.append(f" model {self.state.selected_model}")
        for item in PROVIDERS:
            entry = providers.get(item.name)
            if not isinstance(entry, dict):
                continue
            lines.append(f" provider {item.name}")
            lines.append("  enable" if entry.get("enabled") else "  disable")
            if entry.get("authenticated"):
                lines.append("  session authenticated")
                lines.append(f"  session storage-state {entry.get('session_path', '.ainterceptor/' + item.name + '/storage_state.json')}")
        routes = ai.get("routes", {})
        for name, value in routes.items():
            lines.append(f" route {name} {value}")
        prompts = ai.get("prompts", {})
        for name, value in prompts.items():
            lines.append(f" prompt {name} {value}")
        lines.extend([" exit", "!", "end"])
        return "\n".join(lines)

    def _show(self, args: list[str]) -> str:
        if not args:
            return system_status()
        topic = self._resolve(args[0], SHOW_TOPICS)
        if topic == "version": return version_view()
        if topic == "system": return system_view()
        if topic == "boot": return boot_view()
        if topic == "running-config": return self._running_config()
        if topic == "startup-config": return startup_config_text().rstrip()
        if topic == "ai":
            sub = self._resolve(args[1], SHOW_AI_TOPICS) if len(args) > 1 else None
            if sub == "providers": return providers_status()
            if sub == "models": return models_view()
            if sub == "routes": return routes_view()
            if sub == "sessions": return sessions_view()
            if sub in {"usage", "counters"}: return counters_view(self.state.counters)
            if sub == "credits": return credits_view()
            if sub == "health": return health_view()
            return self._running_config()
        if topic in {"providers", "provider"}: return providers_status()
        if topic == "models": return models_view()
        if topic == "routes": return routes_view()
        if topic == "sessions": return sessions_view()
        if topic == "counters": return counters_view(self.state.counters)
        if topic == "credits": return credits_view()
        if topic == "health": return health_view()
        return f"% Unknown show topic: {args[0]}. Type show ?."

    def _context_help(self, raw: str) -> bool:
        if "?" not in raw: return False
        attached = raw.rstrip().endswith("?") and not raw.rstrip().endswith(" ?")
        base = raw.rstrip()[:-1] if attached else raw.rstrip()
        parts = base.split()
        if not parts or raw.strip() == "?":
            print(help_view(self.state.mode.value)); return True
        first = parts[0].lower()
        commands = tuple(x for x in AIRouterCompleter.COMMANDS.get(self.state.mode, ()) if x != "?")
        resolved = self._resolve(first, commands)
        if attached and len(parts) == 1:
            print("\n".join(f"  {x}" for x in prefix_matches(parts[-1], commands)) or "  No matching commands."); return True
        if resolved is None:
            print("  No matching commands."); return True
        if resolved == "show":
            if len(parts) == 1:
                print("\n".join(f"  {x}" for x in SHOW_TOPICS)); return True
            if parts[1].lower() == "ai":
                prefix = parts[-1] if attached and len(parts) > 2 else ""
                print("\n".join(f"  {x}" for x in prefix_matches(prefix, SHOW_AI_TOPICS)) or "  No matching show ai options."); return True
            prefix = parts[-1] if attached else ""
            print("\n".join(f"  {x}" for x in prefix_matches(prefix, SHOW_TOPICS)) or "  No matching show options."); return True
        if resolved == "configure": print("  terminal    Enter configuration from terminal"); return True
        if resolved in {"chat", "provider"}:
            print("\n".join(f"  {p.name}" for p in PROVIDERS)); return True
        if resolved == "model" and self.state.mode == Mode.CONFIG_AI:
            provider = self._resolve(parts[1], tuple(p.name for p in PROVIDERS)) if len(parts) > 1 else None
            print(model_help(provider)); return True
        return False

    def _chat(self, provider: str, initial_prompt: str | None, return_mode: Mode) -> None:
        definition = provider_definition(provider)
        if definition is None:
            print(f"% Unknown provider: {provider}"); return
        self.state.chat_provider = provider
        self._set_mode(Mode.CHAT)
        print(f"\nConnected to {definition.display_name} chat context.")
        print("Type /exit, /back, or press Ctrl+C to return to AIRouter.\n")
        if initial_prompt: self._run_chat(provider, initial_prompt)
        while self.state.running and self.state.mode == Mode.CHAT:
            try: prompt = self.chat_session.prompt("AIRouter(chat)> ").strip()
            except (EOFError, KeyboardInterrupt): self._set_mode(return_mode); print(); return
            if not prompt: continue
            if prompt.lower() in {"/exit", "/quit", "/back"}:
                self._set_mode(return_mode); print("Returning to AIRouter."); return
            self._run_chat(provider, prompt)

    def _run_chat(self, provider: str, prompt: str) -> None:
        try:
            self.state.counters["requests"] += 1
            print(f"\n{provider.title()}:\n  ", end="", flush=True)
            asyncio.run(chat(provider, prompt, on_delta=lambda d: print(d, end="", flush=True)))
            self.state.counters["success"] += 1
            print("\n")
        except Exception as exc:
            self.state.counters["failed"] += 1
            print(f"\n% {exc}\n")

    def _login(self, provider: str) -> None:
        try:
            result = asyncio.run(login_provider(provider))
            entry = self.state.config.setdefault("ai", {}).setdefault("providers", {}).setdefault(provider, {})
            entry.update({"authenticated": True, "session_path": result.get("session_path") or f".ainterceptor/{provider}/storage_state.json"})
            self.state.config["ai"]["providers"][provider] = entry
            self.state.save_startup()
            print(f"{provider}: runtime configuration updated; startup config is ready to save/boot.")
        except Exception as exc:
            print(f"% {provider} login failed: {exc}")

    def _save_running_config(self) -> None:
        self.state.config.setdefault("ai", {})["selected_model"] = self.state.selected_model
        from .config_store import save_startup_config
        save_startup_config(self.state.config)
        print(f"Building configuration... [OK]\n[OK] startup-config saved to {STARTUP_CONFIG}")

    def _dispatch_boot(self, name: str) -> None:
        resolved = self._resolve(name, ("bootai", "airouter", "exit", "logout", "quit"))
        if resolved == "airouter":
            print("\n" + banner()); print(); print(bootstrap()); print(providers_status()); print("\nAIRouter NOS initialized. Type ? for commands.\n"); self._set_mode(Mode.USER_EXEC); return
        if resolved == "bootai": print("AInterceptor boot mode ready. Startup configuration is loaded from persistent NVRAM at NOS initialization."); return
        if resolved in {"exit", "logout", "quit"}: self.state.running = False; return
        print(f"% Unknown boot command: {name}. Type ?." )

    def _dispatch_exec(self, name: str, args: list[str]) -> None:
        commands = tuple(x for x in AIRouterCompleter.COMMANDS[self.state.mode] if x != "?")
        resolved = self._resolve(name, commands)
        if resolved is None:
            matches = prefix_matches(name, commands)
            print(f"% Ambiguous command: {name} ({', '.join(matches)})" if matches else f"% Unknown command: {name}. Type ?."); return
        if resolved == "show": print(self._show(args)); return
        if resolved == "airouter": print("\n" + banner()); return
        if resolved == "enable" and self.state.mode == Mode.USER_EXEC: self._set_mode(Mode.PRIVILEGED_EXEC); return
        if resolved == "disable" and self.state.mode == Mode.PRIVILEGED_EXEC: self._set_mode(Mode.USER_EXEC); return
        if resolved in {"exit", "logout", "quit"}:
            if self.state.mode == Mode.USER_EXEC: self.state.running = False
            else: self._set_mode(Mode.USER_EXEC)
            return
        if resolved == "configure" and self.state.mode == Mode.PRIVILEGED_EXEC:
            if not args or self._resolve(args[0], ("terminal",)) is None: print("Usage: configure terminal"); return
            print("Enter configuration commands, one per line. End with 'end'."); self._set_mode(Mode.CONFIG); return
        if resolved in {"copy", "write"} and self.state.mode == Mode.PRIVILEGED_EXEC:
            if resolved == "write" or (args and args[0].lower() in {"running-config", "run"} and len(args) > 1 and args[1].lower() in {"startup-config", "start"}):
                self._save_running_config(); return
            print("Usage: copy running-config startup-config"); return
        if resolved == "clear" and self.state.mode == Mode.PRIVILEGED_EXEC:
            if not args or self._resolve(args[0], ("counters",)) is None: print("Usage: clear counters"); return
            for key in self.state.counters: self.state.counters[key] = 0
            print("Counters cleared."); return
        if resolved == "chat":
            if not args: print("Usage: chat <provider> [initial prompt]"); return
            provider = self._resolve(args[0], tuple(p.name for p in PROVIDERS))
            if provider is None: print(f"% Unknown or ambiguous provider: {args[0]}"); return
            self._chat(provider, " ".join(args[1:]) or None, self.state.mode)

    def _dispatch_config(self, name: str, args: list[str]) -> None:
        commands = tuple(x for x in AIRouterCompleter.COMMANDS[self.state.mode] if x != "?")
        resolved = self._resolve(name, commands)
        if resolved is None:
            matches = prefix_matches(name, commands)
            print(f"% Ambiguous command: {name} ({', '.join(matches)})" if matches else f"% Unknown command: {name}. Type ?."); return
        if resolved == "exit":
            self._set_mode(Mode.PRIVILEGED_EXEC if self.state.mode == Mode.CONFIG else Mode.CONFIG if self.state.mode == Mode.CONFIG_AI else Mode.CONFIG_AI); return
        if resolved == "end": self._set_mode(Mode.PRIVILEGED_EXEC); return
        if self.state.mode == Mode.CONFIG and resolved == "ai": self._set_mode(Mode.CONFIG_AI); return
        if self.state.mode == Mode.CONFIG_AI and resolved == "provider":
            if not args: print("Usage: provider <chatgpt|claude|gemini|deepseek>"); return
            provider = self._resolve(args[0], tuple(p.name for p in PROVIDERS))
            if provider is None: print(f"% Unknown or ambiguous provider: {args[0]}"); return
            self.state.provider = provider; self._set_mode(Mode.CONFIG_AI_PROVIDER); return
        if self.state.mode == Mode.CONFIG_AI and resolved == "model":
            if not args: print(model_help()); return
            provider = None; token = args[0]
            if len(args) > 1:
                provider = self._resolve(args[0], tuple(p.name for p in PROVIDERS))
                if provider: token = args[1]
            model = model_definition(token, provider)
            if model is None: print(f"% Unknown or ambiguous model: {token}. Type model ?"); return
            self.state.selected_model = model.model_id; self.state.config.setdefault("ai", {})["selected_model"] = model.model_id; print(f"Model policy selected: {model.model_id} ({model.display_name})"); return
        if self.state.mode == Mode.CONFIG_AI and resolved in {"route", "prompt", "session", "api"}:
            print(f"% {resolved} configuration submode is reserved for the next orchestration milestone."); return
        if self.state.mode == Mode.CONFIG_AI_PROVIDER:
            provider = self.state.provider or "provider"
            entry = self.state.config.setdefault("ai", {}).setdefault("providers", {}).setdefault(provider, {})
            if resolved in {"enable", "disable"}:
                entry["enabled"] = resolved == "enable"
                print(f"{provider}: routing policy {'enabled' if resolved == 'enable' else 'disabled'}."); return
            if resolved == "login": self._login(provider); return
            if resolved == "logout":
                entry["authenticated"] = False; print(f"{provider}: runtime session marked unauthenticated."); return
            if resolved in {"session", "health"}: print(provider_status_view(provider)); return
            if resolved == "model": print(models_view(provider)); return

    def dispatch(self, raw: str) -> None:
        command = raw.strip()
        if not command: return
        if self._context_help(command): return
        parts = command.split(); name = parts[0].lower(); args = parts[1:]
        if self.state.mode == Mode.BOOT: self._dispatch_boot(name)
        elif self.state.mode in {Mode.USER_EXEC, Mode.PRIVILEGED_EXEC}: self._dispatch_exec(name, args)
        elif self.state.mode in {Mode.CONFIG, Mode.CONFIG_AI, Mode.CONFIG_AI_PROVIDER}: self._dispatch_config(name, args)

    def run(self) -> None:
        print(boot_console()); print()
        while self.state.running:
            try: raw = self.session.prompt(self.prompt)
            except (EOFError, KeyboardInterrupt): print(); break
            self.dispatch(raw)


def main() -> None:
    AIRouterShell().run()
