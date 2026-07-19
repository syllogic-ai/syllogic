"""Computes the next scheduled send time for a Report.

All persisted `next_run_at` values are naive UTC datetimes (matching the
rest of this codebase's `DateTime` columns, which are naive-UTC by
convention — see `Transaction.booked_at`).
"""
from __future__ import annotations

from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

_UTC = ZoneInfo("UTC")


def compute_next_run_at(
    frequency: str,
    send_time: time,
    timezone: str,
    send_day_of_week: int | None,
    send_day_of_month: int | None,
    after: datetime,
) -> datetime:
    """Return the next UTC datetime a report is due, strictly after `after`.

    `after` is a naive UTC datetime. `send_time` and the day fields are
    interpreted in `timezone` (IANA name), then converted back to naive
    UTC for storage/comparison.
    """
    tz = ZoneInfo(timezone)
    after_local = after.replace(tzinfo=_UTC).astimezone(tz)

    if frequency == "DAILY":
        candidate_local = _combine(after_local.date(), send_time, tz)
        if candidate_local <= after_local:
            candidate_local = _combine(after_local.date() + timedelta(days=1), send_time, tz)
        return _to_naive_utc(candidate_local)

    if frequency in ("WEEKLY", "BIWEEKLY"):
        if send_day_of_week is None:
            raise ValueError("send_day_of_week is required for WEEKLY/BIWEEKLY")
        days_ahead = (send_day_of_week - after_local.weekday()) % 7
        candidate_date = after_local.date() + timedelta(days=days_ahead)
        candidate_local = _combine(candidate_date, send_time, tz)
        if candidate_local <= after_local:
            candidate_local = _combine(candidate_date + timedelta(days=7), send_time, tz)
        if frequency == "BIWEEKLY":
            candidate_local = _combine(candidate_local.date() + timedelta(days=7), send_time, tz)
        return _to_naive_utc(candidate_local)

    if frequency == "MONTHLY":
        if send_day_of_month is None:
            raise ValueError("send_day_of_month is required for MONTHLY")
        candidate_date = _safe_date(after_local.year, after_local.month, send_day_of_month)
        candidate_local = _combine(candidate_date, send_time, tz)
        if candidate_local <= after_local:
            year, month = after_local.year, after_local.month + 1
            if month > 12:
                year, month = year + 1, 1
            candidate_date = _safe_date(year, month, send_day_of_month)
            candidate_local = _combine(candidate_date, send_time, tz)
        return _to_naive_utc(candidate_local)

    raise ValueError(f"Unknown frequency: {frequency}")


def _combine(date_part, time_part: time, tz: ZoneInfo) -> datetime:
    return datetime.combine(date_part, time_part, tzinfo=tz)


def _to_naive_utc(dt: datetime) -> datetime:
    return dt.astimezone(_UTC).replace(tzinfo=None)


def _safe_date(year: int, month: int, day: int):
    import calendar

    last_day = calendar.monthrange(year, month)[1]
    return datetime(year, month, min(day, last_day)).date()
