"""
Centralized configuration loaded from environment variables.
To adapt for another salon: update .env / Render env vars and salon_data.py.
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import List

from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)


@dataclass
class Config:
    # Bot
    bot_token: str
    admin_ids: List[int]

    # OpenAI
    openai_api_key: str
    openai_model: str

    # Database
    db_path: str

    # Mini App / Server
    webapp_url: str
    port: int
    log_level: str

    @classmethod
    def load(cls) -> "Config":
        bot_token = os.environ.get("BOT_TOKEN", "").strip()
        if not bot_token:
            raise ValueError(
                "BOT_TOKEN environment variable is required. "
                "Set it in .env or in the Render dashboard."
            )

        raw_ids = os.environ.get("ADMIN_IDS", "7520370397")
        admin_ids: List[int] = []
        for part in raw_ids.split(","):
            part = part.strip()
            if part.isdigit():
                admin_ids.append(int(part))

        if not admin_ids:
            raise ValueError(
                "ADMIN_IDS must contain at least one valid Telegram user ID."
            )

        openai_api_key = os.environ.get("OPENAI_API_KEY", "").strip()
        openai_model   = os.environ.get("OPENAI_MODEL", "gpt-4o-mini").strip()
        db_path        = os.environ.get("DATABASE_PATH", "./data/beauty_studio.db").strip()
        webapp_url     = os.environ.get("WEBAPP_URL", "").strip()

        port_str = os.environ.get("PORT", "8000").strip()
        try:
            port = int(port_str)
        except ValueError:
            port = 8000

        log_level = os.environ.get("LOG_LEVEL", "INFO").strip().upper()

        return cls(
            bot_token=bot_token,
            admin_ids=admin_ids,
            openai_api_key=openai_api_key,
            openai_model=openai_model,
            db_path=db_path,
            webapp_url=webapp_url,
            port=port,
            log_level=log_level,
        )

    def is_admin(self, user_id: int) -> bool:
        return user_id in self.admin_ids

    def log_summary(self) -> None:
        logger.info("Configuration:")
        logger.info("  Admin IDs   : %s", self.admin_ids)
        logger.info("  DB path     : %s", self.db_path)
        logger.info("  Webapp URL  : %s", self.webapp_url or "(not set)")
        logger.info("  OpenAI model: %s", self.openai_model)
        logger.info("  AI enabled  : %s", bool(self.openai_api_key))
        logger.info("  Port        : %s", self.port)
