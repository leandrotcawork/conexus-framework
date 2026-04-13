"""Tests for TelegramBot group/private chat logic."""

from core.messaging.telegram_bot import TelegramBot


def test_strip_mention():
    bot = TelegramBot(
        token="fake",
        agent_name="pesquisador",
        authorized_user_id=123,
    )
    bot._bot_username = "pesquisador_conexus_bot"
    assert bot._strip_mention("@pesquisador_conexus_bot pesquise OAuth2") == "pesquise OAuth2"
    assert bot._strip_mention("pesquise OAuth2") == "pesquise OAuth2"
    assert bot._strip_mention("ola @pesquisador_conexus_bot como vai") == "ola como vai"
