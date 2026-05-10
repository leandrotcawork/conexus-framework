"""Validate an agent on disk: pydantic frontmatter + AST tools + subprocess import smoke."""
from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

from conexus.core.config.skill_loader import parse_skill_file

from .tools_inspector import scan_tools_file

# Source of truth: src/conexus/core/identity/tools.py
# Kept fresh via drift-guard test in test_admin_validators.py.
IDENTITY_TOOLS = frozenset({
    "memory_get", "memory_set", "memory_list_facts", "memory_delete",
    "block_get", "block_set", "block_list",
    "wiki_read", "wiki_list", "wiki_search", "wiki_write", "wiki_append_log",
    "wiki_delete", "wiki_exists", "wiki_lint", "wiki_index_update", "wiki_move",
})


@dataclass
class ValidationResult:
    ok: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def _smoke_import(tools_py: Path) -> str | None:
    """Subprocess-import tools.py. Returns error string or None."""
    code = (
        "import importlib.util, sys; "
        f"spec = importlib.util.spec_from_file_location('_smoke', r'{tools_py}'); "
        "mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod); "
        "assert hasattr(mod, 'create_cli_tools')"
    )
    try:
        result = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True, text=True, timeout=10, check=False,
        )
        if result.returncode != 0:
            return (result.stderr or result.stdout or "import failed").strip().splitlines()[-1]
    except subprocess.TimeoutExpired:
        return "import timed out (10s)"
    return None


def validate_agent(agents_dir: Path, name: str) -> ValidationResult:
    res = ValidationResult(ok=True)
    d = agents_dir / name
    skill_path = d / "SKILL.md"
    tools_path = d / "tools.py"

    if not skill_path.exists():
        res.errors.append(f"SKILL.md missing: {skill_path}")
        res.ok = False
        return res

    try:
        skill = parse_skill_file(skill_path)
    except Exception as exc:  # noqa: BLE001
        res.errors.append(f"SKILL.md parse error: {exc}")
        res.ok = False
        return res

    if skill.frontmatter.name != name:
        res.errors.append(f"frontmatter name '{skill.frontmatter.name}' != folder '{name}'")

    if not tools_path.exists():
        res.errors.append("tools.py missing")
        res.ok = False
    else:
        try:
            methods = {m.name for m in scan_tools_file(tools_path)}
        except SyntaxError as exc:
            res.errors.append(f"tools.py syntax error: {exc}")
            res.ok = False
            methods = set()

        identity_active = bool(
            skill.frontmatter.identity and skill.frontmatter.identity.enabled
        )
        for t in skill.frontmatter.tools:
            if t in methods:
                continue
            if identity_active and t in IDENTITY_TOOLS:
                continue
            res.errors.append(f"tools[]: '{t}' not found in tools.py and not an identity tool")

        if not res.errors:
            err = _smoke_import(tools_path)
            if err:
                res.errors.append(f"tools.py import: {err}")

    body = skill.body
    if len(body.split()) < 10:
        res.warnings.append("system prompt < 10 words — agent may behave unpredictably")
    if not skill.frontmatter.llm.fallback:
        res.warnings.append("no LLM fallback configured")
    if not skill.frontmatter.budget:
        res.warnings.append("no budget cap configured")

    res.ok = res.ok and not res.errors
    return res
