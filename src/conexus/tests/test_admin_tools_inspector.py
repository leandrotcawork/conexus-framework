from pathlib import Path

from conexus.web.admin.services.tools_inspector import ToolMethod, scan_tools_file


SAMPLE = '''
class Tools:
    """Doc."""
    _tool_schemas = {
        "list_items": {"description": "List items.", "params": {}}
    }

    def list_items(self, limit: int = 10) -> list[dict]:
        """List items."""
        return []

    def _internal(self) -> None:
        """Hidden."""

    @staticmethod
    def helper() -> str:
        return "x"


def create_cli_tools(d):
    return None, Tools()
'''


def test_scan_returns_public_instance_methods(tmp_path: Path) -> None:
    p = tmp_path / "tools.py"
    p.write_text(SAMPLE)
    methods = scan_tools_file(p)
    names = [m.name for m in methods]
    assert "list_items" in names
    assert "_internal" not in names
    assert "create_cli_tools" not in names


def test_method_has_description_from_schema(tmp_path: Path) -> None:
    p = tmp_path / "tools.py"
    p.write_text(SAMPLE)
    methods = {m.name: m for m in scan_tools_file(p)}
    assert isinstance(methods["list_items"], ToolMethod)
    assert methods["list_items"].description == "List items."
