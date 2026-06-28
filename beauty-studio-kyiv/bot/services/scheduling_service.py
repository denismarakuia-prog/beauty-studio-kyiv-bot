"""
Slot generation logic — pure functions, no I/O.

Two responsibilities:
  1. Calendar grid generation (month-by-month, with prev/next navigation,
     bounded to "today .. today + CALENDAR_MONTHS_AHEAD months").
  2. Free time-slot computation for a chosen date, in the salon's local
     timezone (Europe/Kyiv), accounting for business hours, a minimum lead
     time, and already-taken slots.

Time-slot values are also encoded/decoded here. aiogram's CallbackData.pack()
rejects any field value containing the ':' separator character, so 'HH:MM'
can never be placed directly into a callback_data field — it must be encoded
as a separator-free token (e.g. '0900') for the wire, and decoded back to
'09:00' the instant it's read out of a callback, before touching anything
else (state, the database, notifications all keep using the real 'HH:MM'
form — only the callback_data wire format is special).
"""
from __future__ import annotations

import calendar as _calendar
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import List, Optional
from zoneinfo import ZoneInfo

from bot.salon_data import (
    CALENDAR_MONTHS_AHEAD,
    CLOSING_HOUR,
    MIN_LEAD_TIME_MINUTES,
    MONTHS_UA_NOMINATIVE,
    OPENING_HOUR,
    SLOT_STEP_MINUTES,
    TIMEZONE_NAME,
)

_TZ = ZoneInfo(TIMEZONE_NAME)
_MONTH_CAL = _calendar.Calendar(firstweekday=0)  # weeks start Monday, matches WEEKDAYS_UA


def now_local() -> datetime:
    """Current time in the salon's timezone."""
    return datetime.now(_TZ)


def today_local() -> date:
    return now_local().date()


def format_date_display(iso_date: str) -> str:
    """'YYYY-MM-DD' -> 'DD.MM.YYYY' for messages shown to user/admin.
    Malformed input safely returns the original string rather than raising."""
    try:
        d = date.fromisoformat(iso_date)
    except (ValueError, TypeError):
        return iso_date
    return d.strftime("%d.%m.%Y")


# ── Time encoding (callback-safe) ───────────────────────────────────────────────

def encode_time(time_str: str) -> str:
    """'09:00' -> '0900' — safe to place in a CallbackData field."""
    return time_str.replace(":", "")


def decode_time(code: str) -> str:
    """'0900' -> '09:00'. Returns '' if the code doesn't look like 4 digits."""
    code = code.strip()
    if len(code) != 4 or not code.isdigit():
        return ""
    return f"{code[:2]}:{code[2:]}"


# ── Month arithmetic ─────────────────────────────────────────────────────────────

def _shift_month(year: int, month: int, delta: int) -> tuple[int, int]:
    idx = year * 12 + (month - 1) + delta
    return idx // 12, idx % 12 + 1


def encode_month(year: int, month: int) -> str:
    """(2026, 6) -> '202606' — safe to place in a CallbackData field."""
    return f"{year:04d}{month:02d}"


def decode_month(code: str) -> Optional[tuple[int, int]]:
    code = code.strip()
    if len(code) != 6 or not code.isdigit():
        return None
    return int(code[:4]), int(code[4:6])


# ── Calendar grid ────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class CalendarDay:
    iso: Optional[str]   # 'YYYY-MM-DD' if this cell is a selectable day, else None
    label: str           # text shown on the button ('', '17', '20•' for today)


@dataclass(frozen=True)
class CalendarMonth:
    year: int
    month: int
    title: str                     # 'Червень 2026'
    weeks: List[List[CalendarDay]]  # each inner list has exactly 7 CalendarDay cells
    has_prev: bool
    has_next: bool
    prev_code: str                  # encoded target month for the ◀️ button
    next_code: str                  # encoded target month for the ▶️ button


def _last_bookable_month() -> tuple[int, int]:
    today = today_local()
    return _shift_month(today.year, today.month, CALENDAR_MONTHS_AHEAD)


def get_calendar_month(year: int, month: int) -> CalendarMonth:
    """
    Build a full month grid clamped to the bookable window:
    [current month .. current month + CALENDAR_MONTHS_AHEAD].
    Days outside that window (past days in the current month, or any day in
    a month beyond the window) are rendered as non-selectable blanks.
    """
    today = today_local()
    min_year, min_month = today.year, today.month
    max_year, max_month = _last_bookable_month()

    # Clamp the requested month into the valid window defensively (handles
    # stale/forged callback data gracefully instead of crashing).
    if (year, month) < (min_year, min_month):
        year, month = min_year, min_month
    elif (year, month) > (max_year, max_month):
        year, month = max_year, max_month

    weeks: List[List[CalendarDay]] = []
    for week in _MONTH_CAL.monthdatescalendar(year, month):
        row: List[CalendarDay] = []
        for d in week:
            if d.month != month:
                row.append(CalendarDay(iso=None, label=""))
                continue
            if d < today:
                row.append(CalendarDay(iso=None, label="·"))
                continue
            label = f"{d.day}•" if d == today else str(d.day)
            row.append(CalendarDay(iso=d.isoformat(), label=label))
        weeks.append(row)

    has_prev = (year, month) > (min_year, min_month)
    has_next = (year, month) < (max_year, max_month)
    prev_y, prev_m = _shift_month(year, month, -1)
    next_y, next_m = _shift_month(year, month, 1)

    title = f"{MONTHS_UA_NOMINATIVE[month - 1]} {year}"

    return CalendarMonth(
        year=year,
        month=month,
        title=title,
        weeks=weeks,
        has_prev=has_prev,
        has_next=has_next,
        prev_code=encode_month(prev_y, prev_m),
        next_code=encode_month(next_y, next_m),
    )


def default_calendar_month() -> CalendarMonth:
    today = today_local()
    return get_calendar_month(today.year, today.month)


# ── Time slots ───────────────────────────────────────────────────────────────────

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

    A malformed/empty date string (stale callback, corrupted state, etc.)
    safely yields an empty list rather than raising — callers already treat
    "no free slots" as a normal, handled case.
    """
    try:
        target_date = date.fromisoformat(booking_date_iso)
    except (ValueError, TypeError):
        return []

    all_slots = get_all_slot_times()
    taken = set(taken_times)
    free = [t for t in all_slots if t not in taken]

    if target_date == today_local():
        cutoff = now_local() + timedelta(minutes=MIN_LEAD_TIME_MINUTES)
        cutoff_minutes = cutoff.hour * 60 + cutoff.minute
        free = [
            t for t in free
            if (int(t[:2]) * 60 + int(t[3:])) >= cutoff_minutes
        ]

    return free


def is_slot_still_valid(booking_date_iso: str, booking_time: str) -> bool:
    """
    Final guard at confirmation time: re-verify the slot hasn't slipped into
    the past. Malformed input safely returns False (treated as "no longer
    valid, please re-pick") rather than raising.
    """
    try:
        target_date = date.fromisoformat(booking_date_iso)
    except (ValueError, TypeError):
        return False

    if target_date < today_local():
        return False
    if target_date > today_local():
        return True

    try:
        slot_time = datetime.strptime(booking_time, "%H:%M").time()
    except (ValueError, TypeError):
        return False

    cutoff = now_local() + timedelta(minutes=MIN_LEAD_TIME_MINUTES)
    slot_dt = datetime.combine(target_date, slot_time, tzinfo=_TZ)
    return slot_dt >= cutoff
