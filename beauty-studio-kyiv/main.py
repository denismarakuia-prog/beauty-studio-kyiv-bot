"""
Entry point for local development and Render.com deployment.
Uvicorn is the process host; the Aiogram bot runs inside the same event loop
as a background task started in the FastAPI lifespan.
"""
from __future__ import annotations

import logging
import os
import sys

# Load .env FIRST so every subsequent os.environ.get() sees the values.
from dotenv import load_dotenv
load_dotenv()


def _setup_logging(level: str = "INFO") -> None:
    logging.basicConfig(
        stream=sys.stdout,
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("aiogram").setLevel(logging.INFO)


def main() -> None:
    import uvicorn
    from bot.config import Config

    log_level = os.environ.get("LOG_LEVEL", "INFO").upper()
    _setup_logging(log_level)

    logger = logging.getLogger(__name__)

    try:
        config = Config.load()
    except ValueError as exc:
        logging.critical("Configuration error: %s", exc)
        sys.exit(1)

    from api.app import create_app

    app = create_app(config)

    logger.info("Starting uvicorn on 0.0.0.0:%s", config.port)
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=config.port,
        workers=1,          # must be 1 — polling task lives in this event loop
        log_level=log_level.lower(),
        access_log=False,   # reduce noise; /health is hit by Render every 30 s
    )


if __name__ == "__main__":
    main()
