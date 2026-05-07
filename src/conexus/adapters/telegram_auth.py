"""Telegram magic-link callback factory for OAuth connector auth_required events."""
from __future__ import annotations

import os
import secrets
from typing import TYPE_CHECKING, Any, Awaitable, Callable

if TYPE_CHECKING:
    from conexus.core.agent_handler import NeedsAuthEvent


def make_telegram_auth_callback(
    *,
    chat_id: int,
    user_id: str,
    bot: Any,  # telegram.Bot
    state_secret: bytes,
    oauth_base: str | None = None,
    nonce_fn: Callable[[], str] | None = None,
) -> Callable[[NeedsAuthEvent], Awaitable[None]]:
    """Return an async callback that sends a Telegram inline keyboard magic link.

    oauth_base defaults to CONEXUS_OAUTH_BASE env var or http://localhost:8000.
    nonce_fn defaults to secrets.token_urlsafe(16) — injectable for tests.
    """
    base = oauth_base or os.environ.get("CONEXUS_OAUTH_BASE", "http://localhost:8000")
    _nonce_fn = nonce_fn or (lambda: secrets.token_urlsafe(16))

    async def _on_auth_required(ev: NeedsAuthEvent) -> None:
        from telegram import InlineKeyboardButton, InlineKeyboardMarkup
        from conexus.core.oauth.state import encode_state

        nonce = _nonce_fn()
        bot_user = await bot.get_me()
        return_to = f"https://t.me/{bot_user.username}?start=auth_done"
        state = encode_state(
            state_secret,
            user_id=user_id,
            server_url=ev.server_url,
            return_to=return_to,
            nonce=nonce,
        )
        url = f"{base}/oauth/start?state={state}"
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("🔗 Conectar conta", url=url)]])
        await bot.send_message(
            chat_id=chat_id,
            text="Preciso de acesso para essa ferramenta. Toque para conectar:",
            reply_markup=kb,
        )

    return _on_auth_required
