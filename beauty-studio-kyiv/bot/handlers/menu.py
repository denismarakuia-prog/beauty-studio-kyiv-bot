"""Price list and 'About the salon' — simple stateless text replies."""
from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from bot.i18n import t
from bot.keyboards.builders import BTN_ABOUT, BTN_PRICE, main_reply_keyboard
from bot.salon_data import SALON_ABOUT, SALON_ABOUT_RU, SALON_NAME, SERVICES

logger = logging.getLogger(__name__)
router = Router(name="menu")


def price_list_text(lang: str = "uk") -> str:
    lines = [t("price_title", lang, salon_name=SALON_NAME)]
    for s in SERVICES:
        lines.append(
            f"{s.emoji} <b>{s.name_for(lang)}</b>\n"
            f"    ⏱ {s.duration}   |   💰 {s.price}\n"
        )
    lines.append(t("price_footer", lang))
    return "\n".join(lines)


def about_text(lang: str = "uk") -> str:
    about = SALON_ABOUT_RU if lang == "ru" and SALON_ABOUT_RU else SALON_ABOUT
    return t("about_title", lang, salon_name=SALON_NAME, about=about)


@router.message(F.text.in_(set(BTN_PRICE.values())))
async def show_price_list(message: Message, state: FSMContext, lang: str) -> None:
    await state.clear()
    await message.answer(
        price_list_text(lang),
        reply_markup=main_reply_keyboard(lang),
        parse_mode="HTML",
    )


@router.message(F.text.in_(set(BTN_ABOUT.values())))
async def show_about(message: Message, state: FSMContext, lang: str) -> None:
    await state.clear()
    await message.answer(
        about_text(lang),
        reply_markup=main_reply_keyboard(lang),
        parse_mode="HTML",
    )
