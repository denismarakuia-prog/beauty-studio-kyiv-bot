"""Register/update every interacting user in the database automatically.
Also injects `lang` (the user's saved language, or None if not yet chosen)
into the handler data context, so any handler can request `lang: str` as a
parameter without an extra DB round-trip of its own."""
from __future__ import annotations

from typing import Any, Awaitable, Callable, Dict, Optional

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject

from bot.database.repositories import UserRepository
from bot.i18n import DEFAULT_LANG


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

        raw_lang: Optional[str] = None
        if user is not None:
            try:
                await self._repo.upsert_user(
                    telegram_id=user.id,
                    username=user.username,
                    first_name=user.first_name,
                )
                raw_lang = await self._repo.get_language(user.id)
            except Exception:
                pass  # Never break the handler because of a DB hiccup

        # `lang` (always a valid, usable language) for display/rendering.
        # `lang_chosen` (True/False) lets the language gate distinguish
        # "never picked yet" from "defaulted".
        data["lang"] = raw_lang or DEFAULT_LANG
        data["lang_chosen"] = bool(raw_lang)

        return await handler(event, data)
