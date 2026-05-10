"""Wiki frontmatter - YAML between --- fences. Parse, inject defaults, validate."""
from __future__ import annotations

import re
from datetime import date
from typing import Any

import yaml

_FENCE_RE = re.compile(r"\A---\s*\n(.*?)\n---\s*\n?(.*)\Z", re.DOTALL)
_ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def parse(text: str) -> tuple[dict[str, Any], str]:
    """Returns (meta, body). Empty meta if no frontmatter. Raises ValueError on malformed YAML."""
    m = _FENCE_RE.match(text)
    if not m:
        return {}, text
    try:
        meta = yaml.safe_load(m.group(1)) or {}
    except yaml.YAMLError as e:
        raise ValueError(f"malformed frontmatter YAML: {e}") from e
    if not isinstance(meta, dict):
        raise ValueError("frontmatter must be a YAML mapping")
    return _normalize_yaml_scalars(meta), m.group(2)


def inject(text: str, defaults: dict[str, Any]) -> str:
    """Add frontmatter if missing; update 'updated' field if present.
    Never overwrites 'created' or 'reviewed'."""
    meta, body = parse(text)
    if not meta:
        meta = dict(defaults)
    else:
        meta.setdefault("created", defaults.get("created"))
        meta.setdefault("tags", defaults.get("tags", []))
        meta.setdefault("source", defaults.get("source"))
        meta.setdefault("reviewed", defaults.get("reviewed", False))
        if "updated" in defaults:
            meta["updated"] = defaults["updated"]
    fm = yaml.safe_dump(meta, sort_keys=False, default_flow_style=False).strip()
    return f"---\n{fm}\n---\n{body}"


def validate(meta: dict[str, Any]) -> list[str]:
    """Soft warnings list. Hard errors raise ValueError."""
    warnings: list[str] = []
    for required in ("created", "updated"):
        v = meta.get(required)
        if v is None:
            warnings.append(f"missing {required}")
        elif not isinstance(v, str) or not _ISO_DATE_RE.match(v):
            raise ValueError(f"{required} must be ISO date YYYY-MM-DD, got {v!r}")
    if "reviewed" in meta and not isinstance(meta["reviewed"], bool):
        raise ValueError(f"reviewed must be bool, got {type(meta['reviewed']).__name__}")
    if "tags" in meta and not isinstance(meta["tags"], list):
        raise ValueError("tags must be a list")
    if "source" not in meta:
        warnings.append("missing source")
    if "tags" not in meta:
        warnings.append("missing tags")
    return warnings


def today_iso() -> str:
    return date.today().isoformat()


def _normalize_yaml_scalars(value: Any) -> Any:
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, dict):
        return {k: _normalize_yaml_scalars(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_normalize_yaml_scalars(v) for v in value]
    return value
