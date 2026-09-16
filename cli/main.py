"""Interactive Cisco-like AInterceptor CLI shell."""
from __future__ import annotations

import asyncio

from cli.chat import chat
from cli.registry import load_providers


def provider_context(provider: str) -> str:
    providers = load_providers()
    if provider not in providers:
        raise ValueError(f"unknown provider: {provider}")
    return provider


def main() -> None:
    providers = load_providers()
    provider: str | None = None

    print("AInterceptor CLI")
    print("Providers: " + ", ".join(f"{i + 1}:{name}" for i, name in enumerate(providers)))
    print("Select a provider by number. Type 'help' for commands or 'exit' to quit.")

    while True:
        prompt = f"AInterceptor [{provider}]> " if provider else "AInterceptor> "
        try:
            command = input(prompt).strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return

        if not command:
            continue
        if command in {"exit", "quit"}:
            return
        if command == "help":
            print("Commands: <1-4>=select provider, use <provider>, back, exit")
            print("With a provider selected, any other text is sent as a chat prompt.")
            continue
        if command == "back":
            provider = None
            continue
        if command.isdigit() and 1 <= int(command) <= len(providers):
            provider = providers[int(command) - 1]
            print(f"Selected provider: {provider}")
            continue
        if command.lower().startswith("use "):
            requested = command[4:].strip().lower()
            if requested in providers:
                provider = provider_context(requested)
                print(f"Selected provider: {provider}")
            else:
                print(f"% Unknown provider: {requested}")
            continue
        if provider is None:
            print("% Select a provider first")
            continue

        try:
            asyncio.run(chat(provider, command))
            print()
        except Exception as exc:
            print(f"% {exc}")


if __name__ == "__main__":
    main()
