"""
Fully click-driven booking flow:

    📅 Записатися
      ↓ (contact collected once, then skipped forever)
    Послуга  →  Дата (compact calendar, multi-month)  →  Вільний час  →  Підтвердження

Every step is an inline keyboard — no manual typing of dates/times anywhere.

Time values are NEVER placed raw into callback_data: aiogram's CallbackData
rejects any field containing ':' (e.g. '09:00'), which previously crashed
production with "ValueError: Separator symbol ':' can not be used in value
'09:00'". All time values go through encode_time()/decode_time() at the
keyboard/callback boundary; everywhere else (state, DB, notifications) keeps
using the normal 'HH:MM' string.

Slot protection is enforced at the database layer (partial unique index);
this module also re-checks freshness defensively before writing, so a
double-tap or a stale screen can never create two bookings for the same slot.

Every step carries the same three-button safety net: ⬅️ Назад · 🏠 Головне
меню · ❌ Скасувати — so the user can never reach a dead end.
"""
from __future__ import annotations

import json
import logging
import time

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from bot.config import Config
from bot.database.repositories import BookingRepository, SlotTakenError, UserRepository
from bot.keyboards.builders import (
    BTN_BOOK,
    MENU_BUTTON_LABELS,
    BookingCallback,
    booking_calendar_keyboard,
    booking_confirm_keyboard,
    booking_service_keyboard,
    booking_time_keyboard,
    contact_request_keyboard,
    duplicate_booking_keyboard,
    main_reply_keyboard,
)
from bot.salon_data import SERVICES_MAP
from bot.services.notification_service import notify_new_booking
from bot.services.scheduling_service import (
    decode_month,
    decode_time,
    default_calendar_month,
    encode_month,
    format_date_display,
    get_available_times,
    get_calendar_month,
    is_slot_still_valid,
)

logger = logging.getLogger(__name__)
router = Router(name="booking")

# How long a booking session may stay open before we consider it stale and
# ask the user to restart (protects against picking a date/time that has long
# since passed because the screen sat untouched for hours).
MAX_SESSION_SECONDS = 30 * 60


class BookingStates(StatesGroup):
    waiting_contact = State()
    picking_service = State()
    picking_date    = State()
    picking_time    = State()
    confirming      = State()


# ── Small helpers ──────────────────────────────────────────────────────────────

def _service_label(service_id: str) -> str:
    s = SERVICES_MAP.get(service_id)
    return f"{s.emoji} {s.name}" if s else "—"


def _service_name(service_id: str) -> str:
    s = SERVICES_MAP.get(service_id)
    return s.name if s else "—"


def _full_name(user_row: dict) -> str:
    first = (user_row.get("first_name") or "").strip()
    last = (user_row.get("last_name") or "").strip()
    full = f"{first} {last}".strip()
    return full or "Клієнт"


def _session_fresh(data: dict) -> bool:
    started = data.get("started_at")
    if not started:
        return False
    return (time.time() - float(started)) < MAX_SESSION_SECONDS


def _build_confirmation_text(user_row: dict, service_id: str, date_iso: str, time_str: str) -> str:
    return (
        "📋 <b>Підтвердження запису</b>\n\n"
        f"👤 Ім'я: <b>{_full_name(user_row)}</b>\n"
        f"📞 Телефон: <b>{user_row.get('phone', '—')}</b>\n"
        f"💄 Послуга: <b>{_service_label(service_id)}</b>\n"
        f"📅 Дата: <b>{format_date_display(date_iso)}</b>\n"
        f"⏰ Час: <b>{time_str}</b>\n\n"
        "Все вірно?"
    )


async def _expire_session(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer(
        "⏳ <b>Час сесії вичерпано</b>\n\n"
        "Будь ласка, розпочніть запис знову — натисніть «📅 Записатися» нижче.",
        reply_markup=main_reply_keyboard(),
        parse_mode="HTML",
    )


async def _begin_booking_flow(
    message: Message,
    state: FSMContext,
    user_repo: UserRepository,
    booking_repo: BookingRepository,
    *,
    preselected_service_id: str = "",
) -> None:
    """Shared entry logic — used by the reply-keyboard button, the inline
    'book now' button, and the Mini App's web_app_data handoff."""
    await state.clear()
    user_id = message.from_user.id if message.from_user else message.chat.id

    # 1 — duplicate-booking guard
    try:
        existing = await booking_repo.get_active_booking_for_user(user_id)
    except Exception as exc:
        logger.error("DB error checking existing booking: %s", exc)
        existing = None

    if existing:
        await message.answer(
            "⚠️ <b>У вас вже є активний запис</b>\n\n"
            f"💄 Послуга: {existing['service_name']}\n"
            f"📅 Дата: {format_date_display(existing['booking_date'])}\n"
            f"⏰ Час: {existing['booking_time']}\n\n"
            "Щоб створити новий запис, спочатку скасуйте поточний "
            "(або перегляньте його в розділі «📖 Мій запис»).",
            reply_markup=duplicate_booking_keyboard(existing["id"]),
            parse_mode="HTML",
        )
        return

    # 2 — contact guard
    try:
        has_phone = await user_repo.has_phone(user_id)
    except Exception as exc:
        logger.error("DB error checking phone: %s", exc)
        has_phone = False

    if not has_phone:
        await state.set_state(BookingStates.waiting_contact)
        await state.update_data(
            preselected_service_id=preselected_service_id,
            started_at=time.time(),
        )
        await message.answer(
            "📱 <b>Потрібен ваш номер телефону</b>\n\n"
            "Щоб завершити запис, поділіться, будь ласка, своїм номером — "
            "натисніть кнопку нижче. Більше просити не будемо 🙂",
            reply_markup=contact_request_keyboard(),
            parse_mode="HTML",
        )
        return

    # 3 — service picker (or skip straight to the calendar if pre-selected)
    if preselected_service_id and preselected_service_id in SERVICES_MAP:
        await state.update_data(service_id=preselected_service_id, started_at=time.time())
        cal = default_calendar_month()
        await state.update_data(cal_year=cal.year, cal_month=cal.month)
        await state.set_state(BookingStates.picking_date)
        await message.answer(
            f"✅ Послуга: <b>{_service_label(preselected_service_id)}</b>\n\n"
            f"📅 <b>{cal.title}</b>\n\nОберіть дату:",
            reply_markup=booking_calendar_keyboard(cal),
            parse_mode="HTML",
        )
    else:
        await state.update_data(started_at=time.time())
        await state.set_state(BookingStates.picking_service)
        await message.answer(
            "💄 <b>Оберіть послугу:</b>",
            reply_markup=booking_service_keyboard(),
            parse_mode="HTML",
        )


# ── Entry points ───────────────────────────────────────────────────────────────

@router.message(F.text == BTN_BOOK)
async def entry_from_menu(
    message: Message, state: FSMContext, user_repo: UserRepository, booking_repo: BookingRepository
) -> None:
    await _begin_booking_flow(message, state, user_repo, booking_repo)


@router.callback_query(BookingCallback.filter(F.action == "start"))
async def entry_from_inline(
    callback: CallbackQuery, state: FSMContext, user_repo: UserRepository, booking_repo: BookingRepository
) -> None:
    await callback.answer()
    await _begin_booking_flow(callback.message, state, user_repo, booking_repo)


@router.message(F.web_app_data)
async def entry_from_webapp(
    message: Message, state: FSMContext, user_repo: UserRepository, booking_repo: BookingRepository
) -> None:
    raw = message.web_app_data.data if message.web_app_data else ""
    service_id = ""
    try:
        payload = json.loads(raw)
        if payload.get("action") == "book":
            service_id = payload.get("service", "")
    except Exception:
        pass
    await _begin_booking_flow(
        message, state, user_repo, booking_repo, preselected_service_id=service_id
    )


# ── No-op (calendar header / padding cells) ─────────────────────────────────────

@router.callback_query(BookingCallback.filter(F.action == "noop"))
async def cb_noop(callback: CallbackQuery) -> None:
    await callback.answer()


# ── Global "🏠 Головне меню" — works from any booking step ─────────────────────

@router.callback_query(BookingCallback.filter(F.action == "main_menu"))
async def cb_main_menu(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    try:
        await callback.message.edit_text("🏠 Головне меню")
    except Exception:
        pass
    await callback.message.answer(
        "Оберіть дію на клавіатурі нижче 👇",
        reply_markup=main_reply_keyboard(),
    )
    await callback.answer()


# ── Step: contact collection ───────────────────────────────────────────────────

@router.message(BookingStates.waiting_contact, F.contact)
async def step_contact(
    message: Message, state: FSMContext, user_repo: UserRepository
) -> None:
    contact = message.contact
    if contact is None:
        return

    if contact.user_id and message.from_user and contact.user_id != message.from_user.id:
        await message.answer(
            "⚠️ Будь ласка, поділіться <b>своїм власним</b> номером телефону, "
            "натиснувши кнопку нижче.",
            reply_markup=contact_request_keyboard(),
            parse_mode="HTML",
        )
        return

    try:
        await user_repo.save_contact(
            telegram_id=message.from_user.id if message.from_user else message.chat.id,
            phone=contact.phone_number,
            first_name=contact.first_name or (message.from_user.first_name if message.from_user else None),
            last_name=contact.last_name,
        )
    except Exception as exc:
        logger.error("Failed to save contact: %s", exc)
        await message.answer(
            "⚠️ Сталася помилка під час збереження номеру. Спробуйте ще раз.",
            reply_markup=contact_request_keyboard(),
        )
        return

    data = await state.get_data()
    preselected = data.get("preselected_service_id", "")

    await message.answer("✅ Дякуємо! Номер збережено.", reply_markup=main_reply_keyboard())

    if preselected and preselected in SERVICES_MAP:
        await state.update_data(service_id=preselected)
        cal = default_calendar_month()
        await state.update_data(cal_year=cal.year, cal_month=cal.month)
        await state.set_state(BookingStates.picking_date)
        await message.answer(
            f"💄 Послуга: <b>{_service_label(preselected)}</b>\n\n"
            f"📅 <b>{cal.title}</b>\n\nОберіть дату:",
            reply_markup=booking_calendar_keyboard(cal),
            parse_mode="HTML",
        )
    else:
        await state.set_state(BookingStates.picking_service)
        await message.answer(
            "💄 Оберіть послугу:",
            reply_markup=booking_service_keyboard(),
            parse_mode="HTML",
        )


@router.message(BookingStates.waiting_contact, F.text, ~F.text.in_(MENU_BUTTON_LABELS))
async def step_contact_nudge(message: Message) -> None:
    await message.answer(
        "📱 Будь ласка, натисніть кнопку «📱 Поділитися номером» нижче, "
        "щоб продовжити запис.",
        reply_markup=contact_request_keyboard(),
    )


# ── Step: service ──────────────────────────────────────────────────────────────

@router.callback_query(BookingCallback.filter(F.action == "service"), BookingStates.picking_service)
async def cb_pick_service(
    callback: CallbackQuery, callback_data: BookingCallback, state: FSMContext
) -> None:
    data = await state.get_data()
    if not _session_fresh(data):
        await _expire_session(callback.message, state)
        await callback.answer()
        return

    service_id = callback_data.value
    if service_id not in SERVICES_MAP:
        await callback.answer("Невідома послуга", show_alert=True)
        return

    await state.update_data(service_id=service_id)
    cal = default_calendar_month()
    await state.update_data(cal_year=cal.year, cal_month=cal.month)
    await state.set_state(BookingStates.picking_date)
    await callback.message.edit_text(
        f"✅ Послуга: <b>{_service_label(service_id)}</b>\n\n"
        f"📅 <b>{cal.title}</b>\n\nОберіть дату:",
        reply_markup=booking_calendar_keyboard(cal),
        parse_mode="HTML",
    )
    await callback.answer()


# ── Step: date (calendar navigation + day selection) ───────────────────────────

@router.callback_query(BookingCallback.filter(F.action == "cal_nav"), BookingStates.picking_date)
async def cb_calendar_navigate(
    callback: CallbackQuery, callback_data: BookingCallback, state: FSMContext
) -> None:
    data = await state.get_data()
    if not _session_fresh(data):
        await _expire_session(callback.message, state)
        await callback.answer()
        return

    decoded = decode_month(callback_data.value)
    if decoded is None:
        await callback.answer()
        return

    year, month = decoded
    cal = get_calendar_month(year, month)
    await state.update_data(cal_year=cal.year, cal_month=cal.month)
    await callback.message.edit_text(
        f"📅 <b>{cal.title}</b>\n\nОберіть дату:",
        reply_markup=booking_calendar_keyboard(cal),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(BookingCallback.filter(F.action == "date"), BookingStates.picking_date)
async def cb_pick_date(
    callback: CallbackQuery,
    callback_data: BookingCallback,
    state: FSMContext,
    booking_repo: BookingRepository,
) -> None:
    data = await state.get_data()
    if not _session_fresh(data):
        await _expire_session(callback.message, state)
        await callback.answer()
        return

    date_iso = callback_data.value

    try:
        taken = await booking_repo.get_taken_times(date_iso)
    except Exception as exc:
        logger.error("DB error fetching taken slots: %s", exc)
        await callback.answer("Сталася помилка. Спробуйте ще раз.", show_alert=True)
        return

    free = get_available_times(date_iso, taken)

    if not free:
        await callback.answer("На цю дату вже немає вільних місць", show_alert=True)
        cal_year = data.get("cal_year") or 0
        cal_month = data.get("cal_month") or 0
        cal = get_calendar_month(cal_year, cal_month) if cal_year and cal_month else default_calendar_month()
        await callback.message.edit_text(
            f"😔 На <b>{format_date_display(date_iso)}</b> вже немає вільних місць.\n\n"
            f"📅 <b>{cal.title}</b>\n\nОберіть іншу дату:",
            reply_markup=booking_calendar_keyboard(cal),
            parse_mode="HTML",
        )
        return

    await state.update_data(booking_date=date_iso)
    await state.set_state(BookingStates.picking_time)
    await callback.message.edit_text(
        f"📅 Дата: <b>{format_date_display(date_iso)}</b>\n\n⏰ Оберіть вільний час:",
        reply_markup=booking_time_keyboard(free),
        parse_mode="HTML",
    )
    await callback.answer()


# ── Step: time ─────────────────────────────────────────────────────────────────

@router.callback_query(BookingCallback.filter(F.action == "time"), BookingStates.picking_time)
async def cb_pick_time(
    callback: CallbackQuery,
    callback_data: BookingCallback,
    state: FSMContext,
    booking_repo: BookingRepository,
    user_repo: UserRepository,
) -> None:
    data = await state.get_data()
    if not _session_fresh(data):
        await _expire_session(callback.message, state)
        await callback.answer()
        return

    date_iso = data.get("booking_date", "")
    service_id = data.get("service_id", "")

    time_str = decode_time(callback_data.value)
    if not time_str:
        await callback.answer("Помилка вибору часу. Спробуйте ще раз.", show_alert=True)
        return

    if not date_iso or service_id not in SERVICES_MAP:
        await _expire_session(callback.message, state)
        await callback.answer()
        return

    try:
        taken = await booking_repo.get_taken_times(date_iso)
    except Exception as exc:
        logger.error("DB error re-checking slots: %s", exc)
        await callback.answer("Сталася помилка. Спробуйте ще раз.", show_alert=True)
        return

    if time_str in taken or not is_slot_still_valid(date_iso, time_str):
        free = get_available_times(date_iso, taken)
        await callback.answer("На жаль, цей час вже зайнято", show_alert=True)
        if free:
            await callback.message.edit_text(
                f"😔 Цей час щойно зайняли. Оберіть інший:\n\n"
                f"📅 Дата: <b>{format_date_display(date_iso)}</b>",
                reply_markup=booking_time_keyboard(free),
                parse_mode="HTML",
            )
        else:
            await state.set_state(BookingStates.picking_date)
            cal = default_calendar_month()
            await state.update_data(cal_year=cal.year, cal_month=cal.month)
            await callback.message.edit_text(
                "😔 Цей час щойно зайняли, а вільних місць на цю дату більше немає.\n\n"
                f"📅 <b>{cal.title}</b>\n\nОберіть іншу дату:",
                reply_markup=booking_calendar_keyboard(cal),
                parse_mode="HTML",
            )
        return

    try:
        user_row = await user_repo.get_user(callback.from_user.id)
    except Exception as exc:
        logger.error("DB error fetching user for confirmation: %s", exc)
        user_row = None

    if not user_row or not user_row.get("phone"):
        await state.clear()
        await callback.message.edit_text(
            "⚠️ Сталася помилка з вашими контактними даними. "
            "Будь ласка, розпочніть запис знову — «📅 Записатися»."
        )
        await callback.answer()
        return

    await state.update_data(booking_time=time_str)
    await state.set_state(BookingStates.confirming)

    await callback.message.edit_text(
        _build_confirmation_text(user_row, service_id, date_iso, time_str),
        reply_markup=booking_confirm_keyboard(),
        parse_mode="HTML",
    )
    await callback.answer()


# ── Step: confirmation ──────────────────────────────────────────────────────────

@router.callback_query(BookingCallback.filter(F.action == "confirm"), BookingStates.confirming)
async def cb_confirm(
    callback: CallbackQuery,
    state: FSMContext,
    bot: Bot,
    config: Config,
    user_repo: UserRepository,
    booking_repo: BookingRepository,
) -> None:
    data = await state.get_data()
    if not _session_fresh(data):
        await _expire_session(callback.message, state)
        await callback.answer()
        return

    date_iso = data.get("booking_date", "")
    time_str = data.get("booking_time", "")
    service_id = data.get("service_id", "")

    if not date_iso or not time_str or service_id not in SERVICES_MAP:
        await _expire_session(callback.message, state)
        await callback.answer()
        return

    if not is_slot_still_valid(date_iso, time_str):
        await callback.answer("Час вже минув", show_alert=True)
        try:
            taken = await booking_repo.get_taken_times(date_iso)
        except Exception:
            taken = []
        free = get_available_times(date_iso, taken)
        if free:
            await state.set_state(BookingStates.picking_time)
            await callback.message.edit_text(
                f"⏳ Обраний час уже минув. Оберіть інший:\n\n"
                f"📅 Дата: <b>{format_date_display(date_iso)}</b>",
                reply_markup=booking_time_keyboard(free),
                parse_mode="HTML",
            )
        else:
            await state.set_state(BookingStates.picking_date)
            cal = default_calendar_month()
            await state.update_data(cal_year=cal.year, cal_month=cal.month)
            await callback.message.edit_text(
                "⏳ Обраний час уже минув, а вільних місць на цю дату більше немає.\n\n"
                f"📅 <b>{cal.title}</b>\n\nОберіть іншу дату:",
                reply_markup=booking_calendar_keyboard(cal),
                parse_mode="HTML",
            )
        return

    try:
        user_row = await user_repo.get_user(callback.from_user.id)
    except Exception as exc:
        logger.error("DB error fetching user: %s", exc)
        user_row = None

    if not user_row or not user_row.get("phone"):
        await state.clear()
        await callback.message.edit_text(
            "⚠️ Сталася помилка з вашими контактними даними. "
            "Будь ласка, розпочніть запис знову — «📅 Записатися»."
        )
        await callback.answer()
        return

    name = _full_name(user_row)
    phone = user_row["phone"]

    try:
        await booking_repo.create_booking(
            telegram_id=callback.from_user.id,
            name=name,
            phone=phone,
            service_id=service_id,
            service_name=_service_name(service_id),
            booking_date=date_iso,
            booking_time=time_str,
        )
    except SlotTakenError:
        try:
            taken = await booking_repo.get_taken_times(date_iso)
        except Exception:
            taken = []
        free = get_available_times(date_iso, taken)
        await callback.answer("На жаль, цей час щойно зайняли", show_alert=True)
        if free:
            await state.set_state(BookingStates.picking_time)
            await callback.message.edit_text(
                f"😔 Цей час щойно зайняли. Оберіть інший:\n\n"
                f"📅 Дата: <b>{format_date_display(date_iso)}</b>",
                reply_markup=booking_time_keyboard(free),
                parse_mode="HTML",
            )
        else:
            await state.set_state(BookingStates.picking_date)
            cal = default_calendar_month()
            await state.update_data(cal_year=cal.year, cal_month=cal.month)
            await callback.message.edit_text(
                "😔 Цей час щойно зайняли, а вільних місць на цю дату більше немає.\n\n"
                f"📅 <b>{cal.title}</b>\n\nОберіть іншу дату:",
                reply_markup=booking_calendar_keyboard(cal),
                parse_mode="HTML",
            )
        return
    except Exception as exc:
        logger.error("Failed to create booking: %s", exc)
        await callback.answer("Сталася помилка. Спробуйте ще раз.", show_alert=True)
        return

    await state.clear()

    try:
        await notify_new_booking(
            bot,
            config.admin_ids,
            name=name,
            username=callback.from_user.username,
            user_id=callback.from_user.id,
            phone=phone,
            service=_service_name(service_id),
            date=format_date_display(date_iso),
            time=time_str,
        )
    except Exception as exc:
        logger.error("Failed to notify admin about new booking: %s", exc)

    await callback.message.edit_text(
        "✅ <b>Дякуємо ❤️</b>\n\nВаш запис підтверджено!\n\n"
        f"💄 {_service_name(service_id)}\n"
        f"📅 {format_date_display(date_iso)}\n"
        f"⏰ {time_str}\n\n"
        "Чекаємо на вас! За потреби запис можна переглянути або скасувати "
        "в розділі «📖 Мій запис».",
        parse_mode="HTML",
    )
    await callback.answer("Запис підтверджено! ✅")


# ── Back navigation ────────────────────────────────────────────────────────────

@router.callback_query(BookingCallback.filter(F.action == "back"))
async def cb_back(
    callback: CallbackQuery,
    callback_data: BookingCallback,
    state: FSMContext,
    booking_repo: BookingRepository,
) -> None:
    target = callback_data.value
    data = await state.get_data()

    if not _session_fresh(data) and target != "service":
        await _expire_session(callback.message, state)
        await callback.answer()
        return

    if target == "service":
        await state.update_data(started_at=time.time())
        await state.set_state(BookingStates.picking_service)
        await callback.message.edit_text(
            "💄 Оберіть послугу:", reply_markup=booking_service_keyboard()
        )

    elif target == "date":
        cal_year = data.get("cal_year") or 0
        cal_month = data.get("cal_month") or 0
        cal = get_calendar_month(cal_year, cal_month) if cal_year and cal_month else default_calendar_month()
        await state.update_data(cal_year=cal.year, cal_month=cal.month)
        await state.set_state(BookingStates.picking_date)
        await callback.message.edit_text(
            f"📅 <b>{cal.title}</b>\n\nОберіть дату:",
            reply_markup=booking_calendar_keyboard(cal),
            parse_mode="HTML",
        )

    elif target == "time":
        date_iso = data.get("booking_date", "")
        if not date_iso:
            cal = default_calendar_month()
            await state.update_data(cal_year=cal.year, cal_month=cal.month)
            await state.set_state(BookingStates.picking_date)
            await callback.message.edit_text(
                f"📅 <b>{cal.title}</b>\n\nОберіть дату:",
                reply_markup=booking_calendar_keyboard(cal),
                parse_mode="HTML",
            )
        else:
            try:
                taken = await booking_repo.get_taken_times(date_iso)
            except Exception:
                taken = []
            free = get_available_times(date_iso, taken)
            if not free:
                cal_year = data.get("cal_year") or 0
                cal_month = data.get("cal_month") or 0
                cal = get_calendar_month(cal_year, cal_month) if cal_year and cal_month else default_calendar_month()
                await state.update_data(cal_year=cal.year, cal_month=cal.month)
                await state.set_state(BookingStates.picking_date)
                await callback.message.edit_text(
                    f"😔 На {format_date_display(date_iso)} вже немає вільних місць.\n\n"
                    f"📅 <b>{cal.title}</b>\n\nОберіть іншу дату:",
                    reply_markup=booking_calendar_keyboard(cal),
                    parse_mode="HTML",
                )
            else:
                await state.set_state(BookingStates.picking_time)
                await callback.message.edit_text(
                    f"📅 Дата: {format_date_display(date_iso)}\n\n⏰ Оберіть вільний час:",
                    reply_markup=booking_time_keyboard(free),
                    parse_mode="HTML",
                )

    await callback.answer()


# ── Cancel the whole flow ───────────────────────────────────────────────────────

@router.callback_query(BookingCallback.filter(F.action == "cancel_flow"))
async def cb_cancel_flow(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    try:
        await callback.message.edit_text("❌ Запис скасовано.")
    except Exception:
        pass
    await callback.answer("Скасовано")
