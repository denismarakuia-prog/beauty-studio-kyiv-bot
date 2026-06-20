"""Simple per-user rate-limiter — silently drops over-frequent updates."""
from __future__ import annotations

import time
from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject

_DEFAULT_RATE = 0.5  # seconds between allowed updates per user


class ThrottlingMiddleware(BaseMiddleware):
    def __init__(self, rate: float = _DEFAULT_RATE) -> None:
        super().__init__()
        self._rate = rate
        self._last: Dict[int, float] = {}

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        user_id: int | None = None
        if isinstance(event, (Message, CallbackQuery)) and event.from_user:
            user_id = event.from_user.id

        if user_id is not None:
            now = time.monotonic()
            if now - self._last.get(user_id, 0.0) < self._rate:
                if isinstance(event, CallbackQuery):
                    try:
                        await event.answer()
                    except Exception:
                        pass
                return  # drop silently
            self._last[user_id] = now

            # Prevent unbounded growth
            if len(self._last) > 50_000:
                oldest = min(self._last, key=lambda k: self._last[k])
                del self._last[oldest]

        return await handler(event, data)
