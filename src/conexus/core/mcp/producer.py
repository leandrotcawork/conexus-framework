"""MCPProducer — exposes Conexus capabilities as an MCP server.

Phase 9 scope: stdio transport + bearer-token gate + wiki_search tool +
wiki:// resource (per spec §1.7 + §9 acceptance). Streamable HTTP transport
and scope-based access control are deferred to a future hardening phase.
"""
from __future__ import annotations
import hmac
from pathlib import Path
from typing import Any

try:
    from fastmcp import FastMCP
except ImportError as exc:  # pragma: no cover
    raise ImportError("fastmcp not installed; run `uv sync`") from exc


class BearerError(Exception):
    """Raised when bearer header is missing or invalid."""


def check_bearer(authorization_header: str | None, *, expected: str) -> None:
    """Validate `Authorization: Bearer <expected>` header using constant-time compare.

    Raises BearerError on missing header, wrong scheme, or wrong token.
    """
    if not authorization_header:
        raise BearerError("missing Authorization header")
    parts = authorization_header.split(" ", 1)
    if len(parts) != 2 or parts[0] != "Bearer":
        raise BearerError("expected 'Bearer <token>' scheme")
    if not hmac.compare_digest(parts[1], expected):
        raise BearerError("invalid bearer token")


def build_mcp_producer(*, wiki_root: str, bearer_token: str) -> FastMCP:
    """Build MCPProducer server with wiki_search + wiki:// resource + verify_bearer tool.

    Stdio transport has no Authorization header, so bearer validation is exposed as
    a first-class MCP tool `verify_bearer(token)`. Clients call it after `initialize`.
    """
    if not bearer_token:
        raise ValueError("bearer_token must be non-empty")

    mcp = FastMCP("conexus")
    root = Path(wiki_root)

    @mcp.tool()
    def verify_bearer(token: str) -> dict[str, bool]:
        """Confirm client holds the correct bearer token. Returns {"ok": true} or raises."""
        check_bearer(f"Bearer {token}", expected=bearer_token)
        return {"ok": True}

    @mcp.tool()
    def wiki_search(query: str) -> list[dict[str, Any]]:
        """Search wiki markdown for literal `query`. Returns up to 20 hits."""
        hits: list[dict[str, Any]] = []
        if not root.exists():
            return hits
        for f in root.rglob("*.md"):
            try:
                text = f.read_text(encoding="utf-8")
            except Exception:
                continue
            if query in text:
                hits.append({"path": str(f.relative_to(root)), "size": len(text)})
                if len(hits) >= 20:
                    break
        return hits

    @mcp.resource("wiki://{path}")
    def wiki_page(path: str) -> str:
        """Return raw markdown of a wiki page by relative path. Sandboxed to wiki_root."""
        target = (root / path).resolve()
        if not str(target).startswith(str(root.resolve())):
            raise ValueError("path outside wiki_root")
        if not target.exists() or not target.is_file():
            raise FileNotFoundError(path)
        return target.read_text(encoding="utf-8")

    return mcp
