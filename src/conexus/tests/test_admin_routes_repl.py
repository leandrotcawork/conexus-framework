from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from conexus.web.admin.app import make_admin_app


def _seed(root: Path, name: str = "ana") -> None:
    d = root / name
    d.mkdir(parents=True)
    (d / "__init__.py").write_text("")
    (d / "SKILL.md").write_text(
        "---\n"
        f"name: {name}\nrole: test\ngoal: |\n  x\n"
        "llm:\n  provider: openai\n  model: gpt-4o-mini\n"
        "tools: []\n---\nbody"
    )
    (d / "tools.py").write_text(
        "class T:\n    pass\n\ndef create_cli_tools(d):\n    return None, T()\n"
    )


def test_repl_post_returns_partial(tmp_path: Path) -> None:
    _seed(tmp_path)
    app = make_admin_app(agents_dir=tmp_path, data_dir=tmp_path)
    client = TestClient(app)

    async def fake_run(*a, **kw):  # noqa: ARG001
        return "hello back"

    with patch("conexus.web.admin.routes.repl.run_one_message", new=fake_run):
        resp = client.post("/admin/agents/ana/test", data={"message": "hi"})
    assert resp.status_code == 200
    assert "hello back" in resp.text
