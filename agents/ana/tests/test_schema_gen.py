"""Snapshot-style tests for the schema auto-generator."""
from agents.ana.tools import AnaTools
from agents.pesquisador.tools import PesquisadorTools
from conexus.core.tools.schema_gen import generate_tool_schemas


def _find(schemas, name):
    return next((s for s in schemas if s["function"]["name"] == name), None)


ANA_TOOLS = [
    "calendar_list_events", "calendar_create_event", "calendar_update_event",
    "calendar_delete_event", "memory_get", "memory_set", "memory_list_facts",
    "todos_add", "todos_list", "todos_mark_done",
    "wiki_read", "wiki_list", "wiki_search", "wiki_write",
]

PESQ_TOOLS = [
    "wiki_read", "wiki_write", "wiki_search", "wiki_list",
    "web_search", "web_fetch", "youtube_transcript", "pdf_extract",
    "raw_save", "compile_article", "git_sync",
]


def test_ana_schema_count():
    schemas = generate_tool_schemas(AnaTools, ANA_TOOLS)
    assert len(schemas) == len(ANA_TOOLS)


def test_ana_calendar_list_required():
    schemas = generate_tool_schemas(AnaTools, ANA_TOOLS)
    fn = _find(schemas, "calendar_list_events")
    assert fn is not None
    assert set(fn["function"]["parameters"]["required"]) == {"start_iso", "end_iso"}
    assert fn["function"]["parameters"]["properties"]["start_iso"]["type"] == "string"


def test_ana_calendar_create_optional_force():
    schemas = generate_tool_schemas(AnaTools, ANA_TOOLS)
    fn = _find(schemas, "calendar_create_event")
    required = fn["function"]["parameters"]["required"]
    assert "title" in required
    assert "force" not in required
    assert fn["function"]["parameters"]["properties"]["force"]["type"] == "boolean"


def test_ana_todos_mark_done_integer():
    schemas = generate_tool_schemas(AnaTools, ANA_TOOLS)
    fn = _find(schemas, "todos_mark_done")
    assert fn["function"]["parameters"]["properties"]["id"]["type"] == "integer"
    assert "id" in fn["function"]["parameters"]["required"]


def test_ana_todos_list_enum():
    schemas = generate_tool_schemas(AnaTools, ANA_TOOLS)
    fn = _find(schemas, "todos_list")
    status = fn["function"]["parameters"]["properties"]["status"]
    assert status.get("enum") == ["open", "done", "all"]
    assert "status" not in fn["function"]["parameters"].get("required", [])


def test_pesq_compile_article_array_param():
    schemas = generate_tool_schemas(PesquisadorTools, PESQ_TOOLS)
    fn = _find(schemas, "compile_article")
    raw_paths = fn["function"]["parameters"]["properties"]["raw_paths"]
    assert raw_paths["type"] == "array"
    assert raw_paths["items"]["type"] == "string"
    assert "raw_paths" in fn["function"]["parameters"]["required"]


def test_pesq_web_search_optional_params():
    schemas = generate_tool_schemas(PesquisadorTools, PESQ_TOOLS)
    fn = _find(schemas, "web_search")
    required = fn["function"]["parameters"].get("required", [])
    assert "query" in required
    assert "max_results" not in required
    assert "tier" not in required


def test_schema_structure():
    schemas = generate_tool_schemas(AnaTools, ["calendar_list_events"])
    s = schemas[0]
    assert s["type"] == "function"
    assert "name" in s["function"]
    assert "description" in s["function"]
    assert s["function"]["parameters"]["type"] == "object"


def test_description_from_tool_schemas():
    schemas = generate_tool_schemas(AnaTools, ["calendar_list_events"])
    desc = schemas[0]["function"]["description"]
    assert "Google Calendar" in desc
