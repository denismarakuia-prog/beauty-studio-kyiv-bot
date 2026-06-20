"""Database initialisation — creates tables if they don't exist."""
from __future__ import annotations

import logging
import os

import aiosqlite

logger = logging.getLogger(__name__)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    telegram_id INTEGER UNIQUE NOT NULL,
    username    TEXT,
    first_name  TEXT,
    last_name   TEXT,
    phone       TEXT,
    is_blocked  INTEGER NOT NULL DEFAULT 0,
    created_at  TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

CREATE INDEX IF NOT EXISTS idx_users_telegram_id ON users (telegram_id);

CREATE TABLE IF NOT EXISTS bookings (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    telegram_id  INTEGER NOT NULL,
    name         TEXT NOT NULL,
    phone        TEXT NOT NULL,
    service_id   TEXT NOT NULL,
    service_name TEXT NOT NULL,
    booking_date TEXT NOT NULL,                 -- 'YYYY-MM-DD'
    booking_time TEXT NOT NULL,                 -- 'HH:MM'
    status       TEXT NOT NULL DEFAULT 'active', -- 'active' | 'cancelled'
    created_at   TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    cancelled_at TEXT,
    FOREIGN KEY (telegram_id) REFERENCES users (telegram_id) ON DELETE SET NULL
);

-- The core anti-double-booking guarantee: only ONE active booking may exist
-- for a given date+time slot. Enforced at the database level so concurrent
-- requests (e.g. a double-tap on the same time button) cannot both succeed,
-- regardless of any application-level race condition.
CREATE UNIQUE INDEX IF NOT EXISTS idx_unique_active_slot
    ON bookings (booking_date, booking_time)
    WHERE status = 'active';

CREATE INDEX IF NOT EXISTS idx_bookings_telegram_id ON bookings (telegram_id);
CREATE INDEX IF NOT EXISTS idx_bookings_date ON bookings (booking_date);
CREATE INDEX IF NOT EXISTS idx_bookings_status ON bookings (status);
CREATE INDEX IF NOT EXISTS idx_bookings_created_at ON bookings (created_at);
"""


async def init_db(db_path: str) -> None:
    """
    Ensure the database directory exists and run the schema.
    Safe to call on every startup (idempotent).
    """
    directory = os.path.dirname(os.path.abspath(db_path))
    os.makedirs(directory, exist_ok=True)

    async with aiosqlite.connect(db_path) as db:
        await db.execute("PRAGMA journal_mode=WAL;")
        await db.execute("PRAGMA foreign_keys=ON;")
        await db.executescript(_SCHEMA)
        await db.commit()

    logger.info("Database ready: %s", db_path)
