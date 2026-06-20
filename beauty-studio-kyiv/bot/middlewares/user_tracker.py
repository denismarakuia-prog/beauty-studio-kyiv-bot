"""Register/update every interacting user in the database automatically."""
from __future__ import annotations

from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject

from bot.database.repositories import UserRepository


class UserTrackerMiddleware(BaseMiddleware):
    def __init__(self, user_repo: UserRepository) -> None:
        super().__init__()
        self._repo = user_repo

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        user = None
        if isinstance(event, Message) and event.from_user:
            user = event.from_user
        elif isinstance(event, CallbackQuery) and event.from_user:
            user = event.from_user

        if user is not None:
            try:
                await self._repo.upsert_user(
                    telegram_id=user.id,
                    username=user.username,
                    first_name=user.first_name,
                )
            except Exception:
                pass  # Never break the handler because of a DB hiccup

        return await handler(event, data)
