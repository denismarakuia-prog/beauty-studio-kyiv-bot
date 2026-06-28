"""'📖 Мій запис' — view and cancel the current active booking."""
from __future__ import annotations

import logging

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot.config import Config
from bot.database.repositories import BookingRepository
from bot.i18n import t
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


def _booking_view_text(booking: dict, lang: str) -> str:
    return t(
        "my_booking_view",
        lang,
        service=booking["service_name"],
        date=format_date_display(booking["booking_date"]),
        time=booking["booking_time"],
    )


@router.message(F.text.in_(set(BTN_MY_BOOKING.values())))
async def show_my_booking(
    message: Message, state: FSMContext, booking_repo: BookingRepository, lang: str
) -> None:
    await state.clear()
    user_id = message.from_user.id if message.from_user else message.chat.id

    try:
        booking = await booking_repo.get_active_booking_for_user(user_id)
    except Exception as exc:
        logger.error("DB error fetching active booking: %s", exc)
        await message.answer(t("my_booking_db_error", lang))
        return

    if not booking:
        await message.answer(
            t("my_booking_none", lang),
            reply_markup=book_now_keyboard(lang),
            parse_mode="HTML",
        )
        return

    await message.answer(
        _booking_view_text(booking, lang),
        reply_markup=my_booking_keyboard(booking["id"], lang),
        parse_mode="HTML",
    )


@router.callback_query(MyBookingCallback.filter(F.action == "cancel_ask"))
async def cb_cancel_ask(
    callback: CallbackQuery,
    callback_data: MyBookingCallback,
    booking_repo: BookingRepository,
    lang: str,
) -> None:
    user_id = callback.from_user.id
    try:
        booking_id = int(callback_data.booking_id)
    except (TypeError, ValueError):
        await callback.answer(t("my_booking_not_active", lang), show_alert=True)
        return

    try:
        booking = await booking_repo.get_active_booking_for_user(user_id)
    except Exception as exc:
        logger.error("DB error: %s", exc)
        await callback.answer(t("my_booking_db_error_alert", lang), show_alert=True)
        return

    if not booking or booking["id"] != booking_id:
        await callback.answer(t("my_booking_not_active", lang), show_alert=True)
        try:
            await callback.message.edit_text(
                t("my_booking_none_short", lang), reply_markup=EMPTY_KEYBOARD
            )
        except Exception:
            pass
        return

    text = t(
        "my_booking_cancel_ask",
        lang,
        service=booking["service_name"],
        date=format_date_display(booking["booking_date"]),
        time=booking["booking_time"],
    )
    await callback.message.edit_text(
        text, reply_markup=my_booking_confirm_cancel_keyboard(booking_id, lang), parse_mode="HTML"
    )
    await callback.answer()


@router.callback_query(MyBookingCallback.filter(F.action == "cancel_no"))
async def cb_cancel_no(
    callback: CallbackQuery,
    callback_data: MyBookingCallback,
    booking_repo: BookingRepository,
    lang: str,
) -> None:
    user_id = callback.from_user.id
    try:
        booking = await booking_repo.get_active_booking_for_user(user_id)
    except Exception as exc:
        logger.error("DB error: %s", exc)
        await callback.answer(t("my_booking_db_error_alert", lang), show_alert=True)
        return

    if not booking:
        await callback.message.edit_text(t("my_booking_none_short", lang), reply_markup=EMPTY_KEYBOARD)
        await callback.answer()
        return

    await callback.message.edit_text(
        _booking_view_text(booking, lang),
        reply_markup=my_booking_keyboard(booking["id"], lang),
        parse_mode="HTML",
    )
    await callback.answer(t("my_booking_left", lang))


@router.callback_query(MyBookingCallback.filter(F.action == "cancel_yes"))
async def cb_cancel_yes(
    callback: CallbackQuery,
    callback_data: MyBookingCallback,
    bot: Bot,
    config: Config,
    booking_repo: BookingRepository,
    lang: str,
) -> None:
    user_id = callback.from_user.id
    try:
        booking_id = int(callback_data.booking_id)
    except (TypeError, ValueError):
        await callback.answer(t("my_booking_not_active", lang), show_alert=True)
        return

    try:
        cancelled = await booking_repo.cancel_booking(booking_id, user_id)
    except Exception as exc:
        logger.error("DB error cancelling booking: %s", exc)
        await callback.answer(t("my_booking_db_error_retry", lang), show_alert=True)
        return

    if not cancelled:
        await callback.answer(t("my_booking_already_cancelled", lang), show_alert=True)
        try:
            await callback.message.edit_text(
                t("my_booking_none_short", lang), reply_markup=EMPTY_KEYBOARD
            )
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
        t("my_booking_cancelled_success", lang),
        reply_markup=EMPTY_KEYBOARD,
        parse_mode="HTML",
    )
    await callback.answer(t("cancelled_toast", lang))
