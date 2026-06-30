"""
AI-powered Q&A assistant — sticky chat mode.

Pressing "🤖 AI Консультант" once activates AI mode for every following
text message — the user is NOT required to press the button again between
questions. AI mode ends automatically the moment the user taps any of the
other main-menu buttons (Back to menu / Price / Contacts / About / My
booking / start a booking) — those are excluded from this handler's own
filter below, so they fall through to their own routers exactly as before;
nothing about that escape mechanism changed.

A tiny, temporary "last mentioned service" is kept in FSM data (a single
string) so a one-word follow-up like "а сколько по времени?" right after
asking about a service can be answered specifically, without any chat
history ever being sent to OpenAI and without touching the database. It is
wiped the instant AI mode ends, because every other entry handler in this
project already calls state.clear() as its first action (unchanged,
pre-existing behaviour) — there is nothing extra to clean up here.
"""
from __future__ import annotations

import logging

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message

from bot.i18n import t
from bot.keyboards.builders import BTN_AI, MENU_BUTTON_LABELS, main_reply_keyboard
from bot.services.ai_service import AIService, detect_service_mention

logger = logging.getLogger(__name__)
router = Router(name="ai_assistant")


class AIStates(StatesGroup):
    waiting = State()


@router.message(F.text.in_(set(BTN_AI.values())))
async def ask_start(message: Message, state: FSMContext, lang: str) -> None:
    await state.clear()
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

    try:
        await bot.send_chat_action(chat_id=message.chat.id, action="typing")
    except Exception:
        pass

    user_id = message.from_user.id if message.from_user else message.chat.id

    data = await state.get_data()
    context_service_id = data.get("last_service_id", "")

    # `lang` here is the user's SAVED preference, used only as a fallback —
    # ai_service.ask() always detects the language of THIS specific message
    # first and answers in that language, per the per-message detection
    # requirement (a Ukrainian-preference user asking in Russian still gets
    # a Russian answer).
    answer = await ai_service.ask(
        question,
        user_id=user_id,
        fallback_lang=lang,
        context_service_id=context_service_id,
    )

    # Remember the service this turn was about (if any), purely in memory
    # via FSM data, so a short follow-up next turn ("а сколько по
    # времени?") can still be answered specifically. If this turn didn't
    # mention a service, keep whatever was remembered from before.
    mentioned = detect_service_mention(question)
    if mentioned:
        await state.update_data(last_service_id=mentioned)

    # Stay in AI chat mode for follow-up questions — the user only needs to
    # tap "🤖 AI Консультант" once. Re-entering the SAME state (rather than
    # clearing it) is what makes this sticky; any of the main-menu buttons
    # still correctly exits AI mode via the filter exclusion above.
    await state.set_state(AIStates.waiting)

    await message.answer(
        f"💬 {answer}",
        reply_markup=main_reply_keyboard(lang),
        parse_mode="HTML",
    )
