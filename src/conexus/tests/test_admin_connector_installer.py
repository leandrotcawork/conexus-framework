import json
from pathlib import Path

from conexus.web.admin.services.connector_installer import install_connector
from conexus.web.admin.services.template_lib import scaffold_agent


def _registry(tmp_path: Path) -> Path:
    p = tmp_path / "registry.json"
    p.write_text(json.dumps({"version": "1.0", "connectors": [{
        "name": "notion", "version": "1.0", "server_url": "https://mcp.notion.so",
        "scopes": ["read"],
        "ui": {"label": "Notion", "icon": "📓", "category": "Docs", "description": "Notion."},
    }]}))
    return p


def test_install_writes_pack_and_appends_skill(tmp_path: Path) -> None:
    scaffold_agent(tmp_path, "ana", template="chat-only")
    install_connector(agents_dir=tmp_path, agent_name="ana",
                      connector_name="notion", registry_path=_registry(tmp_path))
    pack = tmp_path / "ana" / "skills" / "notion"
    assert (pack / "SKILL_PACK.md").exists()
    assert (pack / "connector.json").exists()
    skill_md = (tmp_path / "ana" / "SKILL.md").read_text()
    assert "notion@1.0" in skill_md


def test_install_idempotent_skill_ref(tmp_path: Path) -> None:
    scaffold_agent(tmp_path, "ana", template="chat-only")
    install_connector(agents_dir=tmp_path, agent_name="ana",
                      connector_name="notion", registry_path=_registry(tmp_path))
    install_connector(agents_dir=tmp_path, agent_name="ana",
                      connector_name="notion", registry_path=_registry(tmp_path))
    skill_md = (tmp_path / "ana" / "SKILL.md").read_text()
    assert skill_md.count("notion@1.0") == 1
