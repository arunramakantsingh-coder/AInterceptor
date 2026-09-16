from dataclasses import dataclass
from pathlib import Path
import json


@dataclass(frozen=True)
class ProviderSpec:
    name: str
    display_name: str
    transport: str
    configured: bool


ROOT = Path(__file__).resolve().parents[1]
PROVIDERS_DIR = ROOT / "providers"


def load_providers() -> list[ProviderSpec]:
    providers = []

    for path in sorted(PROVIDERS_DIR.glob("*/provider.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        providers.append(
            ProviderSpec(
                name=data["name"],
                display_name=data["display_name"],
                transport=data.get("transport", "web"),
                configured=bool(data.get("configured", False)),
            )
        )

    # Stable operator-facing order.
    preferred = {"chatgpt": 1, "claude": 2, "gemini": 3, "grok": 4}
    return sorted(providers, key=lambda p: preferred.get(p.name, 99))
