"""Tests for BuiltinTimeTools.get_current_time."""
from conexus.core.tools.builtin_time import BuiltinTimeTools


def test_get_current_time_shape():
    tools = BuiltinTimeTools()
    out = tools.get_current_time()
    assert set(out.keys()) == {"brt", "iso", "weekday"}
    assert "T" in out["iso"]
    assert out["weekday"] in {
        "Monday", "Tuesday", "Wednesday",
        "Thursday", "Friday", "Saturday", "Sunday",
    }


def test_brt_contains_timezone_marker():
    tools = BuiltinTimeTools()
    out = tools.get_current_time()
    # BRT or -03:00 offset present
    assert "BRT" in out["brt"] or "-03" in out["iso"] or "-04" in out["iso"]


def test_tool_schema_exposed():
    assert "get_current_time" in BuiltinTimeTools._tool_schemas
    schema = BuiltinTimeTools._tool_schemas["get_current_time"]
    assert "description" in schema
    assert "Call when" in schema["description"]
