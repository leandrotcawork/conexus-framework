"""AST scan of an agent's tools.py — list public instance methods."""
from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ToolParam:
    name: str
    annotation: str | None
    has_default: bool


@dataclass(frozen=True)
class ToolMethod:
    name: str
    params: list[ToolParam]
    return_annotation: str | None
    docstring: str | None
    description: str | None  # from _tool_schemas if present


def _find_tool_class(tree: ast.Module) -> ast.ClassDef | None:
    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            return node
    return None


def _extract_schemas(cls: ast.ClassDef) -> dict[str, str]:
    """Pull description from _tool_schemas = {...} dict literal."""
    out: dict[str, str] = {}
    for stmt in cls.body:
        if isinstance(stmt, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == "_tool_schemas" for t in stmt.targets
        ):
            if isinstance(stmt.value, ast.Dict):
                for k, v in zip(stmt.value.keys, stmt.value.values, strict=False):
                    if isinstance(k, ast.Constant) and isinstance(v, ast.Dict):
                        for sk, sv in zip(v.keys, v.values, strict=False):
                            if (
                                isinstance(sk, ast.Constant)
                                and sk.value == "description"
                                and isinstance(sv, ast.Constant)
                            ):
                                out[k.value] = sv.value
    return out


def _is_public_instance_method(stmt: ast.stmt) -> bool:
    if not isinstance(stmt, ast.FunctionDef | ast.AsyncFunctionDef):
        return False
    if stmt.name.startswith("_"):
        return False
    if any(isinstance(d, ast.Name) and d.id in {"staticmethod", "classmethod"} for d in stmt.decorator_list):
        return False
    if not stmt.args.args or stmt.args.args[0].arg != "self":
        return False
    return True


def _ann(node: ast.expr | None) -> str | None:
    return ast.unparse(node) if node else None


def scan_tools_file(path: Path) -> list[ToolMethod]:
    src = path.read_text(encoding="utf-8")
    tree = ast.parse(src, filename=str(path))
    cls = _find_tool_class(tree)
    if cls is None:
        return []
    schemas = _extract_schemas(cls)
    out: list[ToolMethod] = []
    for stmt in cls.body:
        if not _is_public_instance_method(stmt):
            continue
        assert isinstance(stmt, ast.FunctionDef | ast.AsyncFunctionDef)
        defaults_offset = len(stmt.args.args) - len(stmt.args.defaults)
        params = [
            ToolParam(name=a.arg, annotation=_ann(a.annotation), has_default=(i >= defaults_offset))
            for i, a in enumerate(stmt.args.args[1:], start=1)
        ]
        out.append(
            ToolMethod(
                name=stmt.name,
                params=params,
                return_annotation=_ann(stmt.returns),
                docstring=ast.get_docstring(stmt),
                description=schemas.get(stmt.name),
            )
        )
    return out
