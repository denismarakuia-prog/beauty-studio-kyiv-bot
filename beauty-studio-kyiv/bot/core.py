"""
Factory that builds the Bot + Dispatcher with all routers and middlewares.
Dependencies (repos, AI service) are injected at polling time via start_polling kwargs.
"""
from __future__ import annotations

import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

from bot.config import Config
from bot.database.repositories import UserRepository
from bot.handlers import admin, ai_assistant, booking, contacts, menu, my_booking, start
from bot.middlewares.throttling import ThrottlingMiddleware
from bot.middlewares.user_tracker import UserTrackerMiddleware

logger = logging.getLogger(__name__)


def create_bot_and_dispatcher(
    config: Config,
    user_repo: UserRepository,
) -> tuple[Bot, Dispatcher]:
    bot = Bot(
        token=config.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )

    dp = Dispatcher(storage=MemoryStorage())

    # ── Middlewares ──────────────────────────────────────────────────────────
    # IMPORTANT: registered as OUTER middleware, not inner.
    #
    # All handlers in this project live in sub-routers attached via
    # dp.include_router(...) — none are registered directly on dp.message /
    # dp.callback_query. Inner middleware (`.middleware()`) only wraps handler
    # calls on the SAME observer it's registered on, so it would never fire
    # for handlers living in nested routers — a silent no-op.
    #
    # Outer middleware (`.outer_middleware()`) wraps propagate_event() at the
    # Dispatcher level, which recursively covers every nested router. This is
    # also semantically correct for throttling/user-tracking: both should run
    # unconditionally for every incoming update, before any filter decides
    # whether a handler matches.
    throttle = ThrottlingMiddleware(rate=0.3)
    tracker  = UserTrackerMiddleware(user_repo=user_repo)

    for observer in (dp.message, dp.callback_query):
        observer.outer_middleware(throttle)
        observer.outer_middleware(tracker)

    # ── Routers (order matters: most specific first) ────────────────────────
    dp.include_router(admin.router)         # admin commands — filtered by IsAdmin
    dp.include_router(booking.router)       # booking flow (reply-button entry + inline steps)
    dp.include_router(my_booking.router)    # "Мій запис" view/cancel
    dp.include_router(menu.router)          # price / about (reply-button entries)
    dp.include_router(contacts.router)      # contacts (reply-button entry)
    dp.include_router(ai_assistant.router)  # AI Q&A (reply-button entry)
    dp.include_router(start.router)         # /start + catch-all (must always be last)

    logger.info("Bot and Dispatcher created.")
    return bot, dp
