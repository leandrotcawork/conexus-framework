from conexus.core.llm.context_tag import current_context, set_context


def test_default_empty():
    assert current_context() == "unknown"


def test_set_and_read():
    with set_context("scheduler"):
        assert current_context() == "scheduler"
    assert current_context() == "unknown"
