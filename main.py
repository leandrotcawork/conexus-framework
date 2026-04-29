"""Conexus entry point."""

from __future__ import annotations

import asyncio

from adapters.telegram_runner import run


if __name__ == "__main__":
    asyncio.run(run())
