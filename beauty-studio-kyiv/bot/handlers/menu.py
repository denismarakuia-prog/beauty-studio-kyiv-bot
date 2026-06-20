"""Price list and 'About the salon' — simple stateless text replies."""
from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from bot.keyboards.builders import BTN_ABOUT, BTN_PRICE, main_reply_keyboard
from bot.salon_data import SALON_ABOUT, SALON_NAME, SERVICES

logger = logging.getLogger(__name__)
router = Router(name="menu")


def price_list_text() -> str:
    lines = [f"<b>💰 Прайс-лист — {SALON_NAME}</b>\n"]
    for s in SERVICES:
        lines.append(
            f"{s.emoji} <b>{s.name}</b>\n"
            f"    ⏱ {s.duration}   |   💰 {s.price}\n"
        )
    lines.append("<i>Натисніть «📅 Записатися», щоб обрати послугу, дату й час.</i>")
    return "\n".join(lines)


def about_text() -> str:
    return f"<b>ℹ️ Про {SALON_NAME}</b>\n\n{SALON_ABOUT}"


@router.message(F.text == BTN_PRICE)
async def show_price_list(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer(
        price_list_text(),
        reply_markup=main_reply_keyboard(),
        parse_mode="HTML",
    )


@router.message(F.text == BTN_ABOUT)
async def show_about(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer(
        about_text(),
        reply_markup=main_reply_keyboard(),
        parse_mode="HTML",
    )
