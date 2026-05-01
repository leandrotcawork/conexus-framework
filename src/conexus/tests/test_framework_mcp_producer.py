"""MCPProducer §9 acceptance: tool + wiki:// resource + bearer auth round-trip."""
from __future__ import annotations
import asyncio
import pytest
from conexus.core.mcp.producer import (
    build_mcp_producer,
    check_bearer,
    BearerError,
)


def test_producer_exposes_wiki_search_tool(tmp_path):
    server = build_mcp_producer(wiki_root=str(tmp_path), bearer_token="t")
    tool_names = {t.name for t in asyncio.run(server.list_tools())}
    assert "wiki_search" in tool_names


def test_producer_exposes_wiki_resource(tmp_path):
    """wiki:// resource template must be registered per spec §1.7."""
    (tmp_path / "page.md").write_text("hello world", encoding="utf-8")
    server = build_mcp_producer(wiki_root=str(tmp_path), bearer_token="t")
    templates = asyncio.run(server.list_resource_templates())
    uris = {str(t.uri_template) for t in templates}
    assert any(u.startswith("wiki://") for u in uris)


def test_producer_requires_bearer_token():
    with pytest.raises(ValueError):
        build_mcp_producer(wiki_root="/tmp", bearer_token="")


def test_check_bearer_accepts_correct_token():
    check_bearer("Bearer abc", expected="abc")  # no raise


def test_check_bearer_rejects_missing():
    with pytest.raises(BearerError):
        check_bearer(None, expected="abc")


def test_check_bearer_rejects_wrong_scheme():
    with pytest.raises(BearerError):
        check_bearer("Basic abc", expected="abc")


def test_check_bearer_rejects_wrong_token():
    with pytest.raises(BearerError):
        check_bearer("Bearer wrong", expected="abc")


def test_check_bearer_constant_time():
    """check_bearer must use compare_digest (smoke check)."""
    with pytest.raises(BearerError):
        check_bearer("Bearer wrong1", expected="rightxxxxxxxx")
    with pytest.raises(BearerError):
        check_bearer("Bearer wrong2", expected="rightxxxxxxxx")


def test_verify_bearer_tool_round_trip(tmp_path):
    """End-to-end: client invokes verify_bearer tool with valid + invalid tokens."""
    server = build_mcp_producer(wiki_root=str(tmp_path), bearer_token="secret-abc")
    tools = {t.name: t for t in asyncio.run(server.list_tools())}
    assert "verify_bearer" in tools

    result = asyncio.run(server.call_tool("verify_bearer", {"token": "secret-abc"}))
    assert result is not None

    with pytest.raises(Exception):
        asyncio.run(server.call_tool("verify_bearer", {"token": "wrong"}))
