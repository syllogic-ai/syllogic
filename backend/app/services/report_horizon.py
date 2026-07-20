"""Digest horizon: how far back a report looks, derived from its cadence.

A weekly digest should report on the last seven days, not on all of history.
Kept dependency-free (no DB, no models) so it is trivially testable.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

# Rolling windows, not calendar periods: "monthly" means the last 30 days
# rather than the previous calendar month.
_HORIZON_DAYS = {
    "DAILY": 1,
    "WEEKLY": 7,
    "BIWEEKLY": 14,
    "MONTHLY": 30,
}

# An unexpected frequency must not stop a report from sending.
_DEFAULT_DAYS = 30

_LABELS = {
    1: "Last 24 hours",
    7: "Last 7 days",
    14: "Last 14 days",
    30: "Last 30 days",
}


def horizon_days(frequency: Optional[str]) -> int:
    """Number of days a report of this cadence looks back."""
    if not frequency:
        return _DEFAULT_DAYS
    return _HORIZON_DAYS.get(frequency.upper(), _DEFAULT_DAYS)


def horizon_start(frequency: Optional[str], now: datetime) -> datetime:
    """Inclusive lower bound for `booked_at`."""
    return now - timedelta(days=horizon_days(frequency))


def period_label(frequency: Optional[str]) -> str:
    """Human-readable window, rendered in the email masthead."""
    return _LABELS[horizon_days(frequency)]
