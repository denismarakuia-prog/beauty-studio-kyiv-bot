"""
/start command — sends the welcome message with the persistent main reply keyboard.
Also acts as a safety-net catch-all so the user is never stuck without /start.
"""
from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from bot.keyboards.builders import main_reply_keyboard
from bot.salon_data import SALON_NAME

logger = logging.getLogger(__name__)
router = Router(name="start")


def _welcome_text() -> str:
    return (
        f"✨ <b>{SALON_NAME}</b>\n\n"
        "Ласкаво просимо до нашого салону краси ❤️\n\n"
        "Оберіть дію на клавіатурі нижче 👇"
    )


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer(
        _welcome_text(),
        reply_markup=main_reply_keyboard(),
        parse_mode="HTML",
    )


@router.message(F.text)
async def fallback_text(message: Message, state: FSMContext) -> None:
    """
    Catch-all for unrecognised plain text.
    By the time an update reaches this router, every dedicated menu / FSM-step
    handler in earlier routers has already had a chance to match — if we're
    here, the user typed something the bot doesn't understand. Reset state
    defensively and re-show the main menu rather than leaving them stuck.
    """
    await state.clear()
    await message.answer(
        "Не розумію цю команду 🙂\nСкористайтесь кнопками на клавіатурі нижче 👇",
        reply_markup=main_reply_keyboard(),
        parse_mode="HTML",
    )
