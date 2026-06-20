"""Broadcast messages to all non-blocked users with rate-limit handling."""
from __future__ import annotations

import asyncio
import logging

from aiogram import Bot
from aiogram.exceptions import TelegramForbiddenError, TelegramBadRequest, TelegramRetryAfter

from bot.database.repositories import UserRepository

logger = logging.getLogger(__name__)

# Telegram allows ~30 msg/s to different users; 0.05 s gap keeps us safe.
_SEND_DELAY = 0.05


class BroadcastService:
    def __init__(self, bot: Bot, user_repo: UserRepository) -> None:
        self._bot = bot
        self._repo = user_repo

    async def send(self, text: str) -> tuple[int, int]:
        """
        Send *text* to every non-blocked user.
        Returns (delivered, failed).
        """
        ids = await self._repo.get_all_telegram_ids()
        delivered = 0
        failed = 0

        for tg_id in ids:
            try:
                await self._bot.send_message(
                    chat_id=tg_id, text=text, parse_mode="HTML"
                )
                delivered += 1
                await asyncio.sleep(_SEND_DELAY)

            except TelegramRetryAfter as exc:
                wait = exc.retry_after + 1
                logger.warning("Rate-limited; sleeping %s s", wait)
                await asyncio.sleep(wait)
                try:
                    await self._bot.send_message(
                        chat_id=tg_id, text=text, parse_mode="HTML"
                    )
                    delivered += 1
                except Exception:
                    failed += 1

            except TelegramForbiddenError:
                logger.info("User %s blocked the bot — marking.", tg_id)
                await self._repo.mark_blocked(tg_id)
                failed += 1

            except TelegramBadRequest as exc:
                logger.warning("Bad request for %s: %s", tg_id, exc)
                failed += 1

            except Exception as exc:
                logger.error("Failed to send to %s: %s", tg_id, exc)
                failed += 1

        return delivered, failed
