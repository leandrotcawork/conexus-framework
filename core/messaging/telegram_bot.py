"""Telegram bot entry point. Each agent gets its own bot instance.

In private chat: the bot always responds (no prefix needed).
In group chat: the bot responds only when @mentioned or replied to.
Proactive messages (from the scheduler) are sent via `send_message()`.
"""

from __future__ import annotations

import base64
import os
from typing import Awaitable, Callable

import litellm
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters


MessageHandlerFn = Callable[[str, str], Awaitable[str]]
# signature: handler(chat_text, agent_name) -> reply_text


class TelegramBot:
    def __init__(
        self,
        token: str,
        agent_name: str,
        authorized_user_id: int,
        group_chat_ids: list[int] | None = None,
        message_handler: MessageHandlerFn | None = None,
        usage_command_handler: Callable[[str], Awaitable[str]] | None = None,
    ):
        self.token = token
        self.agent_name = agent_name
        self.authorized_user_id = authorized_user_id
        self.group_chat_ids: set[int] = set(group_chat_ids or [])
        self.message_handler = message_handler
        self.usage_command_handler = usage_command_handler
        self.app: Application | None = None
        self._bot_username: str | None = None  # filled after build()

    def build(self) -> Application:
        self.app = Application.builder().token(self.token).build()
        self.app.add_handler(CommandHandler("uso", self._on_usage))
        self.app.add_handler(CommandHandler("usage", self._on_usage))
        self.app.add_handler(MessageHandler(filters.VOICE, self._on_voice))
        self.app.add_handler(MessageHandler(filters.Document.PDF, self._on_document))
        self.app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self._on_message))
        return self.app

    async def post_init(self) -> None:
        """Call after app.initialize() to cache the bot username."""
        if self.app:
            me = await self.app.bot.get_me()
            self._bot_username = me.username

    async def send_message(self, text: str, chat_id: int | None = None) -> None:
        if self.app is None:
            raise RuntimeError("bot not built")
        target = chat_id or self.authorized_user_id
        await self.app.bot.send_message(chat_id=target, text=text)

    # ----- handlers -----

    def _is_group(self, update: Update) -> bool:
        chat_type = update.effective_chat.type if update.effective_chat else ""
        return chat_type in ("group", "supergroup")

    def _authorized(self, update: Update) -> bool:
        if not update.effective_chat:
            return False
        chat_id = update.effective_chat.id
        user_id = update.effective_user.id if update.effective_user else 0
        # Private chat: must be the authorized user
        if not self._is_group(update):
            return chat_id == self.authorized_user_id
        # Group chat: must be an allowed group, from the authorized user
        return chat_id in self.group_chat_ids and user_id == self.authorized_user_id

    def _is_for_me(self, update: Update) -> bool:
        """In group chat, only respond if @mentioned or replied to."""
        if not self._is_group(update):
            return True  # private chat: always respond

        msg = update.message
        if not msg:
            return False

        # Check if replying to one of this bot's messages
        if msg.reply_to_message and msg.reply_to_message.from_user:
            if msg.reply_to_message.from_user.username == self._bot_username:
                return True

        # Check if @mentioned in the text
        text = msg.text or msg.caption or ""
        if self._bot_username and f"@{self._bot_username}" in text:
            return True

        return False

    def _strip_mention(self, text: str) -> str:
        """Remove @bot_username from text."""
        if self._bot_username:
            text = text.replace(f"@{self._bot_username}", "")
            text = " ".join(text.split())  # collapse whitespace
        return text.strip()

    async def _on_message(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._authorized(update) or not self._is_for_me(update):
            return
        text = update.message.text or ""
        body = self._strip_mention(text)
        if not body:
            return
        reply = await self.message_handler(body, self.agent_name)
        await update.message.reply_text(reply)

    async def _on_voice(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._authorized(update) or not self._is_for_me(update):
            return
        await update.message.reply_text("🎙 Ouvi seu audio, transcrevendo...")
        try:
            tg_file = await update.message.voice.get_file()
            audio_bytes = bytes(await tg_file.download_as_bytearray())
            encoded = base64.b64encode(audio_bytes).decode("utf-8")

            model = os.environ.get("GEMINI_MODEL", "gemini/gemini-2.5-flash")
            resp = litellm.completion(
                model=model,
                messages=[{
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "Transcreva esta mensagem de voz. Retorne apenas o texto falado, sem comentarios."},
                        {"type": "file", "file": {"file_data": f"data:audio/ogg;base64,{encoded}"}},
                    ],
                }],
            )
            transcribed = resp.choices[0].message.content.strip()
        except Exception as e:
            await update.message.reply_text(f"Nao consegui transcrever o audio: {e}")
            return

        reply = await self.message_handler(transcribed, self.agent_name)
        await update.message.reply_text(f'🎙 *"{transcribed}"*\n\n{reply}', parse_mode="Markdown")

    async def _on_document(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._authorized(update) or not self._is_for_me(update):
            return
        doc = update.message.document
        if doc.mime_type != "application/pdf":
            await update.message.reply_text("So aceito PDFs por enquanto.")
            return
        await update.message.reply_text("📄 Recebi o PDF, processando...")
        import tempfile, os
        tmp_path = None
        try:
            tg_file = await doc.get_file()
            file_bytes = bytes(await tg_file.download_as_bytearray())
            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
                tmp.write(file_bytes)
                tmp_path = tmp.name
            body = f"resuma este PDF\n[PDF_PATH:{tmp_path}]"
            reply = await self.message_handler(body, self.agent_name)
            await update.message.reply_text(reply)
        except Exception as e:
            await update.message.reply_text(f"Erro ao processar PDF: {e}")
        finally:
            if tmp_path and os.path.exists(tmp_path):
                os.unlink(tmp_path)

    async def _on_usage(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._authorized(update):
            return
        args = " ".join(ctx.args) if ctx.args else ""
        if self.usage_command_handler is None:
            await update.message.reply_text("uso nao disponivel")
            return
        reply = await self.usage_command_handler(args)
        await update.message.reply_text(reply)
