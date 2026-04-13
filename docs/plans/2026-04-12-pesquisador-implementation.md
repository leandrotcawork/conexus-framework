# Pesquisador Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a second Conexus agent — Pesquisador — that researches topics and builds a professional knowledge wiki following Karpathy's LLM Wiki pattern, communicating via Telegram in pt-BR.

**Architecture:** Three-file agent pattern (SKILL.md + tools.py + jobs.py) mirroring Ana exactly. Two TrackedLLM instances (Flash for primary, R1 for synthesis). Knowledge wiki in a separate Git repo cloned to `/data/knowledge/`. DuckDuckGo for free web search. Source trust system via `sources.md`.

**Tech Stack:** Python 3.11, LiteLLM, python-telegram-bot, APScheduler, duckduckgo-search, youtube-transcript-api, pypdfium2, httpx (web fetch)

---

## File Structure

### New files to create

| File | Responsibility |
|------|---------------|
| `agents/pesquisador/__init__.py` | Package marker |
| `agents/pesquisador/SKILL.md` | Frontmatter (LLM tiers, schedules, budget) + system prompt |
| `agents/pesquisador/tools.py` | `PesquisadorTools` @dataclass — 11 tool methods bound to wiki store + search clients + synthesis LLM |
| `agents/pesquisador/jobs.py` | 3 job builders: `make_weekly_digest_job`, `make_wiki_audit_job`, `make_proactive_research_job` |

### Existing files to modify

| File | Change |
|------|--------|
| `core/config/skill_loader.py:35-46` | Add optional `llm_synthesis` field + `prefix` field to `SkillFrontmatter` |
| `core/messaging/telegram_bot.py:102-109` | Add `pesq` to `_split_prefix()` allowed prefixes, add document/PDF handler |
| `core/scheduler/scheduler.py:31-38` | Add Pesquisador job kinds to `CATCHUP_WINDOWS` |
| `main.py` | Add Pesquisador wiring: parse SKILL.md, build 2 LLMs, instantiate tools, register jobs, add handler + tool schema |
| `pyproject.toml` | Add `duckduckgo-search` and `httpx` dependencies |

---

### Task 1: Add `duckduckgo-search` and `httpx` dependencies

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1: Add dependencies to pyproject.toml**

Read `pyproject.toml` and add `duckduckgo-search` and `httpx` to the `dependencies` list:

```toml
"duckduckgo-search>=7.0",
"httpx>=0.27",
```

`youtube-transcript-api` and `pypdfium2` should already be in dependencies — verify and add if missing.

- [ ] **Step 2: Install dependencies**

Run: `uv sync`
Expected: dependencies install successfully, `uv.lock` updated.

- [ ] **Step 3: Verify imports work**

Run: `python -c "from duckduckgo_search import DDGS; import httpx; print('ok')"`
Expected: `ok`

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml uv.lock
git commit -m "chore: add duckduckgo-search and httpx dependencies for Pesquisador"
```

---

### Task 2: Extend `skill_loader.py` for dual-LLM and prefix support

**Files:**
- Modify: `core/config/skill_loader.py`
- Test: `tests/test_skill_loader.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_skill_loader.py`:

```python
"""Tests for skill_loader with dual-LLM and prefix support."""

from pathlib import Path
from core.config.skill_loader import parse_skill_file


def test_parse_skill_with_synthesis_llm(tmp_path: Path):
    skill_md = tmp_path / "SKILL.md"
    skill_md.write_text(
        "---\n"
        "name: Pesquisador\n"
        "role: Knowledge researcher\n"
        "language: pt-BR\n"
        "prefix: pesq\n"
        "goal: Research and build knowledge wiki\n"
        "tools:\n"
        "  - wiki_read\n"
        "  - web_search\n"
        "llm:\n"
        "  provider: gemini\n"
        "  model: gemini-2.5-flash\n"
        "  temperature: 0.3\n"
        "llm_synthesis:\n"
        "  provider: deepseek\n"
        "  model: deepseek-reasoner\n"
        "  temperature: 0.2\n"
        "budget:\n"
        "  daily_usd: 0.15\n"
        "  monthly_usd: 4.50\n"
        "  on_exceed: notify\n"
        "---\n"
        "# System prompt body\n"
    )
    doc = parse_skill_file(skill_md)
    assert doc.frontmatter.name == "Pesquisador"
    assert doc.frontmatter.prefix == "pesq"
    assert doc.frontmatter.llm.provider == "gemini"
    assert doc.frontmatter.llm_synthesis is not None
    assert doc.frontmatter.llm_synthesis.provider == "deepseek"
    assert doc.frontmatter.llm_synthesis.model == "deepseek-reasoner"
    assert doc.frontmatter.llm_synthesis.temperature == 0.2


def test_parse_skill_without_synthesis_llm(tmp_path: Path):
    """Ana's SKILL.md has no llm_synthesis — should still parse fine."""
    skill_md = tmp_path / "SKILL.md"
    skill_md.write_text(
        "---\n"
        "name: Ana\n"
        "role: Secretary\n"
        "goal: Help Leandro\n"
        "tools:\n"
        "  - memory_get\n"
        "llm:\n"
        "  provider: gemini\n"
        "  model: gemini-2.5-flash\n"
        "---\n"
        "# Ana prompt\n"
    )
    doc = parse_skill_file(skill_md)
    assert doc.frontmatter.llm_synthesis is None
    assert doc.frontmatter.prefix is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_skill_loader.py -v`
Expected: FAIL — `SkillFrontmatter` has no `llm_synthesis` or `prefix` field.

- [ ] **Step 3: Add `llm_synthesis` and `prefix` to SkillFrontmatter**

In `core/config/skill_loader.py`, add to `SkillFrontmatter`:

```python
class SkillFrontmatter(BaseModel):
    name: str
    role: str
    language: str = "pt-BR"
    prefix: str | None = None
    goal: str
    tools: list[str]
    llm: LLMSection
    llm_synthesis: LLMSection | None = None
    schedules: list[Schedule] = Field(default_factory=list)
    budget: Optional[BudgetSection] = None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_skill_loader.py -v`
Expected: 2 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add core/config/skill_loader.py tests/test_skill_loader.py
git commit -m "feat: add llm_synthesis and prefix fields to SkillFrontmatter"
```

---

### Task 3: Add `pesq` prefix to Telegram routing

**Files:**
- Modify: `core/messaging/telegram_bot.py:102-109`

- [ ] **Step 1: Update `_split_prefix()` to recognize `pesq:`**

The current `_split_prefix` uses `/ana` prefix format. The spec says Pesquisador uses `pesq:` prefix format. Looking at the existing code:

```python
def _split_prefix(text: str) -> tuple[str, str]:
    """Parse '/ana olá' -> ('ana', 'olá'). Plain text -> ('', text)."""
    if text.startswith("/") and " " in text:
        head, rest = text.split(" ", 1)
        name = head[1:]
        if name in {"ana", "researcher", "code_manager"}:
            return name, rest
    return "", text
```

Update to also handle `pesq:` colon-prefix format and add `pesquisador` to the set:

```python
def _split_prefix(text: str) -> tuple[str, str]:
    """Parse 'pesq: olá' -> ('pesquisador', 'olá'). '/ana olá' -> ('ana', 'olá'). Plain text -> ('', text)."""
    # Colon-prefix format: "pesq: text" or "pesq:text"
    _COLON_PREFIXES = {"pesq": "pesquisador"}
    for short, full in _COLON_PREFIXES.items():
        if text.lower().startswith(f"{short}:"):
            body = text[len(short) + 1:].lstrip()
            return full, body

    # Slash-prefix format: "/ana text"
    if text.startswith("/") and " " in text:
        head, rest = text.split(" ", 1)
        name = head[1:]
        if name in {"ana", "pesquisador", "researcher", "code_manager"}:
            return name, rest
    return "", text
```

- [ ] **Step 2: Verify Ana still routes correctly**

Run: `python -c "from core.messaging.telegram_bot import _split_prefix; print(_split_prefix('/ana olá'))"`
Expected: `('ana', 'olá')`

- [ ] **Step 3: Verify Pesquisador routes correctly**

Run: `python -c "from core.messaging.telegram_bot import _split_prefix; print(_split_prefix('pesq: pesquise OAuth2'))"`
Expected: `('pesquisador', 'pesquise OAuth2')`

- [ ] **Step 4: Verify plain text still routes to default**

Run: `python -c "from core.messaging.telegram_bot import _split_prefix; print(_split_prefix('olá'))"`
Expected: `('', 'olá')`

- [ ] **Step 5: Add document/PDF handler to TelegramBot**

In `core/messaging/telegram_bot.py`, add a document handler for PDF attachments:

In `build()`, add after the VOICE handler:
```python
self.app.add_handler(MessageHandler(filters.Document.PDF, self._on_document))
```

Add the handler method:
```python
    async def _on_document(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._authorized(update):
            return
        doc = update.message.document
        if doc.mime_type != "application/pdf":
            await update.message.reply_text("Só aceito PDFs por enquanto.")
            return
        await update.message.reply_text("📄 Recebi o PDF, processando...")
        try:
            tg_file = await doc.get_file()
            file_bytes = bytes(await tg_file.download_as_bytearray())
            # Save to temp file
            import tempfile, os
            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
                tmp.write(file_bytes)
                tmp_path = tmp.name
            # Route to handler with PDF path in the message
            caption = update.message.caption or ""
            prefix_agent, body = _split_prefix(caption if caption else "pesq: resuma este PDF")
            body = f"{body}\n[PDF_PATH:{tmp_path}]"
            reply = await self.message_handler(body, prefix_agent)
            await update.message.reply_text(reply)
            os.unlink(tmp_path)
        except Exception as e:
            await update.message.reply_text(f"Erro ao processar PDF: {e}")
```

- [ ] **Step 6: Commit**

```bash
git add core/messaging/telegram_bot.py
git commit -m "feat: add pesq: prefix routing and PDF document handler"
```

---

### Task 4: Create `agents/pesquisador/SKILL.md`

**Files:**
- Create: `agents/pesquisador/__init__.py`
- Create: `agents/pesquisador/SKILL.md`

- [ ] **Step 1: Create package directory and init**

```bash
mkdir -p agents/pesquisador
touch agents/pesquisador/__init__.py
```

- [ ] **Step 2: Write SKILL.md**

Create `agents/pesquisador/SKILL.md`:

```markdown
---
name: Pesquisador
role: Pesquisador de conhecimento e curador de wiki técnica
language: pt-BR
prefix: pesq
goal: >
  Pesquisar temas técnicos, construir e manter uma wiki de conhecimento
  profissional sobre engenharia de software, e responder perguntas com base
  no conhecimento acumulado.
tools:
  - wiki_read
  - wiki_write
  - wiki_search
  - wiki_list
  - web_search
  - web_fetch
  - youtube_transcript
  - pdf_extract
  - raw_save
  - git_sync
llm:
  provider: gemini
  model: gemini-2.5-flash
  temperature: 0.3
llm_synthesis:
  provider: deepseek
  model: deepseek-reasoner
  temperature: 0.2
schedules:
  - { kind: weekly_digest, cron: "0 20 * * 0" }
  - { kind: wiki_audit, cron: "0 10 1 * *" }
  - { kind: proactive_research, cron: "0 14 * * 3,6" }
budget:
  daily_usd: 0.15
  monthly_usd: 4.50
  on_exceed: notify
---

# Pesquisador — Curador de Conhecimento

## Sobre você
Você é o Pesquisador, um agente especializado em pesquisa técnica e construção
de conhecimento. Você fala português brasileiro, de forma profissional e direta.
Você nunca inventa informações — tudo vem de fontes pesquisadas e documentadas.

## O que você faz
- Pesquisa temas técnicos quando o Leandro pede (web, YouTube, PDFs).
- Mantém uma wiki de conhecimento profissional em Markdown (padrão Karpathy).
- Responde perguntas consultando a wiki primeiro (barato), pesquisando só se necessário.
- Compila fontes brutas em artigos estruturados e profissionais usando DeepSeek R1.
- Gerencia fontes confiáveis (sources.md) para controle de qualidade.

## O que você NÃO faz
- Não inventa conteúdo — se não encontrou fonte, diz que não encontrou.
- Não pesquisa proativamente fora das fontes confiáveis (sources.md Tier 1).
- Não escreve artigos na wiki sem salvar as fontes brutas em raw/ primeiro.
- Não ultrapassa o orçamento — priorize consultas à wiki sobre novas pesquisas.

## Wiki — Padrão Karpathy (3 camadas)
1. **raw/** — Fontes brutas imutáveis (artigos, transcrições, PDFs)
2. **domains/, entities/, concepts/** — Wiki compilada pelo LLM (artigos profissionais)
3. **schema.md, sources.md** — Governança (regras de qualidade e fontes confiáveis)

### Convenções de artigos
- Cada artigo tem frontmatter YAML: domain, confidence, sources, last_updated.
- Confidence: high (3+ fontes confiáveis), medium (1-2 fontes), low (fonte única ou não confiável).
- Seções adaptam ao tema — não use template fixo. Qualidade é constante, estrutura é flexível.
- Sempre inclua "## See Also" com [[backlinks]] e "## Sources" com caminhos raw/.
- Atualize index.md e log.md após cada escrita.

### Fluxos
- **Pesquisa**: pergunta → busca web → salva raw/ → R1 compila artigo → index + log → git sync.
- **Consulta**: pergunta → busca wiki → responde com citação. Sem pesquisa, sem R1.
- **Ingestão**: URL/PDF/YouTube → extrai conteúdo → salva raw/ → R1 compila → index + log → git sync.

### Fontes confiáveis (sources.md)
- Pesquisa proativa: SOMENTE Tier 1 (fontes em sources.md).
- Pesquisa sob demanda: pode usar web aberta, mas marca confidence como low se fonte não confiável.
- Leandro pode adicionar/remover fontes via Telegram.
```

- [ ] **Step 3: Verify it parses correctly**

Run: `python -c "from core.config.skill_loader import parse_skill_file; d = parse_skill_file('agents/pesquisador/SKILL.md'); print(d.frontmatter.name, d.frontmatter.prefix, d.frontmatter.llm_synthesis.model)"`
Expected: `Pesquisador pesq deepseek-reasoner`

- [ ] **Step 4: Commit**

```bash
git add agents/pesquisador/
git commit -m "feat: add Pesquisador SKILL.md with dual-LLM config"
```

---

### Task 5: Create `agents/pesquisador/tools.py`

**Files:**
- Create: `agents/pesquisador/tools.py`
- Test: `tests/test_pesquisador_tools.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_pesquisador_tools.py`:

```python
"""Tests for PesquisadorTools wiki operations."""

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from agents.pesquisador.tools import PesquisadorTools
from core.memory.wiki_store import WikiStore


@pytest.fixture
def wiki(tmp_path: Path) -> WikiStore:
    wiki_dir = tmp_path / "knowledge"
    wiki_dir.mkdir()
    return WikiStore(wiki_dir, autocommit=False)


@pytest.fixture
def tools(wiki: WikiStore) -> PesquisadorTools:
    return PesquisadorTools(wiki=wiki)


def test_wiki_write_and_read(tools: PesquisadorTools):
    tools.wiki_write("domains/backend/_index.md", "# Backend\n")
    content = tools.wiki_read("domains/backend/_index.md")
    assert "# Backend" in content


def test_wiki_search(tools: PesquisadorTools):
    tools.wiki_write("domains/backend/auth/oauth2.md", "# OAuth2\nOpen Authorization 2.0")
    results = tools.wiki_search("OAuth2")
    assert len(results) >= 1
    assert "oauth2" in results[0]["path"]


def test_wiki_list(tools: PesquisadorTools):
    tools.wiki_write("domains/backend/auth/oauth2.md", "# OAuth2\n")
    tools.wiki_write("domains/backend/auth/jwt.md", "# JWT\n")
    files = tools.wiki_list("domains/backend/auth")
    assert len(files) == 2


def test_raw_save(tools: PesquisadorTools):
    result = tools.raw_save("articles", "oauth2-guide.md", "# OAuth2 Guide\nContent here.")
    assert result["ok"] is True
    content = tools.wiki_read("raw/articles/oauth2-guide.md")
    assert "OAuth2 Guide" in content


def test_raw_save_immutable(tools: PesquisadorTools):
    """raw/ files are immutable — cannot overwrite existing."""
    tools.raw_save("articles", "oauth2-guide.md", "# Original")
    result = tools.raw_save("articles", "oauth2-guide.md", "# Overwritten")
    assert result.get("error") is not None
    content = tools.wiki_read("raw/articles/oauth2-guide.md")
    assert "Original" in content


def test_web_search_classifies_trusted(tools: PesquisadorTools):
    """web_search results include is_trusted flag based on sources.md."""
    tools.wiki_write("sources.md", "## Official Documentation\n- docs.python.org\n")
    results = tools.web_search("python tutorial", max_results=3)
    # Results should have is_trusted field (True/False based on sources.md)
    for r in results:
        assert "is_trusted" in r


def test_git_sync_calls_commit(tools: PesquisadorTools, monkeypatch):
    called = []
    monkeypatch.setattr(
        tools.wiki, "_git_commit_push",
        lambda msg: called.append(msg),
    )
    tools.git_sync("test commit")
    assert len(called) == 1
    assert "test commit" in called[0]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_pesquisador_tools.py -v`
Expected: FAIL — `agents.pesquisador.tools` module doesn't exist yet.

- [ ] **Step 3: Implement PesquisadorTools**

Create `agents/pesquisador/tools.py`:

```python
"""Pesquisador's tool functions. Each method maps to a tool the LLM can call.
Wiki operations use the shared WikiStore pointed at the knowledge-wiki repo.
Research tools (web_search, web_fetch, youtube_transcript, pdf_extract) use
external libraries."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from core.memory.wiki_store import WikiStore


@dataclass
class PesquisadorTools:
    wiki: WikiStore
    llm_synthesis: object = None  # TrackedLLM, injected from main.py

    # ----- source trust -----

    def _load_trusted_domains(self) -> set[str]:
        """Parse sources.md and extract domain names from trusted sources."""
        try:
            content = self.wiki.read("sources.md")
        except FileNotFoundError:
            return set()
        domains: set[str] = set()
        for line in content.splitlines():
            line = line.strip().lstrip("- ")
            # Extract domain-like strings (e.g., "docs.python.org", "martinfowler.com")
            if "." in line and not line.startswith("#") and not line.startswith(">"):
                # Take first word that looks like a domain
                for word in line.split():
                    if "." in word and not word.startswith("("):
                        clean = word.strip("(),")
                        domains.add(clean.lower())
                        break
        return domains

    def _is_trusted_url(self, url: str, trusted_domains: set[str]) -> bool:
        from urllib.parse import urlparse
        host = urlparse(url).hostname or ""
        return any(host.endswith(d) for d in trusted_domains)

    # ----- wiki tools -----

    def wiki_read(self, path: str) -> str:
        return self.wiki.read(path)

    def wiki_write(self, path: str, content: str) -> dict:
        self.wiki.write(path, content)
        return {"ok": True}

    def wiki_search(self, query: str) -> list[dict]:
        return self.wiki.search(query)

    def wiki_list(self, domain: str = "") -> list[str]:
        return self.wiki.list(domain)

    # ----- research tools -----

    def web_search(self, query: str, max_results: int = 5, tier: int = 3) -> list[dict]:
        """Search the web using DuckDuckGo. Results include is_trusted flag.
        tier=1: return ONLY trusted sources (for proactive research).
        tier=2: return all but mark trust status (for user-requested research).
        tier=3: return all (open web, default)."""
        from duckduckgo_search import DDGS

        trusted_domains = self._load_trusted_domains()
        # Fetch more results when filtering to tier 1 to compensate for filtering
        fetch_count = max_results * 3 if tier == 1 else max_results
        raw_results = DDGS().text(query, max_results=fetch_count)
        results = []
        for r in raw_results:
            url = r.get("href", "")
            is_trusted = self._is_trusted_url(url, trusted_domains)
            if tier == 1 and not is_trusted:
                continue  # Tier 1: skip non-trusted sources
            results.append({
                "title": r.get("title", ""),
                "url": url,
                "snippet": r.get("body", ""),
                "is_trusted": is_trusted,
            })
        # Sort trusted results first, limit to max_results
        results.sort(key=lambda x: (not x["is_trusted"],))
        return results[:max_results]

    def web_fetch(self, url: str) -> str:
        """Fetch a web page and extract its text content."""
        import httpx
        from html.parser import HTMLParser

        resp = httpx.get(url, follow_redirects=True, timeout=30.0,
                         headers={"User-Agent": "Mozilla/5.0 (Conexus-Pesquisador)"})
        resp.raise_for_status()

        # Simple HTML to text extraction
        class _TextExtractor(HTMLParser):
            def __init__(self):
                super().__init__()
                self.parts: list[str] = []
                self._skip = False

            def handle_starttag(self, tag, attrs):
                if tag in ("script", "style", "nav", "footer", "header"):
                    self._skip = True

            def handle_endtag(self, tag):
                if tag in ("script", "style", "nav", "footer", "header"):
                    self._skip = False

            def handle_data(self, data):
                if not self._skip:
                    text = data.strip()
                    if text:
                        self.parts.append(text)

        extractor = _TextExtractor()
        extractor.feed(resp.text)
        return "\n".join(extractor.parts)

    def youtube_transcript(self, url: str) -> str:
        """Extract transcript from a YouTube video URL."""
        from youtube_transcript_api import YouTubeTranscriptApi

        # Extract video ID from various URL formats
        video_id = None
        patterns = [
            r'(?:v=|/v/|youtu\.be/)([a-zA-Z0-9_-]{11})',
        ]
        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                video_id = match.group(1)
                break

        if not video_id:
            return f"Could not extract video ID from URL: {url}"

        ytt_api = YouTubeTranscriptApi()
        transcript = ytt_api.fetch(video_id)
        lines = [entry.text for entry in transcript]
        return "\n".join(lines)

    def pdf_extract(self, file_path: str) -> str:
        """Extract text from a PDF file."""
        import pypdfium2 as pdfium

        pdf = pdfium.PdfDocument(file_path)
        parts: list[str] = []
        for page in pdf:
            textpage = page.get_textpage()
            parts.append(textpage.get_text_range())
            textpage.close()
            page.close()
        pdf.close()
        return "\n\n".join(parts)

    # ----- storage tools -----

    def raw_save(self, category: str, filename: str, content: str) -> dict:
        """Save source material to raw/<category>/<filename>. Immutable — rejects overwrites."""
        path = f"raw/{category}/{filename}"
        try:
            self.wiki.read(path)
            return {"error": f"raw file already exists: {path}. Raw sources are immutable."}
        except FileNotFoundError:
            pass
        self.wiki.write(path, content)
        return {"ok": True, "path": path}

    def compile_article(self, topic: str, raw_paths: list[str], target_path: str) -> dict:
        """Compile raw sources into a professional wiki article using R1 synthesis LLM.
        This is the ONLY tool that should create/update wiki articles from research."""
        from core.llm.context_tag import set_context

        if self.llm_synthesis is None:
            return {"error": "synthesis LLM not configured"}

        # Read all raw sources
        raw_contents: list[str] = []
        for rp in raw_paths:
            try:
                raw_contents.append(f"--- Source: {rp} ---\n{self.wiki.read(rp)}")
            except FileNotFoundError:
                raw_contents.append(f"--- Source: {rp} --- (not found)")

        # Determine confidence based on trusted sources
        trusted_domains = self._load_trusted_domains()
        trusted_count = sum(1 for rp in raw_paths if any(d in rp for d in trusted_domains))
        total = len(raw_paths)
        if trusted_count >= 3:
            confidence = "high"
        elif trusted_count >= 1:
            confidence = "medium"
        else:
            confidence = "low"

        from datetime import datetime, timezone
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        prompt = (
            f"Compile the following raw sources into a professional wiki article about '{topic}'.\n\n"
            f"Raw sources:\n{''.join(raw_contents)}\n\n"
            f"Requirements:\n"
            f"1. Start with YAML frontmatter: domain (infer from target_path '{target_path}'), "
            f"confidence: {confidence}, sources: {total}, last_updated: {today}\n"
            f"2. Write like Wikipedia: structured, factual, dense. Every sentence earns its place.\n"
            f"3. Sections should adapt to this specific topic — no fixed template.\n"
            f"4. Include '## See Also' with [[backlinks]] to related topics.\n"
            f"5. Include '## Sources' listing the raw/ paths.\n"
            f"6. Write in Portuguese (pt-BR).\n"
        )

        with set_context("synthesis"):
            article = self.llm_synthesis.complete([
                {"role": "system", "content": "You are a professional technical writer compiling research into a structured knowledge article."},
                {"role": "user", "content": prompt},
            ])

        self.wiki.write(target_path, article)

        # Update index.md and log.md atomically
        self.wiki.update_index(target_path, f"{topic} — confidence: {confidence}")
        self.wiki.append_log(
            "ingest", topic,
            f"Compiled {len(raw_paths)} sources into {target_path} (confidence: {confidence})"
        )

        return {"ok": True, "path": target_path, "confidence": confidence}

    def git_sync(self, message: str) -> dict:
        """Commit and push all wiki changes to GitHub."""
        self.wiki._git_commit_push(message)
        return {"ok": True}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_pesquisador_tools.py -v`
Expected: 5 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add agents/pesquisador/tools.py tests/test_pesquisador_tools.py
git commit -m "feat: add PesquisadorTools with 10 tool methods"
```

---

### Task 6: Create `agents/pesquisador/jobs.py`

**Files:**
- Create: `agents/pesquisador/jobs.py`

- [ ] **Step 1: Implement the 3 job builders**

Create `agents/pesquisador/jobs.py`, following Ana's job pattern exactly (`_run_with_ping_log` for idempotency):

```python
"""Pesquisador's proactive jobs. Each builder returns an async JobFn closure.
Main.py wires everything together."""

from __future__ import annotations

from datetime import datetime
from typing import Awaitable, Callable
from zoneinfo import ZoneInfo

from agents.pesquisador.tools import PesquisadorTools
from core.llm.context_tag import set_context
from core.llm.router import TrackedLLM
from core.memory.sqlite_store import SqliteStore

TZ = ZoneInfo("America/Sao_Paulo")


async def _run_with_ping_log(
    store: SqliteStore,
    kind: str,
    ref_id: str,
    agent_name: str,
    body: Callable[[], Awaitable[str]],
    send_telegram: Callable[[str], Awaitable[None]],
) -> None:
    if store.ping_was_sent(kind, ref_id, agent_name):
        return
    store.ping_mark_pending(kind, ref_id, agent_name)
    try:
        text = await body()
        await send_telegram(text)
        store.ping_mark_sent(kind, ref_id, agent_name)
    except Exception as e:
        import sys
        print(f"[pesquisador:{kind}] failed: {e}", file=sys.stderr)


def make_weekly_digest_job(
    tools: PesquisadorTools,
    llm: TrackedLLM,
    store: SqliteStore,
    send_telegram: Callable[[str], Awaitable[None]],
) -> Callable[[], Awaitable[None]]:
    """Sunday 20:00 — summary of wiki additions/updates this week."""
    async def run() -> None:
        now = datetime.now(TZ)
        year, week, _ = now.isocalendar()
        ref_id = f"{year}-{week:02d}"

        async def body() -> str:
            # Read log.md for recent entries
            try:
                log_content = tools.wiki_read("log.md")
            except FileNotFoundError:
                log_content = "(nenhuma atividade)"

            # Count articles
            all_articles = tools.wiki_list("domains")
            entities = tools.wiki_list("entities")
            concepts = tools.wiki_list("concepts")

            prompt = (
                "Você é o Pesquisador. Escreva um resumo semanal curto em pt-BR "
                "do que foi adicionado/atualizado na wiki de conhecimento.\n\n"
                f"Semana: {ref_id}\n"
                f"Total artigos: domains={len(all_articles)}, "
                f"entities={len(entities)}, concepts={len(concepts)}\n\n"
                f"Log recente:\n{log_content[-2000:]}\n\n"
                "Formate como: 📚 Resumo semanal, seguido de bullet points."
            )

            with set_context("weekly_digest"):
                return llm.complete([
                    {"role": "system", "content": "Você é o Pesquisador."},
                    {"role": "user", "content": prompt},
                ])

        await _run_with_ping_log(
            store, "weekly_digest", ref_id, "pesquisador", body, send_telegram
        )

    return run


def make_wiki_audit_job(
    tools: PesquisadorTools,
    llm: TrackedLLM,
    store: SqliteStore,
    send_telegram: Callable[[str], Awaitable[None]],
) -> Callable[[], Awaitable[None]]:
    """1st of month 10:00 — scan for low-confidence, stale, orphan articles."""
    async def run() -> None:
        now = datetime.now(TZ)
        ref_id = now.strftime("%Y-%m")

        async def body() -> str:
            all_files = tools.wiki_list("domains") + tools.wiki_list("entities") + tools.wiki_list("concepts")

            low_confidence: list[str] = []
            no_frontmatter: list[str] = []

            for f in all_files:
                try:
                    content = tools.wiki_read(f)
                    if "confidence: low" in content:
                        low_confidence.append(f)
                    if not content.startswith("---"):
                        no_frontmatter.append(f)
                except FileNotFoundError:
                    continue

            prompt = (
                "Você é o Pesquisador. Faça um relatório de auditoria curto em pt-BR.\n\n"
                f"Total artigos: {len(all_files)}\n"
                f"Artigos com confiança baixa ({len(low_confidence)}): {', '.join(low_confidence[:10])}\n"
                f"Artigos sem frontmatter ({len(no_frontmatter)}): {', '.join(no_frontmatter[:10])}\n\n"
                "Formate como: 🔍 Auditoria mensal, seguido de achados e recomendações."
            )

            with set_context("wiki_audit"):
                return llm.complete([
                    {"role": "system", "content": "Você é o Pesquisador."},
                    {"role": "user", "content": prompt},
                ])

        await _run_with_ping_log(
            store, "wiki_audit", ref_id, "pesquisador", body, send_telegram
        )

    return run


def make_proactive_research_job(
    tools: PesquisadorTools,
    llm: TrackedLLM,
    llm_synthesis: TrackedLLM,
    store: SqliteStore,
    send_telegram: Callable[[str], Awaitable[None]],
) -> Callable[[], Awaitable[None]]:
    """Wed + Sat 14:00 — pick 1 topic and research using Tier 1 sources only."""
    async def run() -> None:
        now = datetime.now(TZ)
        ref_id = now.strftime("%Y-%m-%d")

        async def body() -> str:
            # Find low-confidence or empty domain articles to improve
            all_files = tools.wiki_list("domains")
            low_confidence: list[str] = []

            for f in all_files:
                try:
                    content = tools.wiki_read(f)
                    if "confidence: low" in content:
                        low_confidence.append(f)
                except FileNotFoundError:
                    continue

            if not low_confidence:
                return "📖 Pesquisa proativa: nenhum artigo com confiança baixa encontrado. Wiki está saudável!"

            target = low_confidence[0]

            # Read sources.md for trusted sources
            try:
                sources_config = tools.wiki_read("sources.md")
            except FileNotFoundError:
                sources_config = "(sem sources.md configurado)"

            # Read the current article
            current_content = tools.wiki_read(target)

            # Search for more information
            topic = target.split("/")[-1].replace(".md", "").replace("-", " ")
            search_results = tools.web_search(topic, max_results=5, tier=1)  # Tier 1 ONLY for proactive
            search_text = "\n".join(
                f"- {r['title']}: {r['snippet']}" for r in search_results
            )

            # Use R1 for synthesis
            prompt = (
                f"Você é o Pesquisador. Melhore o artigo '{target}' da wiki.\n\n"
                f"Fontes confiáveis:\n{sources_config[:1000]}\n\n"
                f"Artigo atual:\n{current_content[:2000]}\n\n"
                f"Resultados de pesquisa:\n{search_text}\n\n"
                "Reescreva o artigo completo com frontmatter YAML (domain, confidence, sources, last_updated). "
                "Melhore a qualidade e aumente a confiança. Mantenha formato Wikipedia: "
                "estruturado, factual, denso. Inclua ## See Also e ## Sources."
            )

            with set_context("proactive_research"):
                improved = llm_synthesis.complete([
                    {"role": "system", "content": "Você é um pesquisador técnico especializado."},
                    {"role": "user", "content": prompt},
                ])

            tools.wiki_write(target, improved)
            tools.wiki.append_log("proactive", f"Improved {target}", f"Upgraded via proactive research")
            tools.git_sync(f"proactive: improve {target}")

            return f"📖 Pesquisa proativa: artigo melhorado — {target}"

        await _run_with_ping_log(
            store, "proactive_research", ref_id, "pesquisador", body, send_telegram
        )

    return run
```

- [ ] **Step 2: Verify imports work**

Run: `python -c "from agents.pesquisador.jobs import make_weekly_digest_job, make_wiki_audit_job, make_proactive_research_job; print('ok')"`
Expected: `ok`

- [ ] **Step 3: Commit**

```bash
git add agents/pesquisador/jobs.py
git commit -m "feat: add Pesquisador jobs — weekly digest, monthly audit, proactive research"
```

---

### Task 7: Add Pesquisador job kinds to scheduler CATCHUP_WINDOWS

**Files:**
- Modify: `core/scheduler/scheduler.py:31-38`

- [ ] **Step 1: Add Pesquisador kinds to CATCHUP_WINDOWS and current_ref_id**

In `core/scheduler/scheduler.py`, add to `CATCHUP_WINDOWS`:

```python
CATCHUP_WINDOWS = {
    # Ana
    "briefing":            (True,  12),
    "recap":               (True,  24),
    "pre_event":           (False, 0),
    "todo_sweep":          (False, 0),
    "lint":                (True,  0),
    # Pesquisador
    "weekly_digest":       (True,  0),   # weekly, catchable
    "wiki_audit":          (True,  0),   # monthly, catchable
    "proactive_research":  (False, 0),   # skip if missed
}
```

Update `current_ref_id` to handle the new kinds:

```python
def current_ref_id(kind: str, now_local: datetime) -> str:
    if kind in ("briefing", "recap", "todo_sweep", "proactive_research"):
        return now_local.strftime("%Y-%m-%d")
    if kind in ("lint", "weekly_digest"):
        year, week, _ = now_local.isocalendar()
        return f"{year}-{week:02d}"
    if kind == "wiki_audit":
        return now_local.strftime("%Y-%m")
    if kind == "pre_event":
        return ""
    return ""
```

- [ ] **Step 2: Commit**

```bash
git add core/scheduler/scheduler.py
git commit -m "feat: add Pesquisador job kinds to scheduler CATCHUP_WINDOWS"
```

---

### Task 8: Wire Pesquisador into `main.py`

**Files:**
- Modify: `main.py`

This is the largest task. It adds: tool schema, Pesquisador handler, LLM instantiation, tool instantiation, job registration, and wiki repo cloning.

- [ ] **Step 1: Add imports at top of main.py**

After the existing Ana imports, add:

```python
from agents.pesquisador.jobs import (
    make_proactive_research_job,
    make_weekly_digest_job,
    make_wiki_audit_job,
)
from agents.pesquisador.tools import PesquisadorTools
```

- [ ] **Step 2: Add `_PESQUISADOR_TOOLS_SCHEMA` constant**

After `_ANA_TOOLS_SCHEMA`, add:

```python
_PESQUISADOR_TOOLS_SCHEMA = [
    {
        "type": "function",
        "function": {
            "name": "wiki_read",
            "description": "Lê um artigo da wiki de conhecimento. Path relativo, ex: 'domains/backend/auth/oauth2.md'.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Caminho relativo ao artigo"},
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "wiki_write",
            "description": "Cria ou atualiza um artigo na wiki. Inclua frontmatter YAML com domain, confidence, sources, last_updated.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path":    {"type": "string", "description": "Caminho relativo, ex: 'domains/backend/auth/oauth2.md'"},
                    "content": {"type": "string", "description": "Conteúdo completo do artigo em Markdown"},
                },
                "required": ["path", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "wiki_search",
            "description": "Busca artigos na wiki por palavra-chave.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "wiki_list",
            "description": "Lista artigos em um domínio da wiki. Ex: 'domains/backend' ou 'entities'.",
            "parameters": {
                "type": "object",
                "properties": {
                    "domain": {"type": "string", "description": "Pasta a listar, ex: 'domains/backend'. Vazio para raiz."},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": "Pesquisa na web via DuckDuckGo. Retorna título, URL, snippet e is_trusted. Use tier=1 para fontes confiáveis apenas.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query":       {"type": "string", "description": "Termo de busca"},
                    "max_results": {"type": "integer", "description": "Máximo de resultados (padrão 5)"},
                    "tier":        {"type": "integer", "description": "1=fontes confiáveis apenas, 2=todas marcadas, 3=web aberta (padrão)"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "web_fetch",
            "description": "Busca uma página web e extrai o texto. Use para ler artigos completos.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "URL completa da página"},
                },
                "required": ["url"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "youtube_transcript",
            "description": "Extrai a transcrição de um vídeo do YouTube.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "URL do vídeo do YouTube"},
                },
                "required": ["url"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "pdf_extract",
            "description": "Extrai texto de um arquivo PDF.",
            "parameters": {
                "type": "object",
                "properties": {
                    "file_path": {"type": "string", "description": "Caminho do arquivo PDF"},
                },
                "required": ["file_path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "raw_save",
            "description": "Salva material fonte bruto em raw/<category>/<filename>. Fontes são imutáveis.",
            "parameters": {
                "type": "object",
                "properties": {
                    "category": {"type": "string", "description": "Categoria: articles, transcripts, ou pdfs"},
                    "filename": {"type": "string", "description": "Nome do arquivo, ex: 'oauth2-guide.md'"},
                    "content":  {"type": "string", "description": "Conteúdo do material fonte"},
                },
                "required": ["category", "filename", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "git_sync",
            "description": "Faz commit e push das alterações da wiki para o GitHub.",
            "parameters": {
                "type": "object",
                "properties": {
                    "message": {"type": "string", "description": "Mensagem do commit"},
                },
                "required": ["message"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "compile_article",
            "description": "Compila fontes brutas (raw/) em um artigo profissional da wiki usando DeepSeek R1. Use SEMPRE após salvar fontes em raw/ para criar/atualizar artigos.",
            "parameters": {
                "type": "object",
                "properties": {
                    "topic":       {"type": "string", "description": "Nome do tema, ex: 'OAuth2'"},
                    "raw_paths":   {"type": "array", "items": {"type": "string"}, "description": "Lista de caminhos raw/, ex: ['raw/articles/oauth2-guide.md']"},
                    "target_path": {"type": "string", "description": "Caminho do artigo na wiki, ex: 'domains/backend/auth/oauth2.md'"},
                },
                "required": ["topic", "raw_paths", "target_path"],
            },
        },
    },
]
```

- [ ] **Step 3: Add wiki repo cloning in `amain()`**

After the existing storage setup (`store`, `wiki`), add knowledge wiki clone:

```python
    # --- Knowledge Wiki (Pesquisador) ---
    knowledge_dir = data_dir / "knowledge"
    knowledge_wiki_url = os.environ.get("KNOWLEDGE_WIKI_REPO", "")
    if knowledge_wiki_url and not (knowledge_dir / ".git").exists():
        import subprocess
        print(f"Cloning knowledge wiki to {knowledge_dir}...", flush=True)
        subprocess.run(
            ["git", "clone", knowledge_wiki_url, str(knowledge_dir)],
            check=True, capture_output=True, text=True, timeout=60,
        )
    knowledge_wiki = WikiStore(knowledge_dir, autocommit=False)  # git_sync tool handles commits
```

- [ ] **Step 4: Add Pesquisador LLM + tools + budget setup**

After Ana's setup block, add:

```python
    # --- Load Pesquisador ---
    pesq_skill = parse_skill_file("agents/pesquisador/SKILL.md")
    pesq_llm_cfg = LLMConfig(
        provider=pesq_skill.frontmatter.llm.provider,
        model=pesq_skill.frontmatter.llm.model,
        temperature=pesq_skill.frontmatter.llm.temperature,
        fallback=[{"provider": pesq_skill.frontmatter.llm_synthesis.provider,
                   "model": pesq_skill.frontmatter.llm_synthesis.model}],
    )
    pesq_llm = build_llm(pesq_llm_cfg, tracker, agent_name="pesquisador")

    pesq_synthesis_cfg = LLMConfig(
        provider=pesq_skill.frontmatter.llm_synthesis.provider,
        model=pesq_skill.frontmatter.llm_synthesis.model,
        temperature=pesq_skill.frontmatter.llm_synthesis.temperature,
        fallback=[{"provider": pesq_skill.frontmatter.llm.provider,
                   "model": pesq_skill.frontmatter.llm.model}],
    )
    pesq_llm_synthesis = build_llm(pesq_synthesis_cfg, tracker, agent_name="pesquisador")

    pesq_tools = PesquisadorTools(wiki=knowledge_wiki, llm_synthesis=pesq_llm_synthesis)

    pesq_cap = BudgetCap(
        daily_usd=pesq_skill.frontmatter.budget.daily_usd,
        monthly_usd=pesq_skill.frontmatter.budget.monthly_usd,
        on_exceed=pesq_skill.frontmatter.budget.on_exceed,
    ) if pesq_skill.frontmatter.budget else None
```

- [ ] **Step 5: Add `_execute_pesq_tool` and `_handle_pesquisador_message`**

After `_execute_tool` (for Ana), add:

```python
    def _execute_pesq_tool(name: str, args: dict) -> str:
        fn = getattr(pesq_tools, name, None)
        if fn is None:
            return json.dumps({"error": f"ferramenta desconhecida: {name}"})
        try:
            result = fn(**args)
            return json.dumps(result, ensure_ascii=False, default=str)
        except Exception as exc:
            return json.dumps({"error": str(exc)})

    async def _handle_pesquisador_message(body: str, _prefix: str) -> str:
        import litellm

        if pesq_cap:
            r = cap_checker.check("pesquisador", pesq_cap)
            if not r.allowed:
                return "Orçamento diário atingido. Volto amanhã."

        now_brt = datetime.now(_BRT)
        history = store.chat_recent("pesquisador", limit=10)

        system = (
            f"{pesq_skill.frontmatter.goal}\n\n"
            f"{pesq_skill.body}\n\n"
            f"Data/hora atual (BRT): {now_brt.strftime('%Y-%m-%d %H:%M %Z')}\n"
            "Use as ferramentas disponíveis para pesquisar, ler a wiki, "
            "salvar fontes e compilar artigos. Consulte a wiki antes de pesquisar na web."
        )

        context_lines = "\n".join(f"{m['role']}: {m['content']}" for m in history)

        messages: list[dict] = [
            {"role": "system", "content": system},
            {
                "role": "user",
                "content": (
                    f"Histórico recente:\n{context_lines}\n\n"
                    f"Leandro agora: {body}"
                ),
            },
        ]

        full_model = f"{pesq_llm_cfg.provider}/{pesq_llm_cfg.model}"

        with set_context("reactive"):
            for _turn in range(6):
                t0 = time.monotonic()
                resp = litellm.completion(
                    model=full_model,
                    messages=messages,
                    tools=_PESQUISADOR_TOOLS_SCHEMA,
                    tool_choice="auto",
                    temperature=pesq_llm_cfg.temperature,
                )
                duration_ms = int((time.monotonic() - t0) * 1000)

                usage = resp.usage
                tracker.log_call(
                    agent_name="pesquisador",
                    provider=pesq_llm_cfg.provider,
                    model=pesq_llm_cfg.model,
                    input_tokens=getattr(usage, "prompt_tokens", 0) or 0,
                    output_tokens=getattr(usage, "completion_tokens", 0) or 0,
                    context="reactive",
                    duration_ms=duration_ms,
                )

                choice = resp.choices[0]
                msg = choice.message

                tool_calls = getattr(msg, "tool_calls", None) or (msg.get("tool_calls") if isinstance(msg, dict) else None)
                text_content = getattr(msg, "content", None) or (msg.get("content") if isinstance(msg, dict) else None)

                if tool_calls:
                    messages.append(msg if isinstance(msg, dict) else msg.model_dump(exclude_unset=True))
                    for tc in tool_calls:
                        fn_name = tc.function.name if hasattr(tc, "function") else tc["function"]["name"]
                        fn_args_raw = tc.function.arguments if hasattr(tc, "function") else tc["function"]["arguments"]
                        tc_id = tc.id if hasattr(tc, "id") else tc["id"]
                        try:
                            fn_args = json.loads(fn_args_raw) if isinstance(fn_args_raw, str) else fn_args_raw
                        except json.JSONDecodeError:
                            fn_args = {}
                        print(f"[pesq-tool] {fn_name}({fn_args})", flush=True)
                        result = _execute_pesq_tool(fn_name, fn_args)
                        messages.append({
                            "role": "tool",
                            "tool_call_id": tc_id,
                            "content": result,
                        })
                    continue

                reply = text_content or "Pronto."
                store.chat_append("pesquisador", "user", body)
                store.chat_append("pesquisador", "assistant", reply)
                return reply

        return "Não consegui completar a pesquisa."
```

- [ ] **Step 6: Update message routing to dispatch to correct handler**

Replace the single `message_handler=_handle_ana_message` with a router:

```python
    async def _route_message(body: str, prefix: str) -> str:
        if prefix == "pesquisador":
            return await _handle_pesquisador_message(body, prefix)
        return await _handle_ana_message(body, prefix)

    bot = TelegramBot(
        token=token,
        authorized_chat_id=authorized_chat_id,
        message_handler=_route_message,
        usage_command_handler=_handle_usage_cmd,
    )
```

- [ ] **Step 7: Update `_handle_usage_cmd` to show both agents**

Replace the existing `_handle_usage_cmd` to show costs for both agents:

```python
    async def _handle_usage_cmd(args: str) -> str:
        from datetime import timedelta
        since_days = 30
        if "today" in args:
            since_days = 1
        elif "week" in args:
            since_days = 7
        since = datetime.now(timezone.utc) - timedelta(days=since_days)

        lines = [f"📊 Uso últimos {since_days} dia(s)", ""]
        for agent in ("ana", "pesquisador"):
            total = tracker.total_usd(agent_name=agent, since=since)
            by_ctx = tracker.by_context(agent_name=agent, since=since)
            lines.append(f"{agent}:  US$ {total:.4f}")
            for ctx_name, cost in by_ctx.items():
                lines.append(f"  {ctx_name}: US$ {cost:.4f}")
        return "\n".join(lines)
```

- [ ] **Step 8: Register Pesquisador jobs with scheduler**

After Ana's job registrations, add:

```python
    scheduler.add_job(JobSpec("pesquisador", "weekly_digest", "0 20 * * 0",
                              make_weekly_digest_job(pesq_tools, pesq_llm, store, send_to_leandro)))
    scheduler.add_job(JobSpec("pesquisador", "wiki_audit", "0 10 1 * *",
                              make_wiki_audit_job(pesq_tools, pesq_llm, store, send_to_leandro)))
    scheduler.add_job(JobSpec("pesquisador", "proactive_research", "0 14 * * 3,6",
                              make_proactive_research_job(pesq_tools, pesq_llm, pesq_llm_synthesis, store, send_to_leandro)))
```

- [ ] **Step 9: Update startup print**

Change `print("Ana online.", flush=True)` to:

```python
    print("Ana + Pesquisador online.", flush=True)
```

- [ ] **Step 10: Commit**

```bash
git add main.py
git commit -m "feat: wire Pesquisador agent into main.py with routing, tools, and jobs"
```

---

### Task 9: Seed the knowledge wiki repository

**Files:**
- Create: GitHub repo `knowledge-wiki`
- Create: Initial wiki structure files

- [ ] **Step 1: Create the GitHub repo**

```bash
gh repo create knowledge-wiki --private --description "Professional software engineering knowledge wiki (Karpathy LLM Wiki pattern)" --clone
cd knowledge-wiki
```

- [ ] **Step 2: Create initial structure**

```bash
mkdir -p raw/articles raw/transcripts raw/pdfs
mkdir -p domains/backend/authentication domains/backend/databases domains/backend/apis domains/backend/architecture
mkdir -p domains/frontend
mkdir -p domains/infrastructure
mkdir -p domains/security
mkdir -p domains/ai-ml
mkdir -p domains/devops
mkdir -p domains/languages/golang domains/languages/python domains/languages/typescript
mkdir -p entities
mkdir -p concepts
```

- [ ] **Step 3: Create index.md**

```markdown
# Knowledge Wiki — Master Index

> Professional software engineering knowledge base.
> Maintained by Pesquisador (Conexus agent) following Karpathy's LLM Wiki pattern.

## Domains

(Articles will be listed here as they are created)

## Entities

(Technology-specific pages will be listed here)

## Concepts

(Cross-cutting concept pages will be listed here)
```

- [ ] **Step 4: Create log.md**

```markdown
# Wiki Log

<!-- Append-only chronological record of all operations -->
```

- [ ] **Step 5: Create schema.md**

```markdown
# Knowledge Wiki Schema

## Article Quality Rules

1. Every article MUST have YAML frontmatter: domain, confidence, sources, last_updated.
2. Confidence levels: high (3+ trusted sources), medium (1-2 sources or non-trusted), low (single source or outdated).
3. Write like Wikipedia: structured, factual, dense. Every sentence earns its place.
4. Sections adapt to the topic — no fixed template. Quality is constant, structure is flexible.
5. Always include "## See Also" with [[backlinks]] and "## Sources" with raw/ paths.
6. Raw sources are immutable — never edit files in raw/.

## When to Create vs Update

- CREATE when a distinct concept/entity/tool doesn't have its own page.
- UPDATE when new sources refine or extend existing knowledge.
- FLAG contradictions rather than silently overwriting.

## Naming Conventions

- File names: lowercase, hyphenated. Ex: `oauth2.md`, `session-management.md`
- Domain paths: `domains/<area>/<sub-area>/<topic>.md`
- Each domain folder has `_index.md` with overview and links.
- Entities: `entities/<tool-name>.md`
- Concepts: `concepts/<concept-name>.md`

## Log Format

`## [YYYY-MM-DD HH:MM] <operation> | <title>` followed by 1-3 lines.
Operations: ingest, update, audit, proactive.
```

- [ ] **Step 6: Create sources.md**

```markdown
# Trusted Sources

## Official Documentation
- docs.python.org
- go.dev/doc
- react.dev
- developer.mozilla.org (MDN)
- postgresql.org/docs
- nodejs.org/docs

## YouTube Channels
- Andrej Karpathy
- Fireship
- ThePrimeagen

## Blogs & Authors
- martinfowler.com
- blog.pragmaticengineer.com
- karpathy.ai

## Aggregators (top-rated content only)
- news.ycombinator.com (Hacker News)
- github.com/trending
- awesome-* lists (awesome-go, awesome-python, etc.)

## Communities
- dev.to (top rated only)
- r/golang
- r/python
- r/webdev
```

- [ ] **Step 7: Create domain _index.md files**

Create a `_index.md` in each domain folder with just:

```markdown
# <Domain Name>

> Overview of <domain> knowledge.

## Articles

(Will be populated as articles are added)
```

Do this for: backend, frontend, infrastructure, security, ai-ml, devops, languages/golang, languages/python, languages/typescript.

- [ ] **Step 8: Add .gitkeep files to empty directories**

```bash
touch raw/articles/.gitkeep raw/transcripts/.gitkeep raw/pdfs/.gitkeep
touch entities/.gitkeep concepts/.gitkeep
```

- [ ] **Step 9: Commit and push**

```bash
git add -A
git commit -m "chore: seed knowledge wiki with Karpathy 3-layer structure"
git push -u origin main
```

- [ ] **Step 10: Go back to Conexus repo**

```bash
cd ..
```

---

### Task 10: Configure secrets and deploy

**Files:**
- Fly.io secrets
- `.env` file (local dev)

- [ ] **Step 1: Generate GitHub deploy key**

```bash
ssh-keygen -t ed25519 -C "pesquisador@conexus" -f ~/.ssh/pesquisador_deploy -N ""
```

- [ ] **Step 2: Add deploy key to knowledge-wiki repo**

```bash
gh repo deploy-key add ~/.ssh/pesquisador_deploy.pub --repo leandrotcawork/knowledge-wiki --allow-write --title "Pesquisador (Conexus)"
```

- [ ] **Step 3: Add SSH bootstrap to `amain()` before wiki clone**

In `main.py`, add SSH key setup before the knowledge wiki clone block:

```python
    # --- SSH deploy key for knowledge-wiki (Fly.io only) ---
    deploy_key = os.environ.get("GITHUB_WIKI_DEPLOY_KEY", "")
    if deploy_key:
        import subprocess
        ssh_dir = Path.home() / ".ssh"
        ssh_dir.mkdir(mode=0o700, exist_ok=True)
        key_file = ssh_dir / "pesquisador_deploy"
        if not key_file.exists():
            key_file.write_text(deploy_key + "\n")
            key_file.chmod(0o600)
            # Add GitHub to known_hosts
            subprocess.run(
                ["ssh-keyscan", "-t", "ed25519", "github.com"],
                stdout=open(ssh_dir / "known_hosts", "a"),
                stderr=subprocess.DEVNULL,
                timeout=10,
            )
            # Configure git to use this key for knowledge-wiki
            os.environ["GIT_SSH_COMMAND"] = f"ssh -i {key_file} -o StrictHostKeyChecking=accept-new"
```

- [ ] **Step 4: Add secrets to Fly.io**

```bash
fly secrets set DEEPSEEK_API_KEY="<your-deepseek-api-key>" --app conexus
fly secrets set KNOWLEDGE_WIKI_REPO="git@github.com:leandrotcawork/knowledge-wiki.git" --app conexus
fly secrets set GITHUB_WIKI_DEPLOY_KEY="$(cat ~/.ssh/pesquisador_deploy)" --app conexus
```

- [ ] **Step 5: Add openssh-client and git to Dockerfile**

In `deployment/Dockerfile`, ensure these packages are installed:

```dockerfile
RUN apt-get update && apt-get install -y --no-install-recommends \
    git openssh-client \
    && rm -rf /var/lib/apt/lists/*
```

- [ ] **Step 6: Update .env.example**

Add to `.env.example`:

```bash
# Pesquisador
DEEPSEEK_API_KEY=your-deepseek-api-key
KNOWLEDGE_WIKI_REPO=git@github.com:leandrotcawork/knowledge-wiki.git
```

- [ ] **Step 7: Update local .env for testing**

Add the same variables to your local `.env` file with real values.

- [ ] **Step 8: Commit**

```bash
git add .env.example deployment/Dockerfile
git commit -m "chore: add Pesquisador secrets, SSH bootstrap, and Dockerfile deps"
```

---

### Task 11: Local end-to-end test

- [ ] **Step 1: Start the bot locally**

```bash
python main.py
```

Expected: `Ana + Pesquisador online.`

- [ ] **Step 2: Test wiki query (should fail gracefully — empty wiki)**

Send via Telegram: `pesq: o que é OAuth2?`
Expected: Agent searches web, creates article, responds with summary.

- [ ] **Step 3: Test wiki read after creation**

Send: `pesq: o que é OAuth2?`
Expected: This time it finds the article in the wiki and responds from it (no web search).

- [ ] **Step 4: Test YouTube transcript**

Send: `pesq: resuma https://www.youtube.com/watch?v=<any-video-id>`
Expected: Extracts transcript, saves to raw/, compiles article.

- [ ] **Step 5: Test status command**

Send: `pesq: status`
Expected: Wiki stats showing article count.

- [ ] **Step 6: Test source management**

Send: `pesq: fontes`
Expected: Lists trusted sources from sources.md.

- [ ] **Step 7: Test Ana still works**

Send: `olá Ana` (or just plain text)
Expected: Ana responds normally — routing didn't break.

- [ ] **Step 8: Test /uso command**

Send: `/uso today`
Expected: Shows costs for both ana and pesquisador.

- [ ] **Step 9: Fix any issues found and commit**

```bash
git add -A
git commit -m "fix: local testing fixes for Pesquisador"
```

---

### Task 12: Deploy to Fly.io

- [ ] **Step 1: Deploy**

```bash
fly deploy --app conexus
```

- [ ] **Step 2: Check logs**

```bash
fly logs --app conexus
```

Expected: `Ana + Pesquisador online.` in logs, no errors.

- [ ] **Step 3: Test in production**

Send via Telegram: `pesq: pesquise WebSockets`
Expected: Research flow works end-to-end in production.

- [ ] **Step 4: Verify knowledge-wiki repo**

```bash
gh repo view leandrotcawork/knowledge-wiki --web
```

Expected: New commits from the Pesquisador agent visible in the repo.

- [ ] **Step 5: Commit any production fixes**

```bash
git add -A
git commit -m "fix: production deployment fixes for Pesquisador"
```
