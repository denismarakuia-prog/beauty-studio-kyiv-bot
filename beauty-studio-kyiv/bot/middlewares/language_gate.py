"""
On a user's very first interaction (no language saved yet), intercept
EVERY update — regardless of what was tapped or typed — and show the
language picker instead of running the normal handler. Once they pick a
language, every later update proceeds normally.

Registered as an outer middleware, AFTER UserTrackerMiddleware (so
`data["lang_chosen"]` is already available here without an extra DB call).
"""
from __future__ import annotations

from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject

from bot.i18n import t
from bot.keyboards.builders import LANG_CALLBACK_PREFIX, language_picker_keyboard


class LanguageGateMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        if data.get("lang_chosen"):
            return await handler(event, data)

        # Let the language-selection callback itself through to its handler.
        if isinstance(event, CallbackQuery) and (event.data or "").startswith(LANG_CALLBACK_PREFIX):
            return await handler(event, data)

        message = None
        if isinstance(event, Message):
            message = event
        elif isinstance(event, CallbackQuery):
            message = event.message
            try:
                await event.answer()
            except Exception:
                pass

        if message is not None:
            try:
                await message.answer(
                    t("choose_language", "uk"),
                    reply_markup=language_picker_keyboard(),
                )
            except Exception:
                pass

        return None  # gate closed — do not call the real handler yet