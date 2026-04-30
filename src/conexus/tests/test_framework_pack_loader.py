# src/conexus/tests/test_framework_pack_loader.py
import json
import pytest
from conexus.core.skills.pack_loader import parse_skill_pack, SkillPackBackend
from conexus.core.config.skill_loader import parse_skill_file
from conexus.core.skills.skill_resolver import SkillLoader
from conexus.core.agent_registry import AgentRegistry

PACK_MD = """---
name: wiki
version: 1.0.0
backend: python
capabilities: [wiki_read, wiki_write]
data_classes:
  wiki_read: private_read
  wiki_write: external_write
budget_hint_usd: 0.01
prompts:
  - fragments/usage.md
---
Wiki skill body.
"""

def test_parse_skill_pack(tmp_path):
    (tmp_path / "SKILL_PACK.md").write_text(PACK_MD)
    doc = parse_skill_pack(tmp_path / "SKILL_PACK.md")
    assert doc.frontmatter.name == "wiki"
    assert doc.frontmatter.version == "1.0.0"
    assert doc.frontmatter.backend == SkillPackBackend.python
    assert doc.frontmatter.data_classes == {"wiki_read": "private_read", "wiki_write": "external_write"}
    assert doc.body.strip() == "Wiki skill body."
    assert doc.pack_dir == tmp_path

def test_parse_skill_pack_missing_frontmatter(tmp_path):
    (tmp_path / "SKILL_PACK.md").write_text("no frontmatter here")
    with pytest.raises(ValueError, match="missing YAML frontmatter"):
        parse_skill_pack(tmp_path / "SKILL_PACK.md")

SKILL_WITH_SKILLS = """---
name: ana
role: secretary
goal: help
tools: [wiki_read]
llm:
  provider: anthropic
  model: claude-sonnet-4-5
skills:
  - wiki@1.0.0
  - web-search@0.3.0
---
Body.
"""

def test_skill_frontmatter_skills_field(tmp_path):
    (tmp_path / "SKILL.md").write_text(SKILL_WITH_SKILLS)
    doc = parse_skill_file(tmp_path / "SKILL.md")
    assert doc.frontmatter.skills == ["wiki@1.0.0", "web-search@0.3.0"]

def test_skill_frontmatter_skills_optional(tmp_path):
    no_skills = SKILL_WITH_SKILLS.replace("skills:\n  - wiki@1.0.0\n  - web-search@0.3.0\n", "")
    (tmp_path / "SKILL.md").write_text(no_skills)
    doc = parse_skill_file(tmp_path / "SKILL.md")
    assert doc.frontmatter.skills == []


PACK_TOOLS = """
class WikiSkillTools:
    def wiki_search(self, query: str) -> list:
        return [{"result": query}]
    def wiki_read(self, path: str) -> str:
        return f"content of {path}"
"""

def _make_wiki_pack(tmp_path):
    pack_dir = tmp_path / "skills" / "wiki"
    pack_dir.mkdir(parents=True)
    (pack_dir / "SKILL_PACK.md").write_text(
        "---\nname: wiki\nversion: 1.0.0\nbackend: python\ncapabilities: [wiki_search, wiki_read]\n"
        "data_classes:\n  wiki_search: private_read\n  wiki_read: private_read\n---\nWiki fragment.\n"
    )
    (pack_dir / "tools.py").write_text(PACK_TOOLS)
    return pack_dir

def test_skill_loader_loads_pack(tmp_path):
    _make_wiki_pack(tmp_path)
    registry = AgentRegistry()
    loader = SkillLoader(agent_dir=tmp_path, registry=registry, agent_name="bot")
    extra_prompt, tool_tags = loader.load(["wiki@1.0.0"])
    assert "Wiki fragment." in extra_prompt
    assert "wiki_search" in tool_tags
    assert tool_tags["wiki_search"] == "private_read"

@pytest.mark.asyncio
async def test_skill_loader_registers_tools(tmp_path):
    _make_wiki_pack(tmp_path)
    registry = AgentRegistry()
    loader = SkillLoader(agent_dir=tmp_path, registry=registry, agent_name="bot")
    loader.load(["wiki@1.0.0"])
    result = await registry.execute_tool("bot", "wiki_search", {"query": "hello"})
    assert json.loads(result) == [{"result": "hello"}]

def test_skill_loader_missing_pack_raises(tmp_path):
    registry = AgentRegistry()
    loader = SkillLoader(agent_dir=tmp_path, registry=registry, agent_name="bot")
    with pytest.raises(FileNotFoundError, match="SKILL_PACK.md"):
        loader.load(["missing@0.1.0"])


PACK_TOOLS_WITH_IMPORT = """
from collections import OrderedDict

class WikiSkillTools:
    def wiki_search(self, query: str) -> list:
        return [{"result": query}]
"""

@pytest.mark.asyncio
async def test_skill_loader_ignores_imported_classes(tmp_path):
    pack_dir = tmp_path / "skills" / "wiki"
    pack_dir.mkdir(parents=True)
    (pack_dir / "SKILL_PACK.md").write_text(
        "---\nname: wiki\nversion: 1.0.0\nbackend: python\ncapabilities: [wiki_search]\n"
        "data_classes:\n  wiki_search: private_read\n---\nWiki.\n"
    )
    (pack_dir / "tools.py").write_text(PACK_TOOLS_WITH_IMPORT)
    registry = AgentRegistry()
    loader = SkillLoader(agent_dir=tmp_path, registry=registry, agent_name="bot")
    loader.load(["wiki@1.0.0"])
    result = await registry.execute_tool("bot", "wiki_search", {"query": "x"})
    assert json.loads(result) == [{"result": "x"}]


@pytest.mark.asyncio
async def test_skill_loader_lifecycle_no_mcp(tmp_path):
    """start_all/stop_all must be safe when no mcp backends loaded."""
    _make_wiki_pack(tmp_path)
    registry = AgentRegistry()
    loader = SkillLoader(agent_dir=tmp_path, registry=registry, agent_name="bot")
    loader.load(["wiki@1.0.0"])
    await loader.start_all()
    await loader.stop_all()


@pytest.mark.asyncio
async def test_skill_loader_lifecycle_starts_mcp(tmp_path):
    import sys
    pack_dir = tmp_path / "skills" / "echo"
    pack_dir.mkdir(parents=True)
    (pack_dir / "SKILL_PACK.md").write_text(
        "---\nname: echo\nversion: 1.0.0\nbackend: mcp-stdio\ncapabilities: [echo]\n"
        "data_classes:\n  echo: safe\n---\nEcho.\n"
    )
    server_script = tmp_path / "echo_server.py"
    server_script.write_text(
        "import sys, json\n"
        "def respond(id, result):\n"
        "    sys.stdout.write(json.dumps({'jsonrpc':'2.0','id':id,'result':result}) + '\\n')\n"
        "    sys.stdout.flush()\n"
        "for line in sys.stdin:\n"
        "    req = json.loads(line.strip())\n"
        "    if req['method'] == 'initialize':\n"
        "        respond(req['id'], {'protocolVersion':'2024-11-05','capabilities':{},'serverInfo':{'name':'e','version':'0.1.0'}})\n"
        "    elif req['method'] == 'tools/call':\n"
        "        respond(req['id'], {'content':[{'type':'text','text':req['params']['arguments']['msg']}]})\n"
    )
    (pack_dir / "mcp.json").write_text(
        json.dumps({"command": [sys.executable, str(server_script)]})
    )
    registry = AgentRegistry()
    loader = SkillLoader(agent_dir=tmp_path, registry=registry, agent_name="bot")
    loader.load(["echo@1.0.0"])
    await loader.start_all()
    try:
        result = await registry.execute_tool("bot", "echo", {"msg": "hi"})
        assert "hi" in result
    finally:
        await loader.stop_all()
