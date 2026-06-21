"""
Repository layer — all raw SQL lives here, handlers never touch the DB directly.
"""
from __future__ import annotations

import logging
import sqlite3
from typing import Any, Dict, List, Optional

import aiosqlite

logger = logging.getLogger(__name__)


class SlotTakenError(Exception):
    """Raised when a booking attempt loses the race for a date+time slot."""


# ── User Repository ────────────────────────────────────────────────────────────


class UserRepository:
    def __init__(self, db_path: str) -> None:
        self._path = db_path

    async def upsert_user(
        self,
        telegram_id: int,
        username: Optional[str],
        first_name: Optional[str],
    ) -> None:
        """Insert or update user record; preserves phone/created_at if already set."""
        async with aiosqlite.connect(self._path) as db:
            await db.execute(
                """
                INSERT INTO users (telegram_id, username, first_name)
                VALUES (?, ?, ?)
                ON CONFLICT(telegram_id) DO UPDATE SET
                    username   = excluded.username,
                    first_name = excluded.first_name,
                    is_blocked = 0
                """,
                (telegram_id, username, first_name),
            )
            await db.commit()

    async def save_contact(
        self,
        telegram_id: int,
        phone: str,
        first_name: Optional[str],
        last_name: Optional[str],
    ) -> None:
        """Permanently store the user's phone + name from a shared Telegram contact."""
        async with aiosqlite.connect(self._path) as db:
            await db.execute(
                """
                INSERT INTO users (telegram_id, first_name, last_name, phone)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(telegram_id) DO UPDATE SET
                    phone      = excluded.phone,
                    first_name = COALESCE(excluded.first_name, users.first_name),
                    last_name  = excluded.last_name
                """,
                (telegram_id, first_name, last_name, phone),
            )
            await db.commit()

    async def get_user(self, telegram_id: int) -> Optional[Dict[str, Any]]:
        async with aiosqlite.connect(self._path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM users WHERE telegram_id = ?", (telegram_id,)
            ) as cur:
                row = await cur.fetchone()
                return dict(row) if row else None

    async def save_name(self, telegram_id: int, full_name: str) -> None:
        """Permanently store the explicitly-typed display name for this user."""
        async with aiosqlite.connect(self._path) as db:
            await db.execute(
                """
                INSERT INTO users (telegram_id, full_name)
                VALUES (?, ?)
                ON CONFLICT(telegram_id) DO UPDATE SET
                    full_name = excluded.full_name
                """,
                (telegram_id, full_name),
            )
            await db.commit()

    async def has_name(self, telegram_id: int) -> bool:
        user = await self.get_user(telegram_id)
        return bool(user and user.get("full_name"))

    async def has_phone(self, telegram_id: int) -> bool:
        user = await self.get_user(telegram_id)
        return bool(user and user.get("phone"))

    async def get_all_users(self) -> List[Dict[str, Any]]:
        async with aiosqlite.connect(self._path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM users ORDER BY created_at DESC"
            ) as cur:
                rows = await cur.fetchall()
                return [dict(r) for r in rows]

    async def get_all_telegram_ids(self) -> List[int]:
        """Returns IDs of non-blocked users for broadcast."""
        async with aiosqlite.connect(self._path) as db:
            async with db.execute(
                "SELECT telegram_id FROM users WHERE is_blocked = 0"
            ) as cur:
                return [row[0] for row in await cur.fetchall()]

    async def count_users(self) -> int:
        async with aiosqlite.connect(self._path) as db:
            async with db.execute("SELECT COUNT(*) FROM users") as cur:
                row = await cur.fetchone()
                return row[0] if row else 0

    async def mark_blocked(self, telegram_id: int) -> None:
        async with aiosqlite.connect(self._path) as db:
            await db.execute(
                "UPDATE users SET is_blocked = 1 WHERE telegram_id = ?",
                (telegram_id,),
            )
            await db.commit()


# ── Booking Repository ──────────────────────────────────────────────────────────


class BookingRepository:
    def __init__(self, db_path: str) -> None:
        self._path = db_path

    async def get_taken_times(self, booking_date: str) -> List[str]:
        """Return all 'HH:MM' times already taken by an ACTIVE booking on that date."""
        async with aiosqlite.connect(self._path) as db:
            async with db.execute(
                "SELECT booking_time FROM bookings "
                "WHERE booking_date = ? AND status = 'active'",
                (booking_date,),
            ) as cur:
                return [row[0] for row in await cur.fetchall()]

    async def get_active_booking_for_user(
        self, telegram_id: int
    ) -> Optional[Dict[str, Any]]:
        async with aiosqlite.connect(self._path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM bookings "
                "WHERE telegram_id = ? AND status = 'active' "
                "ORDER BY booking_date, booking_time LIMIT 1",
                (telegram_id,),
            ) as cur:
                row = await cur.fetchone()
                return dict(row) if row else None

    async def create_booking(
        self,
        *,
        telegram_id: int,
        name: str,
        phone: str,
        service_id: str,
        service_name: str,
        booking_date: str,
        booking_time: str,
    ) -> int:
        """
        Insert a new active booking.
        Raises SlotTakenError if the (date, time) slot was taken concurrently
        (enforced by the partial unique index on bookings).
        """
        try:
            async with aiosqlite.connect(self._path) as db:
                cur = await db.execute(
                    """
                    INSERT INTO bookings
                        (telegram_id, name, phone, service_id, service_name,
                         booking_date, booking_time, status)
                    VALUES (?, ?, ?, ?, ?, ?, ?, 'active')
                    """,
                    (telegram_id, name, phone, service_id, service_name,
                     booking_date, booking_time),
                )
                await db.commit()
                return cur.lastrowid  # type: ignore[return-value]
        except (aiosqlite.IntegrityError, sqlite3.IntegrityError) as exc:
            logger.info("Slot race lost for %s %s: %s", booking_date, booking_time, exc)
            raise SlotTakenError(f"{booking_date} {booking_time} is already taken") from exc

    async def cancel_booking(self, booking_id: int, telegram_id: int) -> Optional[Dict[str, Any]]:
        """
        Cancel an active booking owned by telegram_id.
        Returns the booking row (pre-cancellation data) if cancelled, else None.
        """
        async with aiosqlite.connect(self._path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM bookings WHERE id = ? AND telegram_id = ? AND status = 'active'",
                (booking_id, telegram_id),
            ) as cur:
                row = await cur.fetchone()
            if not row:
                return None

            await db.execute(
                "UPDATE bookings SET status = 'cancelled', "
                "cancelled_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now') "
                "WHERE id = ?",
                (booking_id,),
            )
            await db.commit()
            return dict(row)

    async def get_all_bookings(self) -> List[Dict[str, Any]]:
        async with aiosqlite.connect(self._path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM bookings ORDER BY created_at DESC"
            ) as cur:
                return [dict(r) for r in await cur.fetchall()]

    async def get_recent_bookings(self, limit: int = 10) -> List[Dict[str, Any]]:
        async with aiosqlite.connect(self._path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM bookings ORDER BY created_at DESC LIMIT ?", (limit,)
            ) as cur:
                return [dict(r) for r in await cur.fetchall()]

    async def count_bookings(self) -> int:
        async with aiosqlite.connect(self._path) as db:
            async with db.execute("SELECT COUNT(*) FROM bookings") as cur:
                row = await cur.fetchone()
                return row[0] if row else 0

    async def count_active_bookings(self) -> int:
        async with aiosqlite.connect(self._path) as db:
            async with db.execute(
                "SELECT COUNT(*) FROM bookings WHERE status = 'active'"
            ) as cur:
                row = await cur.fetchone()
                return row[0] if row else 0

    async def count_bookings_today(self) -> int:
        async with aiosqlite.connect(self._path) as db:
            async with db.execute(
                "SELECT COUNT(*) FROM bookings WHERE DATE(created_at) = DATE('now')"
            ) as cur:
                row = await cur.fetchone()
                return row[0] if row else 0

    async def count_bookings_this_week(self) -> int:
        async with aiosqlite.connect(self._path) as db:
            async with db.execute(
                "SELECT COUNT(*) FROM bookings "
                "WHERE created_at >= strftime('%Y-%m-%dT%H:%M:%SZ', 'now', '-7 days')"
            ) as cur:
                row = await cur.fetchone()
                return row[0] if row else 0
