"""Channel-agnostic messaging interface.

Any future channel (Slack, API gateway, web) implements ``MessageChannel``.
``TelegramBot`` already satisfies this protocol via its ``send`` method.

Usage::

    channel: MessageChannel = TelegramBot(...)
    await channel.send("Hello!")
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class MessageChannel(Protocol):
    """Minimal interface that all messaging channels must implement."""

    async def send(self, text: str, chat_id: int | str | None = None) -> None:
        """Send *text* to *chat_id* (defaults to the primary configured user)."""
        ...
