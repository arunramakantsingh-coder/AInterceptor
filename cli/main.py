"""AInterceptor CLI entry point."""
from __future__ import annotations

from .shell import InteractiveShell


def main() -> None:
    InteractiveShell().run()


if __name__ == "__main__":
    main()
