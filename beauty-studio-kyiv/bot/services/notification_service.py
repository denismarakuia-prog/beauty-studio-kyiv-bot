"""Send admin notifications for new bookings and cancellations."""
from __future__ import annotations

import logging
from typing import List, Optional

from aiogram import Bot

logger = logging.getLogger(__name__)


def _username_line(username: Optional[str]) -> str:
    return f"@{username}" if username else "немає username"


async def notify_new_booking(
    bot: Bot,
    admin_ids: List[int],
    *,
    name: str,
    username: Optional[str],
    user_id: int,
    phone: str,
    service: str,
    date: str,
    time: str,
) -> None:
    text = (
        "🔔 <b>Новий запис</b>\n\n"
        f"👤 Ім'я: {name}\n"
        f"📱 Username: {_username_line(username)}\n"
        f"🆔 ID: <code>{user_id}</code>\n"
        f"📞 Телефон: {phone}\n"
        f"💄 Послуга: {service}\n"
        f"📅 Дата: {date}\n"
        f"⏰ Час: {time}"
    )
    for admin_id in admin_ids:
        try:
            await bot.send_message(chat_id=admin_id, text=text, parse_mode="HTML")
        except Exception as exc:
            logger.error("Cannot notify admin %s about new booking: %s", admin_id, exc)


async def notify_cancelled_booking(
    bot: Bot,
    admin_ids: List[int],
    *,
    name: str,
    username: Optional[str],
    user_id: int,
    phone: str,
    service: str,
    date: str,
    time: str,
) -> None:
    text = (
        "❌ <b>Запис скасовано</b>\n\n"
        f"👤 Ім'я: {name}\n"
        f"📱 Username: {_username_line(username)}\n"
        f"🆔 ID: <code>{user_id}</code>\n"
        f"📞 Телефон: {phone}\n"
        f"💄 Послуга: {service}\n"
        f"📅 Дата: {date}\n"
        f"⏰ Час: {time}"
    )
    for admin_id in admin_ids:
        try:
            await bot.send_message(chat_id=admin_id, text=text, parse_mode="HTML")
        except Exception as exc:
            logger.error("Cannot notify admin %s about cancellation: %s", admin_id, exc)
