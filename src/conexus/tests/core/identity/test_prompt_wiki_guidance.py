from conexus.core.identity.prompt import DEFAULT_MEMORY_PROMPT_PT_BR


def test_prompt_mentions_three_file_pattern():
    p = DEFAULT_MEMORY_PROMPT_PT_BR.lower()
    assert "index.md" in p
    assert "log.md" in p


def test_prompt_mentions_citation_format():
    assert "[" in DEFAULT_MEMORY_PROMPT_PT_BR and "#" in DEFAULT_MEMORY_PROMPT_PT_BR
    assert "wiki_search" in DEFAULT_MEMORY_PROMPT_PT_BR


def test_prompt_mentions_lint_tool():
    assert "wiki_lint" in DEFAULT_MEMORY_PROMPT_PT_BR
