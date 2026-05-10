"""Notes pack tool descriptions must disambiguate from facts/wiki."""
from __future__ import annotations


def test_add_note_warns_against_personal_info():
    from packs.notes.tools import NoteTools
    desc = NoteTools._tool_schemas["add_note"]["description"]
    assert "memory_set" in desc
    assert "wiki_write" in desc
    assert "efêmera" in desc.lower() or "ephemeral" in desc.lower()


def test_list_notes_description_present():
    from packs.notes.tools import NoteTools
    assert NoteTools._tool_schemas["list_notes"]["description"]


def test_search_notes_description_present():
    from packs.notes.tools import NoteTools
    assert NoteTools._tool_schemas["search_notes"]["description"]
