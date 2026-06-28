"""Contacts display + Telegram location pin."""
from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from bot.i18n import t
from bot.keyboards.builders import BTN_CONTACTS, main_reply_keyboard
from bot.salon_data import (
    SALON_ADDRESS,
    SALON_HOURS,
    SALON_LATITUDE,
    SALON_LONGITUDE,
    SALON_NAME,
    SALON_PHONES,
)

logger = logging.getLogger(__name__)
router = Router(name="contacts")


def _contacts_text(lang: str = "uk") -> str:
    phones = "\n".join(f"📞 {p}" for p in SALON_PHONES)
    return t(
        "contacts_block",
        lang,
        salon_name=SALON_NAME,
        address=SALON_ADDRESS,
        phones=phones,
        hours=SALON_HOURS,
    )


@router.message(F.text.in_(set(BTN_CONTACTS.values())))
async def show_contacts(message: Message, state: FSMContext, lang: str) -> None:
    await state.clear()
    await message.answer(
        _contacts_text(lang),
        reply_markup=main_reply_keyboard(lang),
        parse_mode="HTML",
    )
    try:
        await message.answer_location(
            latitude=SALON_LATITUDE,
            longitude=SALON_LONGITUDE,
        )
    except Exception as exc:
        logger.warning("Failed to send location: %s", exc)
