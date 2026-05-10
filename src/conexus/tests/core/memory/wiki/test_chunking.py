from __future__ import annotations

from conexus.core.memory.wiki.chunking import Chunk, markdown_chunks


def test_no_headings_single_chunk() -> None:
    chunks = markdown_chunks("just plain text\nover two lines")

    assert len(chunks) == 1
    assert chunks[0] == Chunk(
        header_path=(),
        line_start=1,
        line_end=2,
        body="just plain text\nover two lines",
    )


def test_split_by_h1_h2_h3() -> None:
    text = "# A\nintro\n## B\nbody\n### C\ndeep\n## D\nmore\n"

    chunks = markdown_chunks(text)
    paths = [chunk.header_path for chunk in chunks]

    assert ("# A",) in paths
    assert ("# A", "## B") in paths
    assert ("# A", "## B", "### C") in paths
    assert ("# A", "## D") in paths


def test_header_path_lineage_is_preserved() -> None:
    text = "# Root\nroot\n## Child\nchild\n### Leaf\nleaf\n"

    chunks = markdown_chunks(text)

    leaf = next(chunk for chunk in chunks if chunk.header_path == ("# Root", "## Child", "### Leaf"))
    assert leaf.body.startswith("### Leaf")


def test_frontmatter_excluded_from_chunks() -> None:
    text = "---\ncreated: 2026-05-09\nupdated: 2026-05-09\n---\n# Heading\nbody\n"

    chunks = markdown_chunks(text)

    assert chunks[0].header_path == ("# Heading",)
    assert chunks[0].line_start == 5
    assert all("created:" not in chunk.body for chunk in chunks)
    assert all("updated:" not in chunk.body for chunk in chunks)


def test_oversized_section_recursive_split() -> None:
    big = "# H\n" + ("filler " * 1200)

    chunks = markdown_chunks(big, max_tokens=200, overlap_tokens=20)

    assert len(chunks) > 1
    assert all(chunk.header_path == ("# H",) for chunk in chunks)


def test_line_ranges_correct() -> None:
    text = "# A\nl2\nl3\n## B\nl5\n"

    chunks = markdown_chunks(text)

    top = next(chunk for chunk in chunks if chunk.header_path == ("# A",))
    assert top.line_start == 1
    assert top.line_end == 3

    child = next(chunk for chunk in chunks if chunk.header_path == ("# A", "## B"))
    assert child.line_start == 4
    assert child.line_end == 5


def test_empty_after_frontmatter_no_chunks() -> None:
    text = "---\ncreated: 2026-05-09\n---\n"

    chunks = markdown_chunks(text)

    assert chunks == []
