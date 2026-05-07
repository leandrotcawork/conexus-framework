import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


@dataclass
class RegistryEntry:
    name: str
    version: str
    server_url: str
    scopes: list[str]
    ui_label: str
    ui_icon: str
    ui_category: str
    ui_description: str
    pack_url: str | None = None


class ConnectorRegistry:
    def __init__(self, entries: list[RegistryEntry]) -> None:
        self._entries = {e.name: e for e in entries}

    @classmethod
    def from_file(cls, path: str | Path) -> "ConnectorRegistry":
        d = json.loads(Path(path).read_text())
        entries = [
            RegistryEntry(
                name=c["name"], version=c["version"], server_url=c["server_url"],
                scopes=c["scopes"], ui_label=c["ui"]["label"], ui_icon=c["ui"]["icon"],
                ui_category=c["ui"]["category"], ui_description=c["ui"]["description"],
                pack_url=c.get("pack_url"),
            )
            for c in d["connectors"]
        ]
        return cls(entries)

    def list(self) -> Iterable[RegistryEntry]:
        return self._entries.values()

    def get(self, name: str) -> RegistryEntry | None:
        return self._entries.get(name)
