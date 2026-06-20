"""AI-powered Q&A assistant — one question per turn, then back to main menu."""
from __future__ import annotations

import logging

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message

from bot.keyboards.builders import BTN_AI, MENU_BUTTON_LABELS, main_reply_keyboard
from bot.services.ai_service import AIService

logger = logging.getLogger(__name__)
router = Router(name="ai_assistant")


class AIStates(StatesGroup):
    waiting = State()


@router.message(F.text == BTN_AI)
async def ask_start(message: Message, state: FSMContext) -> None:
    await state.set_state(AIStates.waiting)
    await message.answer(
        "💬 <b>Запитайте нашого AI-консультанта</b>\n\n"
        "Напишіть своє питання, і я відповім якомога швидше ✍️\n\n"
        "<i>Можна запитати про послуги, ціни, час роботи або будь-що інше!</i>",
        reply_markup=main_reply_keyboard(),
        parse_mode="HTML",
    )


@router.message(AIStates.waiting, F.text, ~F.text.in_(MENU_BUTTON_LABELS))
async def handle_question(
    message: Message, bot: Bot, state: FSMContext, ai_service: AIService
) -> None:
    question = (message.text or "").strip()
    if not question:
        return

    await state.clear()

    try:
        await bot.send_chat_action(chat_id=message.chat.id, action="typing")
    except Exception:
        pass

    answer = await ai_service.ask(question)

    await message.answer(
        f"💬 {answer}",
        reply_markup=main_reply_keyboard(),
        parse_mode="HTML",
    )
