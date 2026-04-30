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
