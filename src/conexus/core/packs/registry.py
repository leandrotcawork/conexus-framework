"""Unified pack/connector registry. Single source of truth for installable items."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal


class RegistryError(ValueError):
    pass


Kind = Literal["skill", "connector"]


@dataclass(frozen=True)
class PackUI:
    label: str
    icon: str
    category: str
    description: str


@dataclass(frozen=True)
class PackEntry:
    id: str
    kind: Kind
    version: str
    source: str
    sha: str
    ui: PackUI
    server_url: str = ""
    scopes: list[str] = field(default_factory=list)


class PacksRegistry:
    def __init__(self, entries: list[PackEntry]) -> None:
        self._by_id = {e.id: e for e in entries}

    @classmethod
    def load(cls, path: Path) -> "PacksRegistry":
        if not path.exists():
            return cls([])
        data = json.loads(path.read_text(encoding="utf-8"))
        out: list[PackEntry] = []
        for raw in data.get("entries", []):
            ui = raw.get("ui", {})
            out.append(PackEntry(
                id=raw["id"],
                kind=raw["kind"],
                version=raw["version"],
                source=raw["source"],
                sha=raw["sha"],
                ui=PackUI(
                    label=ui.get("label", raw["id"]),
                    icon=ui.get("icon", "package"),
                    category=ui.get("category", "Other"),
                    description=ui.get("description", ""),
                ),
                server_url=raw.get("server_url", ""),
                scopes=list(raw.get("scopes", [])),
            ))
        return cls(out)

    def get(self, pack_id: str) -> PackEntry:
        if pack_id not in self._by_id:
            raise RegistryError(f"unknown pack: {pack_id}")
        return self._by_id[pack_id]

    def list(self, *, kind: Kind | None = None) -> list[PackEntry]:
        if kind is None:
            return list(self._by_id.values())
        return [e for e in self._by_id.values() if e.kind == kind]
