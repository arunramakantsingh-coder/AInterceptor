"""Connectors: how AInterceptor reaches each kind of target.

Each connector module loads through a safe loader: a broken
connector disables only its kind, never the daemon (import
isolation). get_connector raises ValueError for unavailable
kinds; the dispatcher converts that into an "error: ..."
string, so one bad connector cannot kill a tool run or the
daemon.
"""
from __future__ import annotations
import importlib
import sys

_KINDS = ("local", "winhelper", "ssh")
_CONNECTORS = {}

for _kind in _KINDS:
    try:
        _CONNECTORS[_kind] = importlib.import_module(
            f"app.agent.connectors.{_kind}")
    except Exception as _e:  # isolation is the point: log, keep going
        print(f"[connectors] DISABLED {_kind}: {_e!r}",
              file=sys.stderr, flush=True)


def get_connector(target):
    """Return a connector instance for a target."""
    kind = getattr(target, "kind", None)
    mod = _CONNECTORS.get(kind)
    if mod is None:
        raise ValueError(f"connector unavailable for kind={kind!r}")
    if kind == "local":
        return mod.LocalConnector(target)
    if kind == "winhelper":
        return mod.WinHelperConnector(target)
    if kind == "ssh":
        return mod.SSHConnector(target)
    raise ValueError(f"no connector for kind={kind!r}")
