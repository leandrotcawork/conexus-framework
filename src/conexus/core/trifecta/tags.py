"""DataClass enum and auto-tag heuristic for TrifectaGuard."""
from __future__ import annotations
import re
from enum import Enum


class DataClass(str, Enum):
    untrusted_read = "untrusted_read"
    private_read = "private_read"
    external_write = "external_write"
    safe = "safe"


_PATTERNS: list[tuple[DataClass, list[re.Pattern]]] = [
    (DataClass.untrusted_read, [
        re.compile(r"web_(fetch|search|browse|get)", re.I),
        re.compile(r"http_get", re.I),
        re.compile(r"read_(email|dm|message|feed)", re.I),
        re.compile(r"rss_", re.I),
    ]),
    (DataClass.private_read, [
        re.compile(r"wiki_(read|search|list)", re.I),
        re.compile(r"memory_get", re.I),
        re.compile(r"(db|sqlite)_read", re.I),
        re.compile(r"calendar_list", re.I),
        re.compile(r"todos_(list|get)", re.I),
        re.compile(r"memory_list", re.I),
    ]),
    (DataClass.external_write, [
        re.compile(r"wiki_(write|append|update)", re.I),
        re.compile(r"calendar_(create|update|delete)", re.I),
        re.compile(r"todos_(add|mark|delete)", re.I),
        re.compile(r"memory_set", re.I),
        re.compile(r"(send|post)_", re.I),
        re.compile(r"git_(push|commit|sync)", re.I),
        re.compile(r"delete_", re.I),
        re.compile(r"raw_save", re.I),
        re.compile(r"compile_article", re.I),
    ]),
]


def auto_tag(tool_name: str) -> DataClass | None:
    """Return DataClass for tool_name via heuristic, or None if unrecognised."""
    for dc, patterns in _PATTERNS:
        for pat in patterns:
            if pat.search(tool_name):
                return dc
    return None
