"""AInterceptor CLI entry point."""
from __future__ import annotations

from .shell import AIRouterShell


def main() -> None:
    AIRouterShell().run()


if __name__ == "__main__":
    main()
