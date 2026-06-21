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
    WebAppInfo,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.salon_data import SERVICES
from bot.services.scheduling_service import CalendarMonth, encode_time


# ── Mini App URL (set once at startup by core.py, read by main_reply_keyboard) ─
#
# Avoids threading `config`/`webapp_url` through every single handler
# signature across the whole project just to render one optional button —
# this is set ONCE when the bot starts and read here whenever the main
# keyboard is built.

_webapp_url: str = ""


def set_webapp_url(url: str) -> None:
    global _webapp_url
    _webapp_url = url or ""


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
#
# IMPORTANT: aiogram's CallbackData.pack() raises ValueError if any field
# value contains the ':' separator character. Time values ('09:00') and any
# other colon-bearing value must NEVER be placed directly into a field below
# — always run them through encode_time()/encode_month() first (see
# scheduling_service.py). Dates ('2026-06-20') use '-' and are safe as-is.


class BookingCallback(CallbackData, prefix="bk"):
    # "start" | "service" | "cal_nav" | "date" | "time" | "confirm"
    # | "back" | "cancel_flow" | "main_menu" | "noop"
    action: str
    value: str = ""    # service_id / month-code / date_iso / time-code / back-target


class MyBookingCallback(CallbackData, prefix="mb"):
    action: str        # "cancel_ask" | "cancel_yes" | "cancel_no"
    booking_id: str = ""


# ── Persistent reply keyboard (always visible) ─────────────────────────────────


def main_reply_keyboard() -> ReplyKeyboardMarkup:
    rows = [
        [KeyboardButton(text=BTN_BOOK), KeyboardButton(text=BTN_PRICE)],
        [KeyboardButton(text=BTN_CONTACTS), KeyboardButton(text=BTN_AI)],
        [KeyboardButton(text=BTN_ABOUT), KeyboardButton(text=BTN_MY_BOOKING)],
    ]
    if _webapp_url:
        # IMPORTANT: this MUST be web_app=WebAppInfo(...), not url=... — only
        # the web_app button type opens Telegram's actual Mini App WebView
        # with a working JS bridge (Telegram.WebApp.sendData() etc.). A plain
        # url= button would just open it as an external browser link, where
        # sendData() has nothing to talk to and the booking handoff breaks.
        rows.append([KeyboardButton(text="🌐 Міні-додаток", web_app=WebAppInfo(url=_webapp_url))])
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True, is_persistent=True)


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


# ── Shared row helpers ──────────────────────────────────────────────────────────

_NOOP = BookingCallback(action="noop")
_MAIN_MENU_BTN_TEXT = "🏠 Головне меню"


def _add_nav_row(b: InlineKeyboardBuilder, *, back_target: str) -> None:
    """⬅️ Назад · 🏠 Головне меню · ❌ Скасувати — present on every booking step."""
    b.button(text="⬅️ Назад", callback_data=BookingCallback(action="back", value=back_target))
    b.button(text=_MAIN_MENU_BTN_TEXT, callback_data=BookingCallback(action="main_menu"))
    b.button(text="❌ Скасувати", callback_data=BookingCallback(action="cancel_flow"))


# ── Booking flow — inline keyboards ─────────────────────────────────────────────


def booking_service_keyboard() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for svc in SERVICES:
        b.button(
            text=f"{svc.emoji} {svc.name}",
            callback_data=BookingCallback(action="service", value=svc.id),
        )
    b.button(text=_MAIN_MENU_BTN_TEXT, callback_data=BookingCallback(action="main_menu"))
    b.button(text="❌ Скасувати", callback_data=BookingCallback(action="cancel_flow"))
    rows = [1] * len(SERVICES) + [1, 1]
    b.adjust(*rows)
    return b.as_markup()


def booking_calendar_keyboard(cal: CalendarMonth) -> InlineKeyboardMarkup:
    """Compact month-grid calendar with ◀️/▶️ navigation between bookable months."""
    b = InlineKeyboardBuilder()

    # Navigation row: ◀️ | title | ▶️
    if cal.has_prev:
        b.button(text="◀️", callback_data=BookingCallback(action="cal_nav", value=cal.prev_code))
    else:
        b.button(text=" ", callback_data=_NOOP)
    b.button(text=cal.title, callback_data=_NOOP)
    if cal.has_next:
        b.button(text="▶️", callback_data=BookingCallback(action="cal_nav", value=cal.next_code))
    else:
        b.button(text=" ", callback_data=_NOOP)

    # Weekday header row
    for wd in ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Нд"]:
        b.button(text=wd, callback_data=_NOOP)

    # Day grid — 7 columns per week
    for week in cal.weeks:
        for day in week:
            if day.iso:
                b.button(text=day.label, callback_data=BookingCallback(action="date", value=day.iso))
            else:
                b.button(text=day.label or " ", callback_data=_NOOP)

    _add_nav_row(b, back_target="service")

    rows = [3, 7] + [7] * len(cal.weeks) + [1, 1, 1]
    b.adjust(*rows)
    return b.as_markup()


def booking_time_keyboard(times: List[str]) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for t in times:
        # IMPORTANT: encode_time() strips the ':' — packing the raw "HH:MM"
        # string here is exactly what caused the production crash
        # (ValueError: Separator symbol ':' can not be used in value '09:00').
        b.button(
            text=f"🕐 {t}",
            callback_data=BookingCallback(action="time", value=encode_time(t)),
        )
    _add_nav_row(b, back_target="date")

    # Time buttons laid out 3 per row; nav row buttons each get their own row.
    n = len(times)
    rows = [3] * (n // 3)
    if n % 3:
        rows.append(n % 3)
    rows += [1, 1, 1]
    b.adjust(*rows)
    return b.as_markup()


def booking_confirm_keyboard() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="✅ Підтвердити запис", callback_data=BookingCallback(action="confirm"))
    _add_nav_row(b, back_target="time")
    b.adjust(1, 1, 1, 1)
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
