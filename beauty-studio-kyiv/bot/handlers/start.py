"""
/start command — sends the welcome message with the persistent main reply keyboard.
Also handles the one-time language selection and the global catch-alls so
the user is never stuck without /start.
"""
from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot.database.repositories import UserRepository
from bot.i18n import normalize_lang, t
from bot.keyboards.builders import (
    EMPTY_KEYBOARD,
    LANG_CALLBACK_PREFIX,
    language_picker_keyboard,
    main_reply_keyboard,
)
from bot.salon_data import SALON_NAME

logger = logging.getLogger(__name__)
router = Router(name="start")


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext, lang: str) -> None:
    await state.clear()
    await message.answer(
        t("welcome", lang, salon_name=SALON_NAME),
        reply_markup=main_reply_keyboard(lang),
        parse_mode="HTML",
    )


@router.message(Command("language"))
async def cmd_language(message: Message) -> None:
    """Lets a user change their language preference at any time."""
    await message.answer(
        t("choose_language", "uk"),
        reply_markup=language_picker_keyboard(),
    )


@router.callback_query(F.data.startswith(LANG_CALLBACK_PREFIX))
async def cb_set_language(
    callback: CallbackQuery, state: FSMContext, user_repo: UserRepository
) -> None:
    raw = (callback.data or "").removeprefix(LANG_CALLBACK_PREFIX)
    lang = normalize_lang(raw)
    user_id = callback.from_user.id if callback.from_user else callback.message.chat.id

    try:
        await user_repo.set_language(user_id, lang)
    except Exception as exc:
        logger.error("Failed to save language for %s: %s", user_id, exc)

    await state.clear()
    try:
        await callback.message.edit_text(t("language_set", lang), reply_markup=EMPTY_KEYBOARD)
    except Exception:
        pass
    await callback.answer()
    await callback.message.answer(
        t("welcome", lang, salon_name=SALON_NAME),
        reply_markup=main_reply_keyboard(lang),
        parse_mode="HTML",
    )


@router.message(F.text)
async def fallback_text(message: Message, state: FSMContext, lang: str) -> None:
    """
    Catch-all for unrecognised plain text.
    By the time an update reaches this router, every dedicated menu / FSM-step
    handler in earlier routers has already had a chance to match — if we're
    here, the user typed something the bot doesn't understand. Reset state
    defensively and re-show the main menu rather than leaving them stuck.
    """
    await state.clear()
    await message.answer(
        t("fallback_unknown", lang),
        reply_markup=main_reply_keyboard(lang),
        parse_mode="HTML",
    )


@router.callback_query()
async def fallback_callback(callback: CallbackQuery, state: FSMContext, lang: str) -> None:
    """
    Global catch-all for any callback_query that matched NO handler anywhere
    in the router tree — e.g. a stale inline button left over from a
    previous bot version/session, corrupted callback_data, or any future
    routing gap.

    This is critical: when a callback_query's data matches no registered
    filter, aiogram does NOT raise an exception (so the global @dp.error()
    handler never fires) — it just silently logs "is not handled" and moves
    on. Telegram's client then leaves that button's loading spinner with no
    answer at all. Confirmed directly from production logs ("Update id=...
    is not handled"), and exactly the mechanism behind reports of the
    booking flow silently "hanging" on a stale screen. Registered LAST so
    every more specific handler always gets first refusal.

    Also strips the stale message's own inline keyboard (editMessageText
    does NOT clear an old keyboard just because a handler didn't touch it —
    confirmed in production logs as repeated taps on the very same stale
    button), so this message self-disarms permanently after the first tap
    instead of staying tappable forever.
    """
    logger.warning(
        "Unhandled callback_query from user %s: data=%r — answering gracefully.",
        callback.from_user.id if callback.from_user else "?",
        callback.data,
    )
    try:
        await state.clear()
    except Exception:
        pass
    try:
        await callback.answer(t("stale_button", lang), show_alert=True)
    except Exception:
        pass
    try:
        await callback.message.edit_reply_markup(reply_markup=EMPTY_KEYBOARD)
    except Exception:
        pass
    try:
        await callback.message.answer(
            t("use_menu_buttons", lang),
            reply_markup=main_reply_keyboard(lang),
        )
    except Exception as exc:
        logger.error("fallback_callback could not message the user: %s", exc)
