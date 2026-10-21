import dataclasses
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

ProviderName = Literal["ollama", "anthropic", "openai", "gemini", "openai_compatible"]


@dataclass
class Settings:
    provider: ProviderName | None = None
    model: str | None = None
    base_url: str | None = None  # only for openai_compatible
    setup_complete: bool = False


class ConfigStore:
    """Persists Settings as JSON. Writes are atomic; no secrets live here."""

    def __init__(self, path: Path):
        self.path = path

    def load(self) -> Settings:
        if not self.path.exists():
            return Settings()
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except ValueError:
            raw = None
        if not isinstance(raw, dict):
            # Keep the unreadable file for inspection; start from defaults.
            os.replace(self.path, self.path.with_name(self.path.name + ".corrupt"))
            return Settings()
        known = {f.name for f in dataclasses.fields(Settings)}
        return Settings(**{k: v for k, v in raw.items() if k in known})

    def save(self, settings: Settings) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_name(self.path.name + ".tmp")
        tmp.write_text(
            json.dumps(dataclasses.asdict(settings), indent=2), encoding="utf-8"
        )
        os.replace(tmp, self.path)
