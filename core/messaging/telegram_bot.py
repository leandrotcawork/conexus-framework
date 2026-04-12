"""Telegram bot entry point. Routes authorized messages to a handler callback.

Proactive messages (from the scheduler) are sent via `send_message()`.
The handler is plugged in from main.py after agents are loaded.
"""

from __future__ import annotations

from typing import Awaitable, Callable

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters


MessageHandlerFn = Callable[[str, str], Awaitable[str]]
# signature: handler(chat_text, prefix_agent_or_empty) -> reply_text


class TelegramBot:
    def __init__(
        self,
        token: str,
        authorized_chat_id: int,
        message_handler: MessageHandlerFn,
        usage_command_handler: Callable[[str], Awaitable[str]] | None = None,
    ):
        self.token = token
        self.authorized_chat_id = authorized_chat_id
        self.message_handler = message_handler
        self.usage_command_handler = usage_command_handler
        self.app: Application | None = None

    def build(self) -> Application:
        self.app = Application.builder().token(self.token).build()
        self.app.add_handler(CommandHandler("uso", self._on_usage))
        self.app.add_handler(CommandHandler("usage", self._on_usage))
        self.app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self._on_message))
        return self.app

    async def send_message(self, text: str) -> None:
        if self.app is None:
            raise RuntimeError("bot not built")
        await self.app.bot.send_message(chat_id=self.authorized_chat_id, text=text)

    # ----- handlers -----

    async def _on_message(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._authorized(update):
            return
        text = update.message.text or ""
        prefix_agent, body = _split_prefix(text)
        reply = await self.message_handler(body, prefix_agent)
        await update.message.reply_text(reply)

    async def _on_usage(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._authorized(update):
            return
        args = " ".join(ctx.args) if ctx.args else ""
        if self.usage_command_handler is None:
            await update.message.reply_text("uso não disponível")
            return
        reply = await self.usage_command_handler(args)
        await update.message.reply_text(reply)

    def _authorized(self, update: Update) -> bool:
        return update.effective_chat and update.effective_chat.id == self.authorized_chat_id


def _split_prefix(text: str) -> tuple[str, str]:
    """Parse '/ana olá' -> ('ana', 'olá'). '/researcher foo' -> ('researcher', 'foo'). Plain text -> ('', text)."""
    if text.startswith("/") and " " in text:
        head, rest = text.split(" ", 1)
        name = head[1:]
        if name in {"ana", "researcher", "code_manager"}:
            return name, rest
    return "", text
