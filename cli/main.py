"""Minimal Cisco-like AInterceptor CLI shell."""
from __future__ import annotations

from cli.registry import load_providers


def provider_context(provider: str) -> str:
    providers = load_providers()
    if provider not in providers:
        raise ValueError(f"unknown provider: {provider}")
    return provider


def main() -> None:
    providers = load_providers()
    print("AInterceptor CLI")
    print("Providers: " + ", ".join(f"{i + 1}:{name}" for i, name in enumerate(providers)))
    while True:
        try:
            command = input("AInterceptor> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return
        if command in {"exit", "quit"}:
            return
        if command.isdigit() and 1 <= int(command) <= len(providers):
            provider = providers[int(command) - 1]
            print(f"AInterceptor [{provider}]>")
            continue
        print("% Unknown command")


if __name__ == "__main__":
    main()
