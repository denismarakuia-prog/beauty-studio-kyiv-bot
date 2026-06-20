"""
Admin-only panel: /admin, /stats, /users, /leads, /export, /broadcast.
All handlers silently ignore non-admin callers via IsAdmin filter.
"""
from __future__ import annotations

import csv
import io
import logging
from datetime import datetime

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import BaseFilter, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import BufferedInputFile, CallbackQuery, Message, TelegramObject

from bot.config import Config
from bot.database.repositories import BookingRepository, UserRepository
from bot.keyboards.builders import admin_panel_keyboard
from bot.services.broadcast_service import BroadcastService
from bot.services.scheduling_service import format_date_display

logger = logging.getLogger(__name__)


# ── Admin filter ───────────────────────────────────────────────────────────────

class IsAdmin(BaseFilter):
    async def __call__(self, event: TelegramObject, config: Config) -> bool:
        user = getattr(event, "from_user", None)
        if user is None:
            return False
        return config.is_admin(user.id)


router = Router(name="admin")
router.message.filter(IsAdmin())
router.callback_query.filter(IsAdmin())


class AdminStates(StatesGroup):
    broadcast = State()


_BROADCAST_STATE: str = str(AdminStates.broadcast)


# ── /admin ─────────────────────────────────────────────────────────────────────

@router.message(Command("admin"))
async def cmd_admin(message: Message) -> None:
    await message.answer(
        "⚙️ <b>Панель адміністратора</b>\n\nОберіть дію:",
        reply_markup=admin_panel_keyboard(),
        parse_mode="HTML",
    )


# ── Stats ──────────────────────────────────────────────────────────────────────

async def _render_stats(
    target: Message,
    user_repo: UserRepository,
    booking_repo: BookingRepository,
) -> None:
    total_users   = await user_repo.count_users()
    total_bookings = await booking_repo.count_bookings()
    active_bookings = await booking_repo.count_active_bookings()
    today_bookings = await booking_repo.count_bookings_today()
    week_bookings  = await booking_repo.count_bookings_this_week()
    await target.answer(
        "📊 <b>Статистика</b>\n\n"
        f"👥 Користувачів: <b>{total_users}</b>\n"
        f"📋 Записів усього: <b>{total_bookings}</b>\n"
        f"✅ Активних записів: <b>{active_bookings}</b>\n"
        f"📅 Записів сьогодні: <b>{today_bookings}</b>\n"
        f"📅 Записів за тиждень: <b>{week_bookings}</b>",
        parse_mode="HTML",
    )


@router.message(Command("stats"))
async def cmd_stats(
    message: Message, user_repo: UserRepository, booking_repo: BookingRepository
) -> None:
    await _render_stats(message, user_repo, booking_repo)


@router.callback_query(F.data == "adm_stats")
async def cb_stats(
    callback: CallbackQuery, user_repo: UserRepository, booking_repo: BookingRepository
) -> None:
    await callback.answer()
    await _render_stats(callback.message, user_repo, booking_repo)


# ── Users ──────────────────────────────────────────────────────────────────────

async def _render_users(target: Message, user_repo: UserRepository) -> None:
    users = await user_repo.get_all_users()
    if not users:
        await target.answer("👥 Користувачів ще немає.")
        return
    lines = [f"👥 <b>Користувачі</b> (всього {len(users)}):\n"]
    for u in users[:20]:
        name    = u.get("first_name") or "—"
        uname   = f"@{u['username']}" if u.get("username") else "—"
        phone   = u.get("phone") or "немає номера"
        blocked = " 🚫" if u.get("is_blocked") else ""
        lines.append(
            f"• {name} ({uname}) — <code>{u['telegram_id']}</code>{blocked}\n"
            f"   📞 {phone}"
        )
    if len(users) > 20:
        lines.append(f"\n<i>…та ще {len(users) - 20} користувачів. Скористайтесь /export.</i>")
    await target.answer("\n".join(lines), parse_mode="HTML")


@router.message(Command("users"))
async def cmd_users(message: Message, user_repo: UserRepository) -> None:
    await _render_users(message, user_repo)


@router.callback_query(F.data == "adm_users")
async def cb_users(callback: CallbackQuery, user_repo: UserRepository) -> None:
    await callback.answer()
    await _render_users(callback.message, user_repo)


# ── Bookings ("Записи") ──────────────────────────────────────────────────────────

async def _render_leads(target: Message, booking_repo: BookingRepository) -> None:
    bookings = await booking_repo.get_recent_bookings(limit=10)
    total = await booking_repo.count_bookings()
    if not bookings:
        await target.answer("📋 Записів ще немає.")
        return
    lines = [f"📋 <b>Останні записи</b> (всього: {total}):\n"]
    for b in bookings:
        status_icon = "✅" if b["status"] == "active" else "❌"
        lines.append(
            "━━━━━━━━━━━━\n"
            f"{status_icon} {b['name']}  |  📞 {b['phone']}\n"
            f"💄 {b['service_name']}\n"
            f"📅 {format_date_display(b['booking_date'])}  ⏰ {b['booking_time']}\n"
            f"🕐 {b['created_at']}"
        )
    await target.answer("\n".join(lines), parse_mode="HTML")


@router.message(Command("leads"))
async def cmd_leads(message: Message, booking_repo: BookingRepository) -> None:
    await _render_leads(message, booking_repo)


@router.callback_query(F.data == "adm_leads")
async def cb_leads(callback: CallbackQuery, booking_repo: BookingRepository) -> None:
    await callback.answer()
    await _render_leads(callback.message, booking_repo)


# ── Export ─────────────────────────────────────────────────────────────────────

async def _do_export(target: Message, booking_repo: BookingRepository) -> None:
    bookings = await booking_repo.get_all_bookings()
    if not bookings:
        await target.answer("📋 Немає даних для експорту.")
        return

    buf = io.StringIO()
    writer = csv.DictWriter(
        buf,
        fieldnames=[
            "id", "name", "phone", "service_name", "booking_date", "booking_time",
            "status", "created_at", "cancelled_at",
        ],
        extrasaction="ignore",
    )
    writer.writeheader()
    writer.writerows(bookings)

    data = buf.getvalue().encode("utf-8-sig")   # BOM for Excel compatibility
    fname = f"bookings_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.csv"

    await target.answer_document(
        BufferedInputFile(data, filename=fname),
        caption=(
            f"📤 <b>Експорт записів</b>\n"
            f"📋 Рядків: <b>{len(bookings)}</b>\n"
            f"🕐 {datetime.utcnow().strftime('%d.%m.%Y %H:%M')} UTC"
        ),
        parse_mode="HTML",
    )


@router.message(Command("export"))
async def cmd_export(message: Message, booking_repo: BookingRepository) -> None:
    await _do_export(message, booking_repo)


@router.callback_query(F.data == "adm_export")
async def cb_export(callback: CallbackQuery, booking_repo: BookingRepository) -> None:
    await callback.answer()
    await _do_export(callback.message, booking_repo)


# ── Broadcast ──────────────────────────────────────────────────────────────────

@router.message(Command("broadcast"))
async def cmd_broadcast(message: Message, state: FSMContext) -> None:
    await state.set_state(AdminStates.broadcast)
    await message.answer(
        "📢 <b>Розсилка повідомлень</b>\n\n"
        "Введіть текст для надсилання всім користувачам.\n"
        "Підтримується HTML-форматування.\n\n"
        "Для скасування введіть /cancel",
        parse_mode="HTML",
    )


@router.callback_query(F.data == "adm_broadcast")
async def cb_broadcast(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await state.set_state(AdminStates.broadcast)
    await callback.message.answer(
        "📢 <b>Розсилка повідомлень</b>\n\n"
        "Введіть текст для надсилання всім користувачам.\n"
        "Підтримується HTML-форматування.\n\n"
        "Для скасування введіть /cancel",
        parse_mode="HTML",
    )


@router.message(AdminStates.broadcast)
async def do_broadcast(
    message: Message,
    bot: Bot,
    state: FSMContext,
    user_repo: UserRepository,
) -> None:
    text = message.text or message.caption or ""
    if not text.strip():
        await message.answer("⚠️ Текст не може бути порожнім. Спробуйте ще раз або введіть /cancel")
        return

    await state.clear()
    status_msg = await message.answer("📤 Розпочинаю розсилку…")

    svc = BroadcastService(bot=bot, user_repo=user_repo)
    delivered, failed = await svc.send(text)

    try:
        await status_msg.edit_text(
            f"✅ <b>Розсилку завершено</b>\n\n"
            f"✅ Доставлено: <b>{delivered}</b>\n"
            f"❌ Не доставлено: <b>{failed}</b>",
            parse_mode="HTML",
        )
    except TelegramBadRequest:
        await message.answer(
            f"✅ Розсилку завершено: доставлено {delivered}, не доставлено {failed}."
        )


@router.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext) -> None:
    current = await state.get_state()
    await state.clear()
    if current == _BROADCAST_STATE:
        await message.answer("❌ Розсилку скасовано.")
    elif current:
        await message.answer("❌ Дію скасовано.")
    else:
        await message.answer("Нічого скасовувати.")
