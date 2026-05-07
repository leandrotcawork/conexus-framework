"""One-shot: convert connectors/registry.json + scan packs/ -> packs/registry.json."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

from conexus.core.skills.pack_loader import parse_skill_pack


def _git_sha(path: Path) -> str:
    try:
        r = subprocess.run(
            ["git", "log", "-1", "--format=%H", "--", str(path)],
            capture_output=True, text=True, check=True,
        )
        return r.stdout.strip() or "unsigned"
    except Exception:
        return "unsigned"


def main(repo_root: Path) -> None:
    entries: list[dict] = []

    packs_dir = repo_root / "packs"
    for pack_md in sorted(packs_dir.glob("*/SKILL_PACK.md")):
        doc = parse_skill_pack(pack_md)
        fm = doc.frontmatter
        entries.append({
            "id": fm.name,
            "kind": "skill",
            "version": fm.version,
            "source": str(pack_md.parent.relative_to(repo_root)).replace("\\", "/"),
            "sha": _git_sha(pack_md.parent),
            "ui": {
                "label": fm.name.replace("_", " ").title(),
                "icon": "puzzle",
                "category": "Skills",
                "description": (doc.body[:140] + "…") if len(doc.body) > 140 else doc.body,
            },
        })

    legacy = repo_root / "connectors" / "registry.json"
    if legacy.exists():
        data = json.loads(legacy.read_text(encoding="utf-8"))
        for c in data.get("connectors", []):
            ui = c.get("ui", {})
            entries.append({
                "id": c["name"],
                "kind": "connector",
                "version": c.get("version", "1.0"),
                "source": c.get("pack_url", ""),
                "sha": "unsigned",
                "server_url": c.get("server_url", ""),
                "scopes": c.get("scopes", []),
                "ui": {
                    "label": ui.get("label", c["name"]),
                    "icon": ui.get("icon", "plug"),
                    "category": ui.get("category", "Connector"),
                    "description": ui.get("description", ""),
                },
            })

    out = repo_root / "packs" / "registry.json"
    out.write_text(json.dumps({"version": "1.0", "entries": entries}, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {out} with {len(entries)} entries")


if __name__ == "__main__":
    import sys
    main(Path(sys.argv[1]) if len(sys.argv) > 1 else Path.cwd())
