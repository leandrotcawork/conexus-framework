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
        p = Path(path)
        if not p.exists():
            return cls([])
        d = json.loads(p.read_text())
        if "connectors" in d:
            # Legacy format: {"connectors": [{name, version, server_url, ...}]}
            entries = [
                RegistryEntry(
                    name=c["name"], version=c["version"], server_url=c["server_url"],
                    scopes=c["scopes"], ui_label=c["ui"]["label"], ui_icon=c["ui"]["icon"],
                    ui_category=c["ui"]["category"], ui_description=c["ui"]["description"],
                    pack_url=c.get("pack_url"),
                )
                for c in d["connectors"]
            ]
        else:
            # Unified format: {"entries": [{kind, id, version, server_url, ...}]}
            entries = [
                RegistryEntry(
                    name=e["id"], version=e["version"],
                    server_url=e.get("server_url", ""),
                    scopes=e.get("scopes", []),
                    ui_label=e["ui"]["label"], ui_icon=e["ui"]["icon"],
                    ui_category=e["ui"]["category"], ui_description=e["ui"]["description"],
                    pack_url=e.get("source"),
                )
                for e in d.get("entries", [])
                if e.get("kind") == "connector"
            ]
        return cls(entries)

    def list(self) -> Iterable[RegistryEntry]:
        return self._entries.values()

    def get(self, name: str) -> RegistryEntry | None:
        return self._entries.get(name)
