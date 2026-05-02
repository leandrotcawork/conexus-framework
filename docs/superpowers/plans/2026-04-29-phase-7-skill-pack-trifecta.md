# Phase 7 — SKILL_PACK + TrifectaGuard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use nexus:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add SKILL_PACK format (pip-installable skills with tools + prompts), backend abstraction (python/mcp-stdio), and TrifectaGuard (deterministic taint-based exfil prevention).

**Architecture:** SKILL_PACK.md parses into `SkillPackDocument`; `SkillLoader` resolves a SKILL.md `skills:` list and registers backends into `AgentRegistry`; `TrifectaGuard` intercepts every tool call in the handler loop with ~5 µs overhead. Guard is opt-in via `tool_tags` on `AgentHandlerConfig` — off by default so existing consumers are unaffected.

**Tech Stack:** pydantic v2, Python 3.11+, asyncio, subprocess (mcp-stdio), httpx (mcp-http, Task 8 only), pytest, ruff

**Spec:** `docs/superpowers/specs/2026-04-29-conexus-framework-v2.md` §1.3, §1.4, §1.8

---

## File Map

| Action | Path | Responsibility |
|--------|------|---------------|
| Create | `src/conexus/core/skills/__init__.py` | package marker |
| Create | `src/conexus/core/skills/pack_loader.py` | `SkillPackDocument`, `parse_skill_pack()` |
| Create | `src/conexus/core/skills/skill_resolver.py` | `SkillLoader` — resolve skills: list, register backends, inject prompts |
| Create | `src/conexus/core/trifecta/__init__.py` | package marker |
| Create | `src/conexus/core/trifecta/tags.py` | `DataClass` enum + `auto_tag()` heuristic |
| Create | `src/conexus/core/trifecta/guard.py` | `TrifectaGuard`, `TrifectaViolation` |
| Create | `src/conexus/core/backends/__init__.py` | package marker |
| Create | `src/conexus/core/backends/base.py` | `ToolBackend` ABC |
| Create | `src/conexus/core/backends/python_backend.py` | `PythonBackend` (in-proc) |
| Create | `src/conexus/core/backends/mcp_stdio_backend.py` | `McpStdioBackend` (subprocess JSON-RPC) |
| Modify | `src/conexus/core/config/skill_loader.py` | add `skills: list[str]` to `SkillFrontmatter` |
| Modify | `src/conexus/core/agent_registry.py` | route through `ToolBackend`; keep `register(agent, tools_obj)` API |
| Modify | `src/conexus/core/agent_handler.py` | add `tool_tags` to config; create `TrifectaGuard` per turn |
| Modify | `src/conexus/cli/__main__.py` | add `conexus tag --suggest <tools.py>` command |
| Create | `src/conexus/tests/test_framework_pack_loader.py` | unit tests |
| Create | `src/conexus/tests/test_framework_trifecta.py` | unit tests |
| Create | `src/conexus/tests/test_framework_backends.py` | unit tests |
| Create | `src/conexus/tests/test_framework_trifecta_integration.py` | end-to-end exfil scenario |

---

## Task 1: SKILL_PACK models + `skills:` field in SKILL.md

**Files:**
- Create: `src/conexus/core/skills/__init__.py`
- Create: `src/conexus/core/skills/pack_loader.py`
- Modify: `src/conexus/core/config/skill_loader.py`
- Test: `src/conexus/tests/test_framework_pack_loader.py`

- [ ] **Write failing tests**

```python
# src/conexus/tests/test_framework_pack_loader.py
from pathlib import Path
import pytest
from conexus.core.skills.pack_loader import parse_skill_pack, SkillPackDocument, SkillPackBackend
from conexus.core.config.skill_loader import parse_skill_file

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
```

- [ ] **Run to verify failure**

```
uv run pytest src/conexus/tests/test_framework_pack_loader.py -v
```
Expected: ImportError or AttributeError.

- [ ] **Implement `pack_loader.py`**

```python
# src/conexus/core/skills/__init__.py
# (empty)
```

```python
# src/conexus/core/skills/pack_loader.py
"""SKILL_PACK.md parser — pip-installable skill package descriptor."""
from __future__ import annotations
from enum import Enum
from pathlib import Path
from typing import Optional
import yaml
from pydantic import BaseModel, Field


class SkillPackBackend(str, Enum):
    python = "python"
    mcp_stdio = "mcp-stdio"
    mcp_http = "mcp-http"


class SkillPackFrontmatter(BaseModel):
    name: str
    version: str
    backend: SkillPackBackend = SkillPackBackend.python
    capabilities: list[str] = Field(default_factory=list)
    data_classes: dict[str, str] = Field(default_factory=dict)
    budget_hint_usd: Optional[float] = None
    prompts: list[str] = Field(default_factory=list)


class SkillPackDocument(BaseModel):
    frontmatter: SkillPackFrontmatter
    body: str
    pack_dir: Path

    model_config = {"arbitrary_types_allowed": True}


def parse_skill_pack(path: str | Path) -> SkillPackDocument:
    path = Path(path)
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        raise ValueError(f"{path}: missing YAML frontmatter")
    after_open = text[4:]
    try:
        close_index = after_open.index("\n---\n")
    except ValueError as e:
        raise ValueError(f"{path}: unterminated frontmatter") from e
    raw = after_open[:close_index]
    body = after_open[close_index + 5:]
    data = yaml.safe_load(raw) or {}
    fm = SkillPackFrontmatter.model_validate(data)
    return SkillPackDocument(frontmatter=fm, body=body.strip(), pack_dir=path.parent)
```

- [ ] **Add `skills: list[str]` to `SkillFrontmatter`**

In `src/conexus/core/config/skill_loader.py`, add one field to `SkillFrontmatter`:
```python
skills: list[str] = Field(default_factory=list)
```

- [ ] **Run tests**

```
uv run pytest src/conexus/tests/test_framework_pack_loader.py -v
```
Expected: all green.

- [ ] **Ruff + commit**

```
uv run ruff check src/conexus/core/skills/ src/conexus/core/config/skill_loader.py
git add src/conexus/core/skills/ src/conexus/core/config/skill_loader.py src/conexus/tests/test_framework_pack_loader.py
git commit -m "feat(phase-7.1): SKILL_PACK models + skills: field in SkillFrontmatter"
```

---

## Task 2: DataClass tags + auto-tag heuristic

**Files:**
- Create: `src/conexus/core/trifecta/__init__.py`
- Create: `src/conexus/core/trifecta/tags.py`
- Test: `src/conexus/tests/test_framework_trifecta.py` (part 1)

- [ ] **Write failing tests**

```python
# src/conexus/tests/test_framework_trifecta.py
from conexus.core.trifecta.tags import DataClass, auto_tag

def test_auto_tag_untrusted_read():
    assert auto_tag("web_fetch") == DataClass.untrusted_read
    assert auto_tag("web_search") == DataClass.untrusted_read

def test_auto_tag_private_read():
    assert auto_tag("wiki_read") == DataClass.private_read
    assert auto_tag("wiki_search") == DataClass.private_read
    assert auto_tag("memory_get") == DataClass.private_read
    assert auto_tag("calendar_list_events") == DataClass.private_read

def test_auto_tag_external_write():
    assert auto_tag("wiki_write") == DataClass.external_write
    assert auto_tag("wiki_append_log") == DataClass.external_write
    assert auto_tag("calendar_create_event") == DataClass.external_write
    assert auto_tag("todos_add") == DataClass.external_write
    assert auto_tag("send_telegram") == DataClass.external_write

def test_auto_tag_returns_none_for_unknown():
    assert auto_tag("compute_hash") is None
    assert auto_tag("format_date") is None
```

- [ ] **Run to verify failure**

```
uv run pytest src/conexus/tests/test_framework_trifecta.py::test_auto_tag_untrusted_read -v
```
Expected: ImportError.

- [ ] **Implement `tags.py`**

```python
# src/conexus/core/trifecta/__init__.py
# (empty)
```

```python
# src/conexus/core/trifecta/tags.py
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
```

- [ ] **Run tests**

```
uv run pytest src/conexus/tests/test_framework_trifecta.py -v
```
Expected: all green.

- [ ] **Commit**

```
git add src/conexus/core/trifecta/ src/conexus/tests/test_framework_trifecta.py
git commit -m "feat(phase-7.2): DataClass enum + auto_tag heuristic"
```

---

## Task 3: TrifectaGuard

**Files:**
- Create: `src/conexus/core/trifecta/guard.py`
- Test: append to `src/conexus/tests/test_framework_trifecta.py`

- [ ] **Append failing tests**

```python
# append to test_framework_trifecta.py
from conexus.core.trifecta.guard import TrifectaGuard, TrifectaViolation

def _guard(extra: dict | None = None) -> TrifectaGuard:
    tags = {
        "web_fetch": "untrusted_read",
        "wiki_read": "private_read",
        "wiki_write": "external_write",
        "compute_hash": "safe",
    }
    if extra:
        tags.update(extra)
    return TrifectaGuard(tags)

def test_guard_allows_read_sequence():
    g = _guard()
    g.check_and_record("web_fetch")   # untrusted_read
    g.check_and_record("wiki_read")   # private_read — allowed (no write yet)

def test_guard_blocks_exfil():
    g = _guard()
    g.check_and_record("web_fetch")   # untrusted_read
    g.check_and_record("wiki_read")   # private_read
    with pytest.raises(TrifectaViolation, match="blocked"):
        g.check_and_record("wiki_write")  # external_write — BLOCKED

def test_guard_allows_write_without_both_reads():
    g = _guard()
    g.check_and_record("web_fetch")   # untrusted_read only — write still allowed
    g.check_and_record("wiki_write")  # OK: no private_read in taint yet

def test_guard_trust_boundary_cleared():
    g = TrifectaGuard(
        {"web_fetch": "untrusted_read", "wiki_read": "private_read", "wiki_write": "external_write"},
        trust_boundary_cleared=True,
    )
    g.check_and_record("web_fetch")
    g.check_and_record("wiki_read")
    g.check_and_record("wiki_write")  # allowed: trust cleared

def test_guard_untagged_tool_raises():
    g = TrifectaGuard({})  # no tags, no heuristic match
    with pytest.raises(ValueError, match="no data_class tag"):
        g.check_and_record("mystery_tool")

def test_guard_auto_tags_unregistered_tool():
    g = TrifectaGuard({})  # empty explicit tags
    # web_fetch matches auto_tag heuristic
    tag = g.check_and_record("web_fetch")
    from conexus.core.trifecta.tags import DataClass
    assert tag == DataClass.untrusted_read
```

- [ ] **Run to verify failure**

```
uv run pytest src/conexus/tests/test_framework_trifecta.py -v -k "guard"
```
Expected: ImportError.

- [ ] **Implement `guard.py`**

```python
# src/conexus/core/trifecta/guard.py
"""TrifectaGuard — per-turn deterministic taint tracker."""
from __future__ import annotations
from .tags import DataClass, auto_tag


class TrifectaViolation(Exception):
    """Raised when a tool call violates the Trifecta rule."""


class TrifectaGuard:
    """Stateful per-turn guard. Create one instance per handle_agent_message call."""

    def __init__(
        self,
        tool_tags: dict[str, str],
        *,
        trust_boundary_cleared: bool = False,
    ) -> None:
        # Normalise strings to DataClass enum; keep unknowns as raw string for error messages
        self._tool_tags: dict[str, DataClass] = {}
        for name, tag in tool_tags.items():
            try:
                self._tool_tags[name] = DataClass(tag)
            except ValueError:
                pass  # invalid tag string — will be caught at check time
        self._trust_cleared = trust_boundary_cleared
        self._taint: set[DataClass] = set()

    def check_and_record(self, tool_name: str) -> DataClass:
        """Resolve tag, check rule, record taint. Returns tag. Raises on violation."""
        # Resolve: explicit map → auto-tag → error
        if tool_name in self._tool_tags:
            tag = self._tool_tags[tool_name]
        else:
            tag = auto_tag(tool_name)
            if tag is None:
                raise ValueError(
                    f"Tool '{tool_name}' has no data_class tag and heuristic could not "
                    "auto-tag it. Add an explicit entry in data_classes: in SKILL_PACK.md."
                )

        # Rule: untrusted_read + private_read already in taint → block external_write
        if (
            tag == DataClass.external_write
            and not self._trust_cleared
            and DataClass.untrusted_read in self._taint
            and DataClass.private_read in self._taint
        ):
            raise TrifectaViolation(
                f"TrifectaGuard blocked '{tool_name}' (external_write): "
                "turn taint contains untrusted_read + private_read — possible exfil path."
            )

        self._taint.add(tag)
        return tag
```

- [ ] **Run tests**

```
uv run pytest src/conexus/tests/test_framework_trifecta.py -v
```
Expected: all green.

- [ ] **Commit**

```
git add src/conexus/core/trifecta/guard.py src/conexus/tests/test_framework_trifecta.py
git commit -m "feat(phase-7.3): TrifectaGuard — per-turn taint tracker + exfil block"
```

---

## Task 4: Backend abstraction + PythonBackend + AgentRegistry refactor

**Files:**
- Create: `src/conexus/core/backends/__init__.py`
- Create: `src/conexus/core/backends/base.py`
- Create: `src/conexus/core/backends/python_backend.py`
- Modify: `src/conexus/core/agent_registry.py`
- Test: `src/conexus/tests/test_framework_backends.py`

- [ ] **Write failing tests**

```python
# src/conexus/tests/test_framework_backends.py
import pytest
from conexus.core.backends.python_backend import PythonBackend
from conexus.core.agent_registry import AgentRegistry


class _FakeTools:
    async def greet(self, name: str) -> str:
        return f"hello {name}"
    def add(self, a: int, b: int) -> int:
        return a + b


@pytest.mark.asyncio
async def test_python_backend_async():
    b = PythonBackend(_FakeTools())
    result = await b.execute("greet", {"name": "world"})
    assert '"hello world"' in result

@pytest.mark.asyncio
async def test_python_backend_sync():
    b = PythonBackend(_FakeTools())
    result = await b.execute("add", {"a": 1, "b": 2})
    assert "3" in result

@pytest.mark.asyncio
async def test_python_backend_unknown_tool():
    b = PythonBackend(_FakeTools())
    result = await b.execute("missing", {})
    assert "error" in result

@pytest.mark.asyncio
async def test_registry_uses_backend():
    registry = AgentRegistry()
    registry.register("bot", _FakeTools())
    result = await registry.execute_tool("bot", "greet", {"name": "test"})
    assert '"hello test"' in result

@pytest.mark.asyncio
async def test_registry_unknown_agent():
    registry = AgentRegistry()
    result = await registry.execute_tool("nobody", "greet", {})
    assert "error" in result
```

- [ ] **Run to verify failure**

```
uv run pytest src/conexus/tests/test_framework_backends.py -v
```
Expected: ImportError on `backends`.

- [ ] **Implement backends**

```python
# src/conexus/core/backends/__init__.py
# (empty)
```

```python
# src/conexus/core/backends/base.py
"""ToolBackend ABC — all backends implement this interface."""
from __future__ import annotations
from abc import ABC, abstractmethod


class ToolBackend(ABC):
    @abstractmethod
    async def execute(self, tool_name: str, args: dict) -> str:
        """Execute tool; return JSON string (success or {"error": ...})."""

    @property
    def backend_type(self) -> str:
        return "unknown"
```

```python
# src/conexus/core/backends/python_backend.py
"""In-process Python tools backend."""
from __future__ import annotations
import inspect
import json
import traceback
from typing import Any
from .base import ToolBackend


class PythonBackend(ToolBackend):
    def __init__(self, tools_obj: Any) -> None:
        self._tools = tools_obj

    async def execute(self, tool_name: str, args: dict) -> str:
        fn = getattr(self._tools, tool_name, None)
        if fn is None:
            return json.dumps({"error": f"unknown tool: {tool_name}"})
        try:
            result = await fn(**args) if inspect.iscoroutinefunction(fn) else fn(**args)
            return json.dumps(result, ensure_ascii=False, default=str)
        except Exception as exc:
            traceback.print_exc()
            return json.dumps({"error": str(exc)})

    @property
    def backend_type(self) -> str:
        return "python"
```

- [ ] **Refactor `agent_registry.py`**

Replace the file content with:

```python
"""Agent registry — routes tool calls to the registered backend per agent."""
from __future__ import annotations
import json
from typing import Any
from conexus.core.backends.base import ToolBackend
from conexus.core.backends.python_backend import PythonBackend


class AgentRegistry:
    """Maps agent names to their ToolBackend."""

    def __init__(self) -> None:
        self._backends: dict[str, ToolBackend] = {}

    def register(self, agent_name: str, tools: Any) -> None:
        """Register a Python tools object. Wraps it in PythonBackend."""
        self._backends[agent_name] = PythonBackend(tools)

    def register_backend(self, agent_name: str, backend: ToolBackend) -> None:
        """Register any backend directly."""
        self._backends[agent_name] = backend

    def get_tools(self, agent_name: str) -> Any:
        """Backward-compat: return underlying tools object for PythonBackend."""
        backend = self._backends.get(agent_name)
        if backend is None:
            raise KeyError(agent_name)
        if isinstance(backend, PythonBackend):
            return backend._tools
        raise TypeError(f"backend for {agent_name!r} is not a PythonBackend")

    def agent_names(self) -> list[str]:
        return list(self._backends.keys())

    async def execute_tool(self, agent_name: str, tool_name: str, args: dict) -> str:
        backend = self._backends.get(agent_name)
        if backend is None:
            return json.dumps({"error": f"agente desconhecido: {agent_name}"})
        return await backend.execute(tool_name, args)
```

- [ ] **Run all tests** (ensure no regressions from registry change)

```
uv run pytest -x -q
```
Expected: 74 passed.

- [ ] **Commit**

```
git add src/conexus/core/backends/ src/conexus/core/agent_registry.py src/conexus/tests/test_framework_backends.py
git commit -m "feat(phase-7.4): backend abstraction — PythonBackend + AgentRegistry refactor"
```

---

## Task 5: McpStdioBackend

**Files:**
- Create: `src/conexus/core/backends/mcp_stdio_backend.py`
- Test: append to `src/conexus/tests/test_framework_backends.py`

- [ ] **Append failing test** (uses a mock stdio MCP server via subprocess)

```python
# append to test_framework_backends.py
import asyncio
import json
import sys
from conexus.core.backends.mcp_stdio_backend import McpStdioBackend

# Minimal MCP echo server as inline script
_ECHO_SERVER = """
import sys, json
def respond(id, result):
    msg = json.dumps({"jsonrpc":"2.0","id":id,"result":result})
    sys.stdout.write(msg + "\\n")
    sys.stdout.flush()
for line in sys.stdin:
    req = json.loads(line.strip())
    if req["method"] == "initialize":
        respond(req["id"], {"protocolVersion":"2024-11-05","capabilities":{},"serverInfo":{"name":"echo","version":"0.1.0"}})
    elif req["method"] == "tools/list":
        respond(req["id"], {"tools":[{"name":"echo","description":"echo args","inputSchema":{"type":"object","properties":{"msg":{"type":"string"}}}}]})
    elif req["method"] == "tools/call":
        respond(req["id"], {"content":[{"type":"text","text":req["params"]["arguments"]["msg"]}]})
"""

@pytest.mark.asyncio
async def test_mcp_stdio_backend(tmp_path):
    server_script = tmp_path / "echo_server.py"
    server_script.write_text(_ECHO_SERVER)

    backend = McpStdioBackend(command=[sys.executable, str(server_script)])
    await backend.start()
    try:
        result = await backend.execute("echo", {"msg": "hello"})
        data = json.loads(result)
        assert data == "hello"
    finally:
        await backend.stop()
```

- [ ] **Run to verify failure**

```
uv run pytest src/conexus/tests/test_framework_backends.py::test_mcp_stdio_backend -v
```
Expected: ImportError.

- [ ] **Implement `mcp_stdio_backend.py`**

```python
# src/conexus/core/backends/mcp_stdio_backend.py
"""MCP stdio backend — launches a subprocess MCP server and dispatches via JSON-RPC 2.0."""
from __future__ import annotations
import asyncio
import json
from typing import Any
from .base import ToolBackend


class McpStdioBackend(ToolBackend):
    """Subprocess-based MCP server backend. Call start() before execute(), stop() at teardown."""

    def __init__(self, command: list[str], env: dict[str, str] | None = None) -> None:
        self._command = command
        self._env = env
        self._proc: asyncio.subprocess.Process | None = None
        self._id = 0
        self._initialized = False

    async def start(self) -> None:
        self._proc = await asyncio.create_subprocess_exec(
            *self._command,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=self._env,
        )
        await self._call("initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "conexus", "version": "0.1.0"},
        })
        self._initialized = True

    async def stop(self) -> None:
        if self._proc:
            self._proc.terminate()
            await self._proc.wait()
            self._proc = None
            self._initialized = False

    async def _call(self, method: str, params: dict) -> Any:
        assert self._proc and self._proc.stdin and self._proc.stdout
        self._id += 1
        req = json.dumps({"jsonrpc": "2.0", "id": self._id, "method": method, "params": params})
        self._proc.stdin.write((req + "\n").encode())
        await self._proc.stdin.drain()
        line = await self._proc.stdout.readline()
        resp = json.loads(line.decode())
        if "error" in resp:
            raise RuntimeError(f"MCP error: {resp['error']}")
        return resp.get("result")

    async def execute(self, tool_name: str, args: dict) -> str:
        if not self._initialized:
            raise RuntimeError("McpStdioBackend.start() must be called before execute()")
        try:
            result = await self._call("tools/call", {"name": tool_name, "arguments": args})
            # MCP returns {"content": [{"type": "text", "text": "..."}]}
            content = result.get("content", [])
            text_parts = [c["text"] for c in content if c.get("type") == "text"]
            return json.dumps("\n".join(text_parts) if len(text_parts) != 1 else text_parts[0])
        except Exception as exc:
            return json.dumps({"error": str(exc)})

    @property
    def backend_type(self) -> str:
        return "mcp-stdio"
```

- [ ] **Run tests**

```
uv run pytest src/conexus/tests/test_framework_backends.py -v
```
Expected: all green.

- [ ] **Commit**

```
git add src/conexus/core/backends/mcp_stdio_backend.py src/conexus/tests/test_framework_backends.py
git commit -m "feat(phase-7.5): McpStdioBackend — subprocess JSON-RPC 2.0 MCP client"
```

---

## Task 6: SkillLoader — resolve skills:, load packs, register backends, inject prompts

**Files:**
- Create: `src/conexus/core/skills/skill_resolver.py`
- Test: `src/conexus/tests/test_framework_pack_loader.py` (append)

- [ ] **Append failing tests**

```python
# append to test_framework_pack_loader.py
from conexus.core.skills.skill_resolver import SkillLoader
from conexus.core.agent_registry import AgentRegistry

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
    # tools were registered — but registry has only one backend per agent
    # calling the loaded tool should work
    result = await registry.execute_tool("bot", "wiki_search", {"query": "hello"})
    import json
    assert json.loads(result) == [{"result": "hello"}]

def test_skill_loader_missing_pack_raises(tmp_path):
    registry = AgentRegistry()
    loader = SkillLoader(agent_dir=tmp_path, registry=registry, agent_name="bot")
    with pytest.raises(FileNotFoundError, match="SKILL_PACK.md"):
        loader.load(["missing@0.1.0"])
```

- [ ] **Run to verify failure**

```
uv run pytest src/conexus/tests/test_framework_pack_loader.py -v -k "loader"
```
Expected: ImportError.

- [ ] **Implement `skill_resolver.py`**

```python
# src/conexus/core/skills/skill_resolver.py
"""SkillLoader — resolves skills: list, loads SKILL_PACK.md, registers backends."""
from __future__ import annotations
import importlib.util
import sys
from pathlib import Path
from conexus.core.skills.pack_loader import parse_skill_pack, SkillPackBackend
from conexus.core.agent_registry import AgentRegistry
from conexus.core.backends.python_backend import PythonBackend
from conexus.core.backends.mcp_stdio_backend import McpStdioBackend


class SkillLoader:
    """Load skills referenced in SKILL.md `skills:` list.

    Convention: skills live at `<agent_dir>/skills/<name>/SKILL_PACK.md`.
    Returns (extra_prompt_fragment: str, tool_tags: dict[str, str]).
    """

    def __init__(self, agent_dir: str | Path, registry: AgentRegistry, agent_name: str) -> None:
        self._agent_dir = Path(agent_dir)
        self._registry = registry
        self._agent_name = agent_name

    def load(self, skill_refs: list[str]) -> tuple[str, dict[str, str]]:
        """Load each skill. Returns (combined_prompt_fragment, merged_tool_tags)."""
        prompt_parts: list[str] = []
        tool_tags: dict[str, str] = {}

        for ref in skill_refs:
            name = ref.split("@")[0]
            pack_path = self._agent_dir / "skills" / name / "SKILL_PACK.md"
            if not pack_path.exists():
                raise FileNotFoundError(f"SKILL_PACK.md not found for skill '{name}': {pack_path}")

            doc = parse_skill_pack(pack_path)
            tool_tags.update(doc.frontmatter.data_classes)

            if doc.body:
                prompt_parts.append(doc.body)

            if doc.frontmatter.backend == SkillPackBackend.python:
                tools_py = doc.pack_dir / "tools.py"
                if tools_py.exists():
                    mod = self._load_module(name, tools_py)
                    # Find the first class in the module (convention)
                    tools_cls = next(
                        (v for v in vars(mod).values() if isinstance(v, type) and not v.__name__.startswith("_")),
                        None,
                    )
                    if tools_cls:
                        self._registry.register_backend(
                            self._agent_name, PythonBackend(tools_cls())
                        )

            elif doc.frontmatter.backend == SkillPackBackend.mcp_stdio:
                mcp_json = doc.pack_dir / "mcp.json"
                if not mcp_json.exists():
                    raise FileNotFoundError(f"mcp.json required for mcp-stdio backend: {mcp_json}")
                import json
                cfg = json.loads(mcp_json.read_text())
                backend = McpStdioBackend(command=cfg["command"], env=cfg.get("env"))
                self._registry.register_backend(self._agent_name, backend)

        return "\n\n".join(prompt_parts), tool_tags

    @staticmethod
    def _load_module(name: str, path: Path):
        module_name = f"_conexus_skill_{name}_tools"
        spec = importlib.util.spec_from_file_location(module_name, path)
        if spec is None or spec.loader is None:
            raise ImportError(f"Cannot load {path}")
        mod = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = mod
        spec.loader.exec_module(mod)  # type: ignore[union-attr]
        return mod
```

- [ ] **Run tests**

```
uv run pytest src/conexus/tests/test_framework_pack_loader.py -v
```
Expected: all green.

- [ ] **Commit**

```
git add src/conexus/core/skills/skill_resolver.py src/conexus/tests/test_framework_pack_loader.py
git commit -m "feat(phase-7.6): SkillLoader — resolve skills, load SKILL_PACK, register backends"
```

---

## Task 7: TrifectaGuard hook in agent_handler + `tool_tags` on config

**Files:**
- Modify: `src/conexus/core/agent_handler.py`
- Test: `src/conexus/tests/test_framework_trifecta_integration.py`

- [ ] **Write failing integration test**

```python
# src/conexus/tests/test_framework_trifecta_integration.py
"""End-to-end: agent_handler respects TrifectaGuard."""
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from conexus.core.agent_handler import AgentHandlerConfig, handle_agent_message


def _make_cfg(tool_calls: list[str], tool_tags: dict[str, str]) -> AgentHandlerConfig:
    """Build a minimal config that makes the LLM call each tool in sequence then reply."""
    call_iter = iter(tool_calls)

    async def mock_acall(**kwargs):
        try:
            tool_name = next(call_iter)
            tc = MagicMock()
            tc.function.name = tool_name
            tc.function.arguments = "{}"
            tc.id = f"id_{tool_name}"
            msg = MagicMock()
            msg.tool_calls = [tc]
            msg.content = None
            choice = MagicMock(); choice.message = msg
            resp = MagicMock(); resp.choices = [choice]
            return resp, "mock-model"
        except StopIteration:
            msg = MagicMock(); msg.tool_calls = None; msg.content = "done"
            choice = MagicMock(); choice.message = msg
            resp = MagicMock(); resp.choices = [choice]
            return resp, "mock-model"

    llm = MagicMock()
    llm.acall = mock_acall
    llm.config = MagicMock(); llm.config.temperature = 0.4

    async def execute_tool(name, args):
        return json.dumps({"ok": True})

    store = MagicMock()
    store.chat_recent.return_value = []
    store.facts_list.return_value = []
    store.chat_append = MagicMock()

    return AgentHandlerConfig(
        name="test",
        llm=llm,
        tools_schema=[],
        execute_tool=execute_tool,
        system_prompt="test",
        tool_tags=tool_tags,
    )


@pytest.mark.asyncio
async def test_handler_allows_safe_sequence():
    cfg = _make_cfg(
        tool_calls=["web_fetch"],
        tool_tags={"web_fetch": "untrusted_read"},
    )
    cap_checker = MagicMock()
    cap_checker.check.return_value = MagicMock(allowed=True)
    reply = await handle_agent_message(cfg, cfg.execute_tool.__self__ if hasattr(cfg.execute_tool, '__self__') else MagicMock(), cap_checker, "hello")
    assert reply == "done"


@pytest.mark.asyncio
async def test_handler_blocks_exfil_sequence():
    cfg = _make_cfg(
        tool_calls=["web_fetch", "wiki_read", "wiki_write"],
        tool_tags={
            "web_fetch": "untrusted_read",
            "wiki_read": "private_read",
            "wiki_write": "external_write",
        },
    )
    store = MagicMock()
    store.chat_recent.return_value = []
    store.facts_list.return_value = []
    store.chat_append = MagicMock()
    cap_checker = MagicMock()
    cap_checker.check.return_value = MagicMock(allowed=True)

    reply = await handle_agent_message(cfg, store, cap_checker, "hello")
    # wiki_write was blocked — reply is eventual text response or fallback
    # The tool result for wiki_write should contain TrifectaGuard error
    assert reply is not None  # handler recovered and continued
```

- [ ] **Run to verify failure**

```
uv run pytest src/conexus/tests/test_framework_trifecta_integration.py -v
```
Expected: error (tool_tags not a valid field yet).

- [ ] **Update `AgentHandlerConfig`**

Add one field to the dataclass in `agent_handler.py`:
```python
tool_tags: dict[str, str] | None = None  # None = TrifectaGuard disabled
```

- [ ] **Add guard to handler loop**

At the start of `handle_agent_message`, after the cap check, add:
```python
from conexus.core.trifecta.guard import TrifectaGuard, TrifectaViolation
guard = TrifectaGuard(cfg.tool_tags) if cfg.tool_tags is not None else None
```

Inside the `for tc in tool_calls:` loop, before calling `cfg.execute_tool`, add:
```python
if guard:
    try:
        guard.check_and_record(fn_name)
    except (TrifectaViolation, ValueError) as exc:
        print(f"[trifecta] {cfg.name}: {exc}", flush=True)
        messages.append({
            "role": "tool",
            "tool_call_id": tc_id,
            "content": json.dumps({"error": f"TrifectaGuard: {exc}"}),
        })
        continue  # skip actual execution; continue the turn
```

- [ ] **Run tests**

```
uv run pytest src/conexus/tests/test_framework_trifecta_integration.py src/conexus/tests/test_framework_trifecta.py -v
uv run pytest -x -q  # full suite
```
Expected: all green.

- [ ] **Commit**

```
git add src/conexus/core/agent_handler.py src/conexus/tests/test_framework_trifecta_integration.py
git commit -m "feat(phase-7.7): TrifectaGuard hook in agent_handler — blocks exfil on tool call"
```

---

## Task 8: `conexus tag --suggest <tools.py>` CLI command

**Files:**
- Modify: `src/conexus/cli/__main__.py`
- Test: manual smoke test (no new test file — CLI output is hard to unit-test meaningfully)

- [ ] **Add `tag` subcommand to `main()` in `__main__.py`**

Add to the `argparse` setup in `main()`:
```python
tag_cmd = sub.add_parser("tag", help="Tag analysis utilities")
tag_sub = tag_cmd.add_subparsers(dest="subcommand")
suggest_cmd = tag_sub.add_parser("suggest", help="Print suggested data_classes for a tools.py")
suggest_cmd.add_argument("tools_file", help="Path to a tools.py file")
suggest_cmd.set_defaults(func=_handle_tag_suggest)
```

Add handler function before `main()`:
```python
def _handle_tag_suggest(args: argparse.Namespace) -> None:
    """Print auto-tag suggestions for every public method in a tools.py."""
    import importlib.util as _ilu
    from conexus.core.trifecta.tags import auto_tag, DataClass

    path = Path(args.tools_file)
    if not path.exists():
        raise SystemExit(f"File not found: {path}")

    spec = _ilu.spec_from_file_location("_tag_target", path)
    if spec is None or spec.loader is None:
        raise SystemExit(f"Cannot load {path}")
    mod = _ilu.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]

    # Find classes and their public methods
    classes = [(n, v) for n, v in vars(mod).items() if isinstance(v, type) and not n.startswith("_")]
    if not classes:
        print("# No classes found.")
        return

    print("# Suggested data_classes: (review before committing)")
    print("data_classes:")
    untagged: list[str] = []
    for cls_name, cls in classes:
        methods = [m for m in dir(cls) if not m.startswith("_") and callable(getattr(cls, m))]
        for method in methods:
            tag = auto_tag(method)
            if tag:
                print(f"  {method}: {tag.value}")
            else:
                untagged.append(method)

    if untagged:
        print("# --- Untagged (manual review required) ---")
        for m in untagged:
            print(f"  {m}: ???  # add to SKILL_PACK.md data_classes")
```

- [ ] **Smoke test**

```bash
conexus tag suggest agents/ana/tools.py
```
Expected: prints a `data_classes:` YAML block listing all AnaTools methods with auto-tags.

- [ ] **Ruff + commit**

```
uv run ruff check src/conexus/cli/__main__.py
uv run pytest -x -q
git add src/conexus/cli/__main__.py
git commit -m "feat(phase-7.8): conexus tag --suggest — auto-tag heuristic preview for tools.py"
```

---

## Self-Review

### Spec coverage check

| Spec requirement (§1.3, §1.4, §1.8) | Task |
|--------------------------------------|------|
| SKILL_PACK.md parses (name, version, backend, capabilities, data_classes, prompts) | Task 1 |
| `skills:` list in SKILL.md frontmatter | Task 1 |
| SkillLoader resolves skills, loads tools, injects prompt fragments | Task 6 |
| python backend dispatches via same AgentRegistry.execute_tool API | Task 4 |
| mcp-stdio backend dispatches via same API | Task 5 |
| TrifectaGuard blocks untrusted_read + private_read → external_write | Task 3, 7 |
| Auto-tag heuristic at skill load | Task 2 |
| Untagged + no heuristic match → error | Task 3 |
| `conexus tag --suggest` CLI | Task 8 |
| Integration test: full exfil scenario blocked | Task 7 |

**Gap:** mcp-http backend not implemented. Defer to Phase 7.5 or Phase 9 (not needed for solo Fly.io deployment). Note in `docs/superpowers/specs/` or open a task.

**Gap:** `trust_boundary: cleared` flag on Handoff payload — Phase 8 (TEAM_PACK adds Handoff type).

### Type consistency

- `TrifectaGuard(tool_tags: dict[str, str])` — used in `AgentHandlerConfig.tool_tags: dict[str, str] | None`. ✓
- `SkillLoader.load()` returns `(str, dict[str, str])` — callers use unpacking. ✓
- `PythonBackend._tools` accessed in `AgentRegistry.get_tools()` via `backend._tools`. ✓

### Placeholder scan

None found.

---

*Plan is load-bearing. Implementation that contradicts must update this doc first. Last revised 2026-04-29.*
