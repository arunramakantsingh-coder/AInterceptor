"""Connectors: how AInterceptor reaches each kind of target."""
from __future__ import annotations

from app.agent.connectors import local   # noqa: F401
from app.agent.connectors import winhelper  # noqa: F401


def get_connector(target):
    """Return a connector instance for a target."""
    if target.kind == "local":
        return local.LocalConnector(target)
    if target.kind == "winhelper":
        return winhelper.WinHelperConnector(target)
    raise ValueError(f"no connector for kind={target.kind!r}")
