"""
Slot generation logic — pure functions, no I/O.
Determines which dates are bookable and which times within a date are free,
in the salon's local timezone (Europe/Kyiv), accounting for business hours,
a minimum lead time, and already-taken slots.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import List
from zoneinfo import ZoneInfo

from bot.salon_data import (
    BOOKING_WINDOW_DAYS,
    CLOSING_HOUR,
    MIN_LEAD_TIME_MINUTES,
    MONTHS_UA,
    OPENING_HOUR,
    SLOT_STEP_MINUTES,
    TIMEZONE_NAME,
    WEEKDAYS_UA,
)

_TZ = ZoneInfo(TIMEZONE_NAME)


def now_local() -> datetime:
    """Current time in the salon's timezone."""
    return datetime.now(_TZ)


def today_local() -> date:
    return now_local().date()


@dataclass(frozen=True)
class DateOption:
    iso: str          # 'YYYY-MM-DD' — stored in DB / used as callback payload
    label: str        # 'Сьогодні', 'Завтра', or 'Пт, 26 черв.'


def format_date_human(d: date) -> str:
    """'Пт, 26 червня' style formatting in Ukrainian."""
    weekday = WEEKDAYS_UA[d.weekday()]
    month = MONTHS_UA[d.month - 1]
    return f"{weekday}, {d.day} {month}"


def format_date_display(iso_date: str) -> str:
    """'YYYY-MM-DD' -> 'DD.MM.YYYY' for messages shown to user/admin."""
    d = date.fromisoformat(iso_date)
    return d.strftime("%d.%m.%Y")


def get_bookable_dates() -> List[DateOption]:
    """All dates the client is allowed to pick from, today .. today+window."""
    today = today_local()
    options: List[DateOption] = []
    for offset in range(BOOKING_WINDOW_DAYS):
        d = today + timedelta(days=offset)
        if offset == 0:
            label = f"Сьогодні · {format_date_human(d)}"
        elif offset == 1:
            label = f"Завтра · {format_date_human(d)}"
        else:
            label = format_date_human(d)
        options.append(DateOption(iso=d.isoformat(), label=label))
    return options


def get_all_slot_times() -> List[str]:
    """All possible 'HH:MM' slots within business hours, ignoring bookings."""
    slots: List[str] = []
    minutes = OPENING_HOUR * 60
    end_minutes = CLOSING_HOUR * 60
    while minutes < end_minutes:
        h, m = divmod(minutes, 60)
        slots.append(f"{h:02d}:{m:02d}")
        minutes += SLOT_STEP_MINUTES
    return slots


def get_available_times(booking_date_iso: str, taken_times: List[str]) -> List[str]:
    """
    Free 'HH:MM' slots for the given ISO date, excluding:
      - times already present in taken_times
      - (if the date is today) times within MIN_LEAD_TIME_MINUTES of now, or in the past
    """
    all_slots = get_all_slot_times()
    taken = set(taken_times)
    free = [t for t in all_slots if t not in taken]

    target_date = date.fromisoformat(booking_date_iso)
    if target_date == today_local():
        cutoff = now_local() + timedelta(minutes=MIN_LEAD_TIME_MINUTES)
        cutoff_minutes = cutoff.hour * 60 + cutoff.minute
        free = [
            t for t in free
            if (int(t[:2]) * 60 + int(t[3:])) >= cutoff_minutes
        ]

    return free


def is_slot_still_valid(booking_date_iso: str, booking_time: str) -> bool:
    """Final guard at confirmation time: re-verify the slot hasn't slipped into the past."""
    target_date = date.fromisoformat(booking_date_iso)
    if target_date < today_local():
        return False
    if target_date > today_local():
        return True

    cutoff = now_local() + timedelta(minutes=MIN_LEAD_TIME_MINUTES)
    slot_dt = datetime.combine(
        target_date,
        datetime.strptime(booking_time, "%H:%M").time(),
        tzinfo=_TZ,
    )
    return slot_dt >= cutoff
