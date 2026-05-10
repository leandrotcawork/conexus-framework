import enum
import inspect
from typing import Any, Literal, get_args, get_origin, get_type_hints


def _is_optional(annotation: Any) -> bool:
    origin = get_origin(annotation)
    if origin is None:
        return False
    args = get_args(annotation)
    return any(arg is type(None) for arg in args)


def _unwrap_optional(annotation: Any) -> Any:
    if not _is_optional(annotation):
        return annotation
    args = [arg for arg in get_args(annotation) if arg is not type(None)]
    return args[0] if args else Any


def _type_to_schema(annotation: Any) -> dict:
    annotation = _unwrap_optional(annotation)
    origin = get_origin(annotation)

    if annotation is str:
        return {"type": "string"}
    if annotation is int:
        return {"type": "integer"}
    if annotation is bool:
        return {"type": "boolean"}
    if annotation is float:
        return {"type": "number"}

    if origin is list:
        args = get_args(annotation)
        item_type = args[0] if args else Any
        return {"type": "array", "items": _type_to_schema(item_type)}

    if origin is Literal:
        return {"type": "string", "enum": [str(v) for v in get_args(annotation)]}

    if isinstance(annotation, type) and issubclass(annotation, enum.Enum):
        return {"type": "string", "enum": [m.value for m in annotation]}

    if origin is dict:
        args = get_args(annotation)
        value_type = args[1] if len(args) >= 2 else Any
        return {
            "type": "object",
            "additionalProperties": {} if value_type is Any else _type_to_schema(value_type),
        }

    if annotation is Any:
        return {}

    raise TypeError(f"schema_gen: unsupported type {annotation!r}")


def _deep_merge(base: dict, override: dict) -> dict:
    merged = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def generate_tool_schemas(cls: type, tool_names: list[str]) -> list[dict]:
    tool_meta = getattr(cls, "_tool_schemas", {}) or {}
    schemas: list[dict] = []

    for tool_name in tool_names:
        method = getattr(cls, tool_name)
        signature = inspect.signature(method)
        hints = get_type_hints(method)
        meta = tool_meta.get(tool_name, {})
        param_overrides = meta.get("params", {})

        properties: dict[str, dict] = {}
        required: list[str] = []

        for param_name, param in signature.parameters.items():
            if param_name == "self":
                continue

            annotation = hints.get(param_name, str)
            schema = _type_to_schema(annotation)
            override = param_overrides.get(param_name, {})
            schema = _deep_merge(schema, override)
            properties[param_name] = schema

            optional = _is_optional(annotation)
            has_default = param.default is not inspect.Parameter.empty
            if not has_default and not optional:
                required.append(param_name)

        parameters = {"type": "object", "properties": properties or {}}
        if required:
            parameters["required"] = required

        schemas.append(
            {
                "type": "function",
                "function": {
                    "name": tool_name,
                    "description": meta.get("description", ""),
                    "parameters": parameters,
                },
            }
        )

    return schemas
