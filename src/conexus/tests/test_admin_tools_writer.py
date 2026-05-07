from pathlib import Path

from conexus.web.admin.services.tools_writer import write_tool_schemas


SAMPLE = '''class Tools:
    """Doc."""
    _tool_schemas = {
        "foo": {"description": "Old.", "params": {}}
    }

    def foo(self) -> dict:
        return {}


def create_cli_tools(d):
    return None, Tools()
'''


def test_overwrites_schemas_block(tmp_path: Path) -> None:
    p = tmp_path / "tools.py"
    p.write_text(SAMPLE)
    write_tool_schemas(p, {"foo": {"description": "New desc.", "params": {}}})
    out = p.read_text()
    assert '"description": "New desc."' in out
    assert '"description": "Old."' not in out
    assert "def foo(self)" in out


def test_inserts_block_when_absent(tmp_path: Path) -> None:
    p = tmp_path / "tools.py"
    p.write_text(
        "class Tools:\n    def foo(self) -> dict: return {}\n\n"
        "def create_cli_tools(d): return None, Tools()\n"
    )
    write_tool_schemas(p, {"foo": {"description": "Hi.", "params": {}}})
    out = p.read_text()
    assert "_tool_schemas" in out
    assert '"description": "Hi."' in out
    assert out.count("_tool_schemas") == 1


ANNOTATED = '''from typing import ClassVar


class Tools:
    _tool_schemas: ClassVar[dict] = {
        "foo": {"description": "Old.", "params": {}}
    }

    def foo(self) -> dict:
        return {}


def create_cli_tools(d):
    return None, Tools()
'''


def test_overwrites_annotated_schemas(tmp_path: Path) -> None:
    """Templates emit `_tool_schemas: ClassVar[dict] = {...}` (ast.AnnAssign)."""
    p = tmp_path / "tools.py"
    p.write_text(ANNOTATED)
    write_tool_schemas(p, {"foo": {"description": "Fresh.", "params": {}}})
    out = p.read_text()
    assert out.count("_tool_schemas") == 1
    assert '"description": "Fresh."' in out
    assert '"description": "Old."' not in out
