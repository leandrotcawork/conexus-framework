"""Rewrite the `_tool_schemas = {...}` block at top of the tool class.

Only this block is rewritten — method bodies, docstrings, imports untouched.
Bodies remain editable in IDE; UI owns metadata only.
"""
from __future__ import annotations

import ast
import json
from pathlib import Path
from typing import Any


def _format_block(schemas: dict[str, Any], indent: str = "    ") -> str:
    payload = json.dumps(schemas, indent=4, ensure_ascii=False)
    indented = "\n".join((indent + line) if line else line for line in payload.splitlines())
    return f"{indent}_tool_schemas = {indented.lstrip()}"


def _is_schemas(s: ast.stmt) -> bool:
    if isinstance(s, ast.Assign):
        return any(isinstance(t, ast.Name) and t.id == "_tool_schemas" for t in s.targets)
    if isinstance(s, ast.AnnAssign):
        return isinstance(s.target, ast.Name) and s.target.id == "_tool_schemas"
    return False


def write_tool_schemas(path: Path, schemas: dict[str, Any]) -> None:
    src = path.read_text(encoding="utf-8")
    tree = ast.parse(src, filename=str(path))

    class_node: ast.ClassDef | None = next(
        (n for n in tree.body if isinstance(n, ast.ClassDef)), None
    )
    if class_node is None:
        raise ValueError(f"{path}: no class found")

    lines = src.splitlines(keepends=True)
    block_text = _format_block(schemas) + "\n"

    existing = next((s for s in class_node.body if _is_schemas(s)), None)

    if existing is not None:
        start = existing.lineno - 1
        end = existing.end_lineno or existing.lineno
        new_lines = lines[:start] + [block_text] + lines[end:]
    else:
        first = class_node.body[0]
        insert_after_line = first.end_lineno if (
            isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant)
        ) else class_node.lineno
        new_lines = lines[:insert_after_line] + [block_text + "\n"] + lines[insert_after_line:]

    path.write_text("".join(new_lines), encoding="utf-8")
