"""Local config file at ~/.airouter/config.json."""
from __future__ import annotations
import json, pathlib
from dataclasses import dataclass, asdict

CONFIG_PATH = pathlib.Path.home() / ".airouter" / "config.json"


@dataclass
class AgentConfig:
    server: str = ""
    token: str = ""


def load() -> AgentConfig:
    if not CONFIG_PATH.exists():
        return AgentConfig()
    try:
        data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        return AgentConfig(server=data.get("server", ""), token=data.get("token", ""))
    except Exception:
        return AgentConfig()


def save(cfg: AgentConfig) -> None:
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(json.dumps(asdict(cfg), indent=2), encoding="utf-8")
