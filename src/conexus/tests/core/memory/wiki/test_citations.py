from conexus.core.memory.wiki.citations import format_citation, parse_citations, slug_anchor


def test_slug_anchor_basic():
    assert slug_anchor("# Hello World") == "hello-world"
    assert slug_anchor("## Wiki Redesign ? 2026") == "wiki-redesign-2026"


def test_format_citation():
    assert format_citation("notes.md", ["# Notes", "## Today"]) == "[notes.md#today]"


def test_parse_citations():
    text = "Conexus is in pt-BR [conventions.md#language] and uses [arch.md#wiki-layer]."
    cites = parse_citations(text)
    assert ("conventions.md", "language") in cites
    assert ("arch.md", "wiki-layer") in cites


def test_parse_citations_ignores_normal_links():
    text = "Visit [GitHub](https://github.com) for details."
    assert parse_citations(text) == []


def test_format_no_header_path_uses_filename():
    assert format_citation("readme.md", []) == "[readme.md]"
