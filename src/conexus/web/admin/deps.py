"""Dependency injection helpers for admin routes."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass
class AdminContext:
    agents_dir: Path
    data_dir: Path
    connectors_registry_path: Path
    repo_root: Path
