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
        from ddgs import DDGS

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

    # Max chars to return from web_fetch / youtube_transcript.
    # ~20K chars ≈ 5K tokens — rich enough for deep articles while keeping loop manageable.
    _MAX_FETCH_CHARS = 20000

    def web_fetch(self, url: str) -> str:
        """Fetch a web page and extract its text content (truncated to ~20K chars)."""
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
        full_text = "\n".join(extractor.parts)
        if len(full_text) > self._MAX_FETCH_CHARS:
            return full_text[:self._MAX_FETCH_CHARS] + f"\n\n[... truncado, {len(full_text)} chars total]"
        return full_text

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
        full_text = "\n".join(lines)
        if len(full_text) > self._MAX_FETCH_CHARS:
            return full_text[:self._MAX_FETCH_CHARS] + f"\n\n[... truncado, {len(full_text)} chars total]"
        return full_text

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

    def raw_save(self, category: str, filename: str, content: str, source_url: str = "") -> dict:
        """Save source material to raw/<category>/<filename>. Immutable -- rejects overwrites.
        source_url is stored so compile_article can determine trust level."""
        path = f"raw/{category}/{filename}"
        try:
            self.wiki.read(path)
            return {"error": f"raw file already exists: {path}. Raw sources are immutable."}
        except FileNotFoundError:
            pass
        # Prepend source URL as metadata comment if provided
        if source_url:
            content = f"<!-- source_url: {source_url} -->\n{content}"
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
        # Extract source_url from raw files (embedded by raw_save as HTML comment)
        trusted_domains = self._load_trusted_domains()
        trusted_count = 0
        for rc in raw_contents:
            match = re.search(r"<!-- source_url: (.+?) -->", rc)
            if match:
                url = match.group(1)
                if self._is_trusted_url(url, trusted_domains):
                    trusted_count += 1
        total = len(raw_paths)
        if trusted_count >= 3:
            confidence = "high"
        elif trusted_count >= 1:
            confidence = "medium"
        else:
            confidence = "low"

        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        # Read schema.md for wiki conventions (tech stack, quality rules)
        schema_context = ""
        try:
            schema_context = self.wiki.read("schema.md")
        except FileNotFoundError:
            pass

        prompt = (
            f"Write a comprehensive technical reference about '{topic}'.\n\n"
            f"Wiki conventions:\n{schema_context}\n\n"
            f"Raw sources (use as references and for latest updates, but DO NOT limit yourself to them):\n"
            f"{''.join(raw_contents)}\n\n"
            f"Requirements:\n"
            f"1. Start with raw YAML frontmatter (NOT inside a code block): "
            f"domain (infer from target_path '{target_path}'), "
            f"confidence: {confidence}, sources: {total}, last_updated: {today}\n"
            f"2. USE YOUR FULL KNOWLEDGE. The raw sources are references and grounding, not the "
            f"ceiling. You know this topic deeply — write everything a senior engineer needs to know. "
            f"The sources verify facts and provide latest updates (e.g., new RFCs, deprecations).\n"
            f"3. Include ASCII diagrams showing flows, architecture, and how components interact. "
            f"Explain related concepts inline (e.g., if OAuth2 uses JWT, explain JWT structure, "
            f"if it uses PKCE, explain the full PKCE mechanism).\n"
            f"4. Include practical guidance: decision matrices, when to use what, "
            f"common pitfalls, how to avoid them, and which tools/libraries to consider.\n"
            f"5. Code examples use the preferred tech stack from schema.md. Keep them practical "
            f"but focused — knowledge and understanding come first, code illustrates patterns.\n"
            f"6. Cover in depth: what it is, how it works internally, the components and how they "
            f"connect, related technologies, implementation patterns, security considerations.\n"
            f"7. End with '## See Also' with [[backlinks]] and '## Sources' listing raw/ paths.\n"
            f"8. Write in Portuguese (pt-BR).\n"
        )

        with set_context("synthesis"):
            article = self.llm_synthesis.complete([
                {"role": "system", "content": (
                    "You are a senior software engineer with deep expertise writing the definitive "
                    "technical reference on each topic. Use your full knowledge — the raw sources are "
                    "for grounding and latest updates, not your only input. Write the article a senior "
                    "engineer would bookmark: thorough, practical, opinionated. Include diagrams, "
                    "explain internals, cover related concepts, give real examples. "
                    "No length limit — be as comprehensive as the topic demands."
                )},
                {"role": "user", "content": prompt},
            ], max_tokens=16000)

        self.wiki.write(target_path, article)

        # Update index.md and log.md atomically
        self.wiki.update_index(target_path, f"{topic} -- confidence: {confidence}")
        self.wiki.append_log(
            "ingest", topic,
            f"Compiled {len(raw_paths)} sources into {target_path} (confidence: {confidence})"
        )

        return {"ok": True, "path": target_path, "confidence": confidence}

    def git_sync(self, message: str) -> dict:
        """Commit and push all wiki changes to GitHub."""
        self.wiki._git_commit_push(message)
        return {"ok": True}
