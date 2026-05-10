"""Unit tests for schema_gen._type_to_schema — Literal/Enum/dict/raise."""
import enum
from typing import Literal

import pytest

from conexus.core.tools.schema_gen import _type_to_schema


def test_literal_to_enum_schema():
    schema = _type_to_schema(Literal["low", "med", "high"])
    assert schema == {"type": "string", "enum": ["low", "med", "high"]}


def test_enum_to_enum_schema():
    class Tier(enum.Enum):
        LOW = "low"
        HIGH = "high"

    schema = _type_to_schema(Tier)
    assert schema == {"type": "string", "enum": ["low", "high"]}


def test_int_enum():
    class Priority(enum.IntEnum):
        LOW = 1
        HIGH = 2

    schema = _type_to_schema(Priority)
    assert schema == {"type": "string", "enum": [1, 2]}


def test_dict_to_object_schema():
    schema = _type_to_schema(dict[str, int])
    assert schema == {
        "type": "object",
        "additionalProperties": {"type": "integer"},
    }


def test_dict_any_value():
    from typing import Any
    schema = _type_to_schema(dict[str, Any])
    assert schema["type"] == "object"


def test_unknown_type_raises():
    class Custom:
        ...

    with pytest.raises(TypeError, match="unsupported type"):
        _type_to_schema(Custom)


def test_str_int_bool_float_unchanged():
    assert _type_to_schema(str) == {"type": "string"}
    assert _type_to_schema(int) == {"type": "integer"}
    assert _type_to_schema(bool) == {"type": "boolean"}
    assert _type_to_schema(float) == {"type": "number"}


def test_list_of_literal():
    schema = _type_to_schema(list[Literal["a", "b"]])
    assert schema == {
        "type": "array",
        "items": {"type": "string", "enum": ["a", "b"]},
    }


def test_optional_literal_unwrapped():
    from typing import Optional
    schema = _type_to_schema(Optional[Literal["x", "y"]])
    assert schema == {"type": "string", "enum": ["x", "y"]}
