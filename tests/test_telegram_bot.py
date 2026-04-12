from core.messaging.telegram_bot import _split_prefix


def test_plain_text_no_prefix():
    assert _split_prefix("olá ana") == ("", "olá ana")


def test_ana_prefix():
    assert _split_prefix("/ana agende uma reunião") == ("ana", "agende uma reunião")


def test_researcher_prefix():
    assert _split_prefix("/researcher últimas de IA") == ("researcher", "últimas de IA")


def test_unknown_prefix_is_not_split():
    assert _split_prefix("/foo hello") == ("", "/foo hello")
