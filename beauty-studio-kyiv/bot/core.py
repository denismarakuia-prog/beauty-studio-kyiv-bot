"""
Factory that builds the Bot + Dispatcher with all routers and middlewares.
Dependencies (repos, AI service) are injected at polling time via start_polling kwargs.
"""
from __future__ import annotations

import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import ErrorEvent

from bot.config import Config
from bot.database.repositories import UserRepository
from bot.handlers import admin, ai_assistant, booking, contacts, menu, my_booking, start
from bot.i18n import t
from bot.keyboards.builders import EMPTY_KEYBOARD, main_reply_keyboard, set_webapp_url
from bot.middlewares.language_gate import LanguageGateMiddleware
from bot.middlewares.throttling import ThrottlingMiddleware
from bot.middlewares.user_tracker import UserTrackerMiddleware

logger = logging.getLogger(__name__)


def create_bot_and_dispatcher(
    config: Config,
    user_repo: UserRepository,
) -> tuple[Bot, Dispatcher]:
    set_webapp_url(config.webapp_url)

    bot = Bot(
        token=config.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )

    dp = Dispatcher(storage=MemoryStorage())

    # ── Global error handler ──────────────────────────────────────────────────
    #
    # ANY unhandled exception raised by ANY handler in ANY router (a bad
    # callback payload, a DB hiccup, a stale message from a previous bot
    # version, etc.) is caught HERE instead of silently dying. Without this,
    # a callback_query whose handler raises never gets answered — Telegram
    # shows the button stuck in its loading spinner forever, which is
    # exactly the "booking hangs" symptom class. This guarantees: the
    # spinner always clears, the FSM state is always reset to a clean
    # slate, and the user always gets a real message with the main menu
    # back, instead of dead silence.
    @dp.error()
    async def global_error_handler(event: ErrorEvent, state: FSMContext, lang: str = "uk") -> None:
        logger.error(
            "Unhandled exception while processing update %s: %s",
            getattr(event.update, "update_id", "?"),
            event.exception,
            exc_info=event.exception,
        )
        try:
            await state.clear()
        except Exception:
            pass

        update = event.update
        cq = update.callback_query
        msg = update.message or (cq.message if cq else None)

        if cq is not None:
            try:
                await cq.answer(t("my_booking_db_error_retry", lang), show_alert=True)
            except Exception:
                pass
            try:
                await cq.message.edit_reply_markup(reply_markup=EMPTY_KEYBOARD)
            except Exception:
                pass

        if msg is not None:
            try:
                await msg.answer(
                    t("tech_error", lang),
                    reply_markup=main_reply_keyboard(lang),
                    parse_mode="HTML",
                )
            except Exception as exc:
                logger.error("Error handler itself failed to notify the user: %s", exc)

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
    lang_gate = LanguageGateMiddleware()

    for observer in (dp.message, dp.callback_query):
        observer.outer_middleware(throttle)
        observer.outer_middleware(tracker)
        observer.outer_middleware(lang_gate)

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
