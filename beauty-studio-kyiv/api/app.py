"""
FastAPI application.

Lifecycle:
  startup  → init DB → create repos/services → create bot/dp → start polling task
  shutdown → cancel polling → close bot session

The web server (uvicorn) is the process supervisor; the bot polling runs as an
asyncio background task inside the same event loop.
"""
from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from bot.config import Config
from bot.core import create_bot_and_dispatcher
from bot.database.connection import init_db
from bot.database.repositories import BookingRepository, UserRepository
from bot.services.ai_service import AIService

logger = logging.getLogger(__name__)

_WEBAPP_DIR = Path(__file__).parent.parent / "webapp"
_WEBAPP_INDEX = _WEBAPP_DIR / "index.html"


def create_app(config: Config) -> FastAPI:

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # ── Startup ───────────────────────────────────────────────────────────
        logger.info("=" * 60)
        logger.info("  Beauty Studio Kyiv — starting")
        logger.info("=" * 60)
        config.log_summary()

        await init_db(config.db_path)

        user_repo    = UserRepository(config.db_path)
        booking_repo = BookingRepository(config.db_path)
        ai_service   = AIService(api_key=config.openai_api_key, model=config.openai_model)

        bot, dp = create_bot_and_dispatcher(config, user_repo)

        polling_task = asyncio.create_task(
            dp.start_polling(
                bot,
                allowed_updates=["message", "callback_query"],
                # Injected dependencies available in all handlers by param name:
                config       = config,
                user_repo    = user_repo,
                booking_repo = booking_repo,
                ai_service   = ai_service,
            )
        )
        logger.info("Bot polling started (long-polling mode).")

        yield  # ← application is running here

        # ── Shutdown ──────────────────────────────────────────────────────────
        logger.info("Shutting down — stopping bot polling…")
        polling_task.cancel()
        try:
            await polling_task
        except asyncio.CancelledError:
            pass
        await bot.session.close()
        logger.info("Bot session closed. Bye!")

    # ── FastAPI instance ───────────────────────────────────────────────────────
    app = FastAPI(
        title="Beauty Studio Kyiv",
        description="Premium beauty salon Telegram bot + Mini App",
        version="1.1.0",
        docs_url=None,   # disable in production
        redoc_url=None,
        lifespan=lifespan,
    )

    # ── Mini App ────────────────────────────────────────────────────────────────
    #
    # IMPORTANT: the Mini App is a single self-contained HTML file (CSS/JS
    # inlined, no separate static assets). We serve it via an EXPLICIT route
    # rather than relying solely on StaticFiles' mount + trailing-slash/
    # index.html auto-resolution, which behaves inconsistently across
    # Starlette versions for a bare "/webapp" request without a trailing
    # slash (some versions 307-redirect, some 404). An explicit route removes
    # all ambiguity: "/webapp" and "/webapp/" both deterministically return
    # the real HTML page with the correct content-type, every time.
    @app.get("/webapp", include_in_schema=False)
    @app.get("/webapp/", include_in_schema=False)
    async def webapp_index() -> HTMLResponse:
        if not _WEBAPP_INDEX.is_file():
            return HTMLResponse(
                "<h1>Mini App not found</h1><p>webapp/index.html is missing.</p>",
                status_code=404,
            )
        html = _WEBAPP_INDEX.read_text(encoding="utf-8")
        return HTMLResponse(content=html, status_code=200)

    # Mounted as a fallback for any future static assets (images, separate
    # css/js) placed under webapp/ — does not affect the explicit routes above.
    if _WEBAPP_DIR.is_dir():
        app.mount(
            "/webapp-assets",
            StaticFiles(directory=str(_WEBAPP_DIR)),
            name="webapp-assets",
        )
    else:
        logger.warning("webapp/ directory not found — Mini App will not be served.")

    # ── Routes ────────────────────────────────────────────────────────────────

    @app.get("/health", tags=["infra"])
    async def health() -> JSONResponse:
        return JSONResponse({"status": "ok", "service": "beauty-studio-kyiv"})

    @app.get("/", tags=["infra"])
    async def root() -> JSONResponse:
        return JSONResponse({
            "service": "Beauty Studio Kyiv Bot",
            "status": "running",
            "endpoints": {
                "health": "/health",
                "webapp": "/webapp",
            },
        })

    return app
