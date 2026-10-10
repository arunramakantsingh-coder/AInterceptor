"""Module-level singleton for the running BrowserSupervisor.

The daemon sets this at startup; the dispatcher reads it. Keeps the
dispatcher's signature stable — no need to thread the supervisor through
every layer.
"""
from __future__ import annotations
from typing import Any


_supervisor: Any = None
_exporter: Any = None
_circuits: Any = None
_prober: Any = None


def set_supervisor(s) -> None:
    global _supervisor
    _supervisor = s


def get_supervisor():
    return _supervisor


def set_exporter(e) -> None:
    global _exporter
    _exporter = e


def get_exporter():
    return _exporter


def set_circuits(c) -> None:
    global _circuits
    _circuits = c


def get_circuits():
    return _circuits


def set_prober(p) -> None:
    global _prober
    _prober = p


def get_prober():
    return _prober
