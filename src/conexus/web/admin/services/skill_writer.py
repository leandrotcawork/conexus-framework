"""Atomic SKILL.md writer."""
from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Any

import yaml


def write_skill_md(path: Path, frontmatter: dict[str, Any], body: str) -> None:
    """Write SKILL.md atomically: tmp file → fsync → os.replace.

    Guarantees:
    - Existing file preserved on any failure (write, fsync, or replace).
    - No `*.tmp*` leftovers in parent on failure paths.
    """
    fm_yaml = yaml.safe_dump(frontmatter, sort_keys=False, allow_unicode=True).rstrip()
    content = f"---\n{fm_yaml}\n---\n{body.rstrip()}\n"

    parent = path.parent
    parent.mkdir(parents=True, exist_ok=True)

    fd, tmp = tempfile.mkstemp(prefix=path.name, suffix=".tmp", dir=str(parent))
    try:
        try:
            f = os.fdopen(fd, "w", encoding="utf-8")
        except Exception:
            os.close(fd)
            raise
        with f:
            f.write(content)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
        tmp = None  # success: tmp consumed by replace
    finally:
        if tmp is not None:
            try:
                os.unlink(tmp)
            except OSError:
                pass
