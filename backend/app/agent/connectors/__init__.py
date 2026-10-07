"""Connectors: how AInterceptor reaches each kind of target."""
from __future__ import annotations

from app.agent.connectors import local  # noqa: F401  (registers kinds)


def get_connector(target):
    """Return a connector instance for a target."""
    if target.kind == "local":
        return local.LocalConnector(target)
    raise ValueError(f"no connector for kind={target.kind!r}")
