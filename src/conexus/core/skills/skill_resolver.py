"""SkillLoader — resolves skills: list, loads SKILL_PACK.md, registers backends."""
from __future__ import annotations
import importlib.util
import sys
from pathlib import Path
from conexus.core.skills.pack_loader import parse_skill_pack, SkillPackBackend
from conexus.core.agent_registry import AgentRegistry
from conexus.core.backends.python_backend import PythonBackend
from conexus.core.backends.mcp_stdio_backend import McpStdioBackend


class SkillLoader:
    """Load skills referenced in SKILL.md `skills:` list.

    Convention: skills live at `<agent_dir>/skills/<name>/SKILL_PACK.md`.
    Returns (extra_prompt_fragment: str, tool_tags: dict[str, str]).
    """

    def __init__(self, agent_dir: str | Path, registry: AgentRegistry, agent_name: str) -> None:
        self._agent_dir = Path(agent_dir)
        self._registry = registry
        self._agent_name = agent_name

    def load(self, skill_refs: list[str]) -> tuple[str, dict[str, str]]:
        """Load each skill. Returns (combined_prompt_fragment, merged_tool_tags)."""
        prompt_parts: list[str] = []
        tool_tags: dict[str, str] = {}

        for ref in skill_refs:
            name = ref.split("@")[0]
            pack_path = self._agent_dir / "skills" / name / "SKILL_PACK.md"
            if not pack_path.exists():
                raise FileNotFoundError(f"SKILL_PACK.md not found for skill '{name}': {pack_path}")

            doc = parse_skill_pack(pack_path)
            tool_tags.update(doc.frontmatter.data_classes)

            if doc.body:
                prompt_parts.append(doc.body)

            if doc.frontmatter.backend == SkillPackBackend.python:
                tools_py = doc.pack_dir / "tools.py"
                if tools_py.exists():
                    mod = self._load_module(name, tools_py)
                    tools_cls = next(
                        (v for v in vars(mod).values() if isinstance(v, type) and not v.__name__.startswith("_")),
                        None,
                    )
                    if tools_cls:
                        self._registry.register_backend(
                            self._agent_name, PythonBackend(tools_cls())
                        )

            elif doc.frontmatter.backend == SkillPackBackend.mcp_stdio:
                mcp_json = doc.pack_dir / "mcp.json"
                if not mcp_json.exists():
                    raise FileNotFoundError(f"mcp.json required for mcp-stdio backend: {mcp_json}")
                import json
                cfg = json.loads(mcp_json.read_text())
                backend = McpStdioBackend(command=cfg["command"], env=cfg.get("env"))
                self._registry.register_backend(self._agent_name, backend)

        return "\n\n".join(prompt_parts), tool_tags

    @staticmethod
    def _load_module(name: str, path: Path):
        module_name = f"_conexus_skill_{name}_tools"
        spec = importlib.util.spec_from_file_location(module_name, path)
        if spec is None or spec.loader is None:
            raise ImportError(f"Cannot load {path}")
        mod = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = mod
        spec.loader.exec_module(mod)  # type: ignore[union-attr]
        return mod
