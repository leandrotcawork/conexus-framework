"""HandoffRouter — resolves Handoff.to_agent.

Resolution order:
  1. If to_agent != "auto" and member exists, use it.
  2. Match `auto: true` edges from sender — first match wins.
  3. Match `when: ...` edges — first match where safe AST eval against payload is True.
  4. Fall back to manager.
  5. No manager → raise.

If a sqlite3 connection is provided, route() writes one row to handoff_audit per
call (outcome ∈ {"routed","unknown_target","no_match"}).
"""
from __future__ import annotations

import ast
import sqlite3
from typing import Any

from conexus.core.memory.handoff_audit import record_handoff
from conexus.core.team.handoff import Handoff
from conexus.core.team.team_registry import TeamRegistry


class HandoffRouter:
    def __init__(
        self,
        registry: TeamRegistry,
        conn: sqlite3.Connection | None = None,
        *,
        session_id: str = "legacy",
    ) -> None:
        self._reg = registry
        self._conn = conn
        self._session_id = session_id

    def route(self, handoff: Handoff) -> str:
        try:
            target = self._resolve(handoff)
        except ValueError:
            self._audit(handoff, "unknown_target" if handoff.to_agent != "auto" else "no_match")
            raise
        self._audit(handoff, "routed")
        return target

    def _resolve(self, handoff: Handoff) -> str:
        if handoff.to_agent != "auto":
            if not self._reg.has_member(handoff.to_agent):
                raise ValueError(f"unknown target: {handoff.to_agent}")
            return handoff.to_agent
        for edge in self._reg.edges_from(handoff.from_agent):
            if edge.get("auto") is True:
                return edge["to"]
            cond = edge.get("when")
            if cond and self._eval(cond, handoff.payload):
                return edge["to"]
        if self._reg.manager:
            return self._reg.manager
        raise ValueError("no edge match and no manager")

    def _audit(self, handoff: Handoff, outcome: str) -> None:
        if self._conn is None:
            return
        record_handoff(self._conn, handoff, outcome, session_id=self._session_id)

    @staticmethod
    def _eval(expr: str, payload: dict[str, Any]) -> bool:
        """Safe AST-walker for `when:` edge conditions.

        Allowed: comparisons, bool ops, unary not, attribute access on `task`,
        identifier `task`, literals (str/int/float/bool/None), tuples, lists.
        Anything else (Call, Subscript, dunders, imports) raises and edge fails closed.

        TEAM_PACK.md may be pip-installed from third-party packages, so `eval` is
        not safe even with cleared builtins (`__class__` traversal escapes).
        """
        try:
            tree = ast.parse(expr, mode="eval")
            return bool(_safe_eval(tree.body, {"task": _Box(payload.get("task", {}))}))
        except Exception:
            return False


_ALLOWED_CMP_OPS = (ast.Eq, ast.NotEq, ast.Lt, ast.LtE, ast.Gt, ast.GtE, ast.In, ast.NotIn)


class _Box:
    """Read-only attribute-access wrapper for nested dict payloads."""
    __slots__ = ("_d",)

    def __init__(self, d: dict[str, Any]) -> None:
        object.__setattr__(self, "_d", d)

    def __getattr__(self, name: str) -> Any:
        if name.startswith("_"):
            raise AttributeError(name)
        if name not in self._d:
            raise AttributeError(name)
        v = self._d[name]
        return _Box(v) if isinstance(v, dict) else v


def _safe_eval(node: ast.AST, env: dict[str, Any]) -> Any:
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.Name):
        if node.id not in env:
            raise ValueError(f"name not allowed: {node.id}")
        return env[node.id]
    if isinstance(node, ast.Attribute):
        if node.attr.startswith("_"):
            raise ValueError(f"dunder access blocked: {node.attr}")
        return getattr(_safe_eval(node.value, env), node.attr)
    if isinstance(node, ast.Compare):
        left = _safe_eval(node.left, env)
        for op, right_node in zip(node.ops, node.comparators):
            if not isinstance(op, _ALLOWED_CMP_OPS):
                raise ValueError(f"op not allowed: {type(op).__name__}")
            right = _safe_eval(right_node, env)
            ok = _apply_cmp(op, left, right)
            if not ok:
                return False
            left = right
        return True
    if isinstance(node, ast.BoolOp):
        vals = [_safe_eval(v, env) for v in node.values]
        if isinstance(node.op, ast.And):
            return all(vals)
        if isinstance(node.op, ast.Or):
            return any(vals)
        raise ValueError("bool op not allowed")
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
        return not _safe_eval(node.operand, env)
    if isinstance(node, ast.Tuple):
        return tuple(_safe_eval(e, env) for e in node.elts)
    if isinstance(node, ast.List):
        return [_safe_eval(e, env) for e in node.elts]
    raise ValueError(f"node not allowed: {type(node).__name__}")


def _apply_cmp(op: ast.cmpop, left: Any, right: Any) -> bool:
    if isinstance(op, ast.Eq):
        return left == right
    if isinstance(op, ast.NotEq):
        return left != right
    if isinstance(op, ast.Lt):
        return left < right
    if isinstance(op, ast.LtE):
        return left <= right
    if isinstance(op, ast.Gt):
        return left > right
    if isinstance(op, ast.GtE):
        return left >= right
    if isinstance(op, ast.In):
        return left in right
    if isinstance(op, ast.NotIn):
        return left not in right
    raise ValueError(f"op not handled: {type(op).__name__}")
