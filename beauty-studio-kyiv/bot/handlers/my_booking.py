"""'📖 Мій запис' — view and cancel the current active booking."""
from __future__ import annotations

import logging

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot.config import Config
from bot.database.repositories import BookingRepository
from bot.keyboards.builders import (
    BTN_MY_BOOKING,
    EMPTY_KEYBOARD,
    MyBookingCallback,
    book_now_keyboard,
    my_booking_confirm_cancel_keyboard,
    my_booking_keyboard,
)
from bot.services.notification_service import notify_cancelled_booking
from bot.services.scheduling_service import format_date_display

logger = logging.getLogger(__name__)
router = Router(name="my_booking")


def _booking_view_text(booking: dict) -> str:
    return (
        "📖 <b>Ваш запис</b>\n\n"
        f"💄 Послуга: {booking['service_name']}\n"
        f"📅 Дата: {format_date_display(booking['booking_date'])}\n"
        f"⏰ Час: {booking['booking_time']}"
    )


@router.message(F.text == BTN_MY_BOOKING)
async def show_my_booking(
    message: Message, state: FSMContext, booking_repo: BookingRepository
) -> None:
    await state.clear()
    user_id = message.from_user.id if message.from_user else message.chat.id

    try:
        booking = await booking_repo.get_active_booking_for_user(user_id)
    except Exception as exc:
        logger.error("DB error fetching active booking: %s", exc)
        await message.answer("⚠️ Сталася помилка. Спробуйте, будь ласка, пізніше.")
        return

    if not booking:
        await message.answer(
            "📖 У вас немає активних записів.\n\nХочете записатися?",
            reply_markup=book_now_keyboard(),
            parse_mode="HTML",
        )
        return

    await message.answer(
        _booking_view_text(booking),
        reply_markup=my_booking_keyboard(booking["id"]),
        parse_mode="HTML",
    )


@router.callback_query(MyBookingCallback.filter(F.action == "cancel_ask"))
async def cb_cancel_ask(
    callback: CallbackQuery,
    callback_data: MyBookingCallback,
    booking_repo: BookingRepository,
) -> None:
    user_id = callback.from_user.id
    try:
        booking_id = int(callback_data.booking_id)
    except (TypeError, ValueError):
        await callback.answer("Помилка запису", show_alert=True)
        return

    try:
        booking = await booking_repo.get_active_booking_for_user(user_id)
    except Exception as exc:
        logger.error("DB error: %s", exc)
        await callback.answer("Сталася помилка", show_alert=True)
        return

    if not booking or booking["id"] != booking_id:
        await callback.answer("Цей запис вже не активний", show_alert=True)
        try:
            await callback.message.edit_text("📖 У вас немає активних записів.", reply_markup=EMPTY_KEYBOARD)
        except Exception:
            pass
        return

    text = (
        "❓ <b>Скасувати цей запис?</b>\n\n"
        f"💄 {booking['service_name']}\n"
        f"📅 {format_date_display(booking['booking_date'])}\n"
        f"⏰ {booking['booking_time']}"
    )
    await callback.message.edit_text(
        text, reply_markup=my_booking_confirm_cancel_keyboard(booking_id), parse_mode="HTML"
    )
    await callback.answer()


@router.callback_query(MyBookingCallback.filter(F.action == "cancel_no"))
async def cb_cancel_no(
    callback: CallbackQuery,
    callback_data: MyBookingCallback,
    booking_repo: BookingRepository,
) -> None:
    user_id = callback.from_user.id
    try:
        booking = await booking_repo.get_active_booking_for_user(user_id)
    except Exception as exc:
        logger.error("DB error: %s", exc)
        await callback.answer("Сталася помилка", show_alert=True)
        return

    if not booking:
        await callback.message.edit_text("📖 У вас немає активних записів.", reply_markup=EMPTY_KEYBOARD)
        await callback.answer()
        return

    await callback.message.edit_text(
        _booking_view_text(booking),
        reply_markup=my_booking_keyboard(booking["id"]),
        parse_mode="HTML",
    )
    await callback.answer("Запис залишено")


@router.callback_query(MyBookingCallback.filter(F.action == "cancel_yes"))
async def cb_cancel_yes(
    callback: CallbackQuery,
    callback_data: MyBookingCallback,
    bot: Bot,
    config: Config,
    booking_repo: BookingRepository,
) -> None:
    user_id = callback.from_user.id
    try:
        booking_id = int(callback_data.booking_id)
    except (TypeError, ValueError):
        await callback.answer("Помилка запису", show_alert=True)
        return

    try:
        cancelled = await booking_repo.cancel_booking(booking_id, user_id)
    except Exception as exc:
        logger.error("DB error cancelling booking: %s", exc)
        await callback.answer("Сталася помилка. Спробуйте ще раз.", show_alert=True)
        return

    if not cancelled:
        await callback.answer("Цей запис вже скасовано", show_alert=True)
        try:
            await callback.message.edit_text("📖 У вас немає активних записів.", reply_markup=EMPTY_KEYBOARD)
        except Exception:
            pass
        return

    try:
        await notify_cancelled_booking(
            bot,
            config.admin_ids,
            name=cancelled["name"],
            username=callback.from_user.username,
            user_id=user_id,
            phone=cancelled["phone"],
            service=cancelled["service_name"],
            date=format_date_display(cancelled["booking_date"]),
            time=cancelled["booking_time"],
        )
    except Exception as exc:
        logger.error("Failed to notify admin about cancellation: %s", exc)

    await callback.message.edit_text(
        "✅ <b>Запис скасовано</b>\n\n"
        "Будемо раді бачити вас знову! Натисніть «📅 Записатися», "
        "щоб обрати новий час.",
        reply_markup=EMPTY_KEYBOARD,
        parse_mode="HTML",
    )
    await callback.answer("Скасовано")
