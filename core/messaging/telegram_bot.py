"""Telegram bot entry point. Routes authorized messages to a handler callback.

Proactive messages (from the scheduler) are sent via `send_message()`.
The handler is plugged in from main.py after agents are loaded.
"""

from __future__ import annotations

import base64
import os
from typing import Awaitable, Callable

import litellm
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
        self.app.add_handler(MessageHandler(filters.VOICE, self._on_voice))
        self.app.add_handler(MessageHandler(filters.Document.PDF, self._on_document))
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

    async def _on_voice(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._authorized(update):
            return
        await update.message.reply_text("🎙 Ouvi seu áudio, transcrevendo...")
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
                        {"type": "text", "text": "Transcreva esta mensagem de voz. Retorne apenas o texto falado, sem comentários."},
                        {"type": "file", "file": {"file_data": f"data:audio/ogg;base64,{encoded}"}},
                    ],
                }],
            )
            transcribed = resp.choices[0].message.content.strip()
        except Exception as e:
            await update.message.reply_text(f"Não consegui transcrever o áudio: {e}")
            return

        prefix_agent, body = _split_prefix(transcribed)
        reply = await self.message_handler(body, prefix_agent)
        await update.message.reply_text(f'🎙 *"{transcribed}"*\n\n{reply}', parse_mode="Markdown")

    async def _on_document(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._authorized(update):
            return
        doc = update.message.document
        if doc.mime_type != "application/pdf":
            await update.message.reply_text("Só aceito PDFs por enquanto.")
            return
        await update.message.reply_text("📄 Recebi o PDF, processando...")
        try:
            tg_file = await doc.get_file()
            file_bytes = bytes(await tg_file.download_as_bytearray())
            # Save to temp file
            import tempfile, os
            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
                tmp.write(file_bytes)
                tmp_path = tmp.name
            # Route to handler with PDF path in the message
            caption = update.message.caption or ""
            prefix_agent, body = _split_prefix(caption if caption else "pesq: resuma este PDF")
            body = f"{body}\n[PDF_PATH:{tmp_path}]"
            reply = await self.message_handler(body, prefix_agent)
            await update.message.reply_text(reply)
            os.unlink(tmp_path)
        except Exception as e:
            await update.message.reply_text(f"Erro ao processar PDF: {e}")

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
    """Parse 'pesq: olá' -> ('pesquisador', 'olá'). '/ana olá' -> ('ana', 'olá'). Plain text -> ('', text)."""
    # Colon-prefix format: "pesq: text" or "pesq:text"
    _COLON_PREFIXES = {"pesq": "pesquisador"}
    for short, full in _COLON_PREFIXES.items():
        if text.lower().startswith(f"{short}:"):
            body = text[len(short) + 1:].lstrip()
            return full, body

    # Slash-prefix format: "/ana text"
    if text.startswith("/") and " " in text:
        head, rest = text.split(" ", 1)
        name = head[1:]
        if name in {"ana", "pesquisador", "researcher", "code_manager"}:
            return name, rest
    return "", text
