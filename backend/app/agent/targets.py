"""Target registry: every machine AInterceptor can reach.

A target is *any* machine you have granted access to:
  - the VM itself (kind=local)
  - a Windows laptop over SSH (kind=ssh)
  - a Docker host (kind=docker)
  - an HTTP API like EVE-NG (kind=http)
  - anything with an SSH or HTTP door

Targets are declared statically today; later, add a UI + encrypted
credential store (see backend/app/intelligence/credential_store.py
on the CareerOS side for the reference pattern).
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Target:
    id: str
    kind: str                        # local | ssh | docker | http | vbox | git
    address: str = ""                # host:port, url, or empty for local
    user: str = ""
    credential_ref: str = ""         # key in the credential vault
    capabilities: list[str] = field(default_factory=list)
    config: dict[str, Any] = field(default_factory=dict)


_REGISTRY: dict[str, Target] = {}


def register(t: Target) -> None:
    _REGISTRY[t.id] = t


def get(target_id: str) -> Target:
    if target_id not in _REGISTRY:
        raise KeyError(f"unknown target: {target_id!r} (known: {list(_REGISTRY)})")
    return _REGISTRY[target_id]


def list_targets() -> list[Target]:
    return list(_REGISTRY.values())


def _bootstrap() -> None:
    # The VM itself. Always present, always local, no credentials.
    register(Target(
        id="vm",
        kind="local",
        capabilities=[
            "fs.read", "fs.write", "fs.glob",
            "shell", "http", "git", "docker",
        ],
    ))


_bootstrap()
