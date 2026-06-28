"""AI-powered Q&A assistant — one question per turn, then back to main menu."""
from __future__ import annotations

import logging

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message

from bot.i18n import t
from bot.keyboards.builders import BTN_AI, MENU_BUTTON_LABELS, main_reply_keyboard
from bot.services.ai_service import AIService

logger = logging.getLogger(__name__)
router = Router(name="ai_assistant")


class AIStates(StatesGroup):
    waiting = State()


@router.message(F.text.in_(set(BTN_AI.values())))
async def ask_start(message: Message, state: FSMContext, lang: str) -> None:
    await state.set_state(AIStates.waiting)
    await message.answer(
        t("ai_intro", lang),
        reply_markup=main_reply_keyboard(lang),
        parse_mode="HTML",
    )


@router.message(AIStates.waiting, F.text, ~F.text.in_(MENU_BUTTON_LABELS))
async def handle_question(
    message: Message, bot: Bot, state: FSMContext, ai_service: AIService, lang: str
) -> None:
    question = (message.text or "").strip()
    if not question:
        return

    await state.clear()

    try:
        await bot.send_chat_action(chat_id=message.chat.id, action="typing")
    except Exception:
        pass

    user_id = message.from_user.id if message.from_user else message.chat.id
    # `lang` here is the user's SAVED preference, used only as a fallback —
    # ai_service.ask() always detects the language of THIS specific message
    # first and answers in that language, per the per-message detection
    # requirement (a Ukrainian-preference user asking in Russian still gets
    # a Russian answer).
    answer = await ai_service.ask(question, user_id=user_id, fallback_lang=lang)

    await message.answer(
        f"💬 {answer}",
        reply_markup=main_reply_keyboard(lang),
        parse_mode="HTML",
    )
