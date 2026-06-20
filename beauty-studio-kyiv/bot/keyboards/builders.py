"""
All keyboards and CallbackData schemas live here.
Handlers import what they need — no keyboard logic escapes this module.
"""
from __future__ import annotations

from typing import List

from aiogram.filters.callback_data import CallbackData
from aiogram.types import (
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder

from bot.salon_data import SERVICES
from bot.services.scheduling_service import DateOption


# ── Reply-keyboard button labels (also used as exact-match filters) ───────────

BTN_BOOK        = "📅 Записатися"
BTN_PRICE       = "💰 Прайс"
BTN_CONTACTS    = "📍 Контакти"
BTN_AI          = "🤖 AI Консультант"
BTN_ABOUT       = "ℹ️ Про салон"
BTN_MY_BOOKING  = "📖 Мій запис"
BTN_SHARE_PHONE = "📱 Поділитися номером"

# Used by every FSM-state free-text handler to detect "the user tapped a main
# menu button instead of answering" and yield so the real menu handler (in a
# later/earlier router) can take over — this is what guarantees the user can
# never get stuck inside a flow.
MENU_BUTTON_LABELS = frozenset(
    {BTN_BOOK, BTN_PRICE, BTN_CONTACTS, BTN_AI, BTN_ABOUT, BTN_MY_BOOKING}
)


# ── CallbackData schemas ───────────────────────────────────────────────────────


class BookingCallback(CallbackData, prefix="bk"):
    action: str       # "start" | "service" | "date" | "time" | "confirm" | "back" | "cancel_flow"
    value: str = ""    # service_id / date_iso / time_str / back-target, per action


class MyBookingCallback(CallbackData, prefix="mb"):
    action: str        # "cancel_ask" | "cancel_yes" | "cancel_no"
    booking_id: str = ""


# ── Persistent reply keyboard (always visible) ─────────────────────────────────


def main_reply_keyboard() -> ReplyKeyboardMarkup:
    b = ReplyKeyboardBuilder()
    b.button(text=BTN_BOOK)
    b.button(text=BTN_PRICE)
    b.button(text=BTN_CONTACTS)
    b.button(text=BTN_AI)
    b.button(text=BTN_ABOUT)
    b.button(text=BTN_MY_BOOKING)
    b.adjust(2, 2, 2)
    return b.as_markup(resize_keyboard=True, is_persistent=True)


def contact_request_keyboard() -> ReplyKeyboardMarkup:
    """Shown while waiting for the client's phone number. Main menu stays reachable
    underneath so the user is never trapped in this step."""
    rows = [
        [KeyboardButton(text=BTN_SHARE_PHONE, request_contact=True)],
        [KeyboardButton(text=BTN_BOOK), KeyboardButton(text=BTN_PRICE)],
        [KeyboardButton(text=BTN_CONTACTS), KeyboardButton(text=BTN_AI)],
        [KeyboardButton(text=BTN_ABOUT), KeyboardButton(text=BTN_MY_BOOKING)],
    ]
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True, is_persistent=True)


# ── Booking flow — inline keyboards ─────────────────────────────────────────────


def booking_service_keyboard() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for svc in SERVICES:
        b.button(
            text=f"{svc.emoji} {svc.name}",
            callback_data=BookingCallback(action="service", value=svc.id),
        )
    b.button(text="❌ Скасувати", callback_data=BookingCallback(action="cancel_flow"))
    b.adjust(1)
    return b.as_markup()


def booking_date_keyboard(dates: List[DateOption]) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for opt in dates:
        b.button(
            text=opt.label,
            callback_data=BookingCallback(action="date", value=opt.iso),
        )
    b.button(text="⬅️ Назад", callback_data=BookingCallback(action="back", value="service"))
    b.button(text="❌ Скасувати", callback_data=BookingCallback(action="cancel_flow"))
    b.adjust(1)
    return b.as_markup()


def booking_time_keyboard(times: List[str]) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for t in times:
        b.button(text=f"🕐 {t}", callback_data=BookingCallback(action="time", value=t))
    b.button(text="⬅️ Назад", callback_data=BookingCallback(action="back", value="date"))
    b.button(text="❌ Скасувати", callback_data=BookingCallback(action="cancel_flow"))

    # Time buttons laid out 3 per row; back/cancel each get their own row.
    # Row sizes are computed to sum EXACTLY to the total button count.
    n = len(times)
    rows = [3] * (n // 3)
    if n % 3:
        rows.append(n % 3)
    rows += [1, 1]
    b.adjust(*rows)
    return b.as_markup()


def booking_confirm_keyboard() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="✅ Підтвердити запис", callback_data=BookingCallback(action="confirm"))
    b.button(text="⬅️ Назад", callback_data=BookingCallback(action="back", value="time"))
    b.button(text="❌ Скасувати", callback_data=BookingCallback(action="cancel_flow"))
    b.adjust(1)
    return b.as_markup()


def duplicate_booking_keyboard(booking_id: int) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(
        text="❌ Скасувати поточний запис",
        callback_data=MyBookingCallback(action="cancel_ask", booking_id=str(booking_id)),
    )
    b.adjust(1)
    return b.as_markup()


# ── My booking ─────────────────────────────────────────────────────────────────


def my_booking_keyboard(booking_id: int) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(
        text="❌ Скасувати запис",
        callback_data=MyBookingCallback(action="cancel_ask", booking_id=str(booking_id)),
    )
    b.adjust(1)
    return b.as_markup()


def my_booking_confirm_cancel_keyboard(booking_id: int) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(
        text="✅ Так, скасувати",
        callback_data=MyBookingCallback(action="cancel_yes", booking_id=str(booking_id)),
    )
    b.button(
        text="↩️ Ні, залишити",
        callback_data=MyBookingCallback(action="cancel_no", booking_id=str(booking_id)),
    )
    b.adjust(1)
    return b.as_markup()


def book_now_keyboard() -> InlineKeyboardMarkup:
    """Used when the user has no active booking yet (e.g. in 'Мій запис')."""
    b = InlineKeyboardBuilder()
    b.button(text="📅 Записатися", callback_data=BookingCallback(action="start"))
    b.adjust(1)
    return b.as_markup()


# ── Admin ──────────────────────────────────────────────────────────────────────


def admin_panel_keyboard() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="📊 Статистика",    callback_data="adm_stats")
    b.button(text="👥 Користувачі",   callback_data="adm_users")
    b.button(text="📋 Записи",        callback_data="adm_leads")
    b.button(text="📤 Експорт CSV",   callback_data="adm_export")
    b.button(text="📢 Розсилка",      callback_data="adm_broadcast")
    b.adjust(2, 2, 1)
    return b.as_markup()
