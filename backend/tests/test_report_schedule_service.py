"""Tests for report scheduling math.

Run with:
    cd backend && .venv/bin/pytest tests/test_report_schedule_service.py -v
"""
from __future__ import annotations

import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import time  # noqa: E402

from app.services.report_schedule_service import compute_next_run_at  # noqa: E402


def test_daily_next_run_today_if_time_not_passed():
    after = datetime(2026, 7, 19, 6, 0)  # 06:00 UTC
    result = compute_next_run_at("DAILY", time(8, 0), "UTC", None, None, after)
    assert result == datetime(2026, 7, 19, 8, 0)


def test_daily_next_run_tomorrow_if_time_passed():
    after = datetime(2026, 7, 19, 9, 0)  # after 08:00
    result = compute_next_run_at("DAILY", time(8, 0), "UTC", None, None, after)
    assert result == datetime(2026, 7, 20, 8, 0)


def test_weekly_picks_next_matching_weekday():
    # 2026-07-19 is a Sunday (weekday()==6). Target Monday (0).
    after = datetime(2026, 7, 19, 6, 0)
    result = compute_next_run_at("WEEKLY", time(8, 0), "UTC", 0, None, after)
    assert result == datetime(2026, 7, 20, 8, 0)  # Monday 2026-07-20


def test_biweekly_skips_one_week_from_weekly():
    after = datetime(2026, 7, 19, 6, 0)
    weekly = compute_next_run_at("WEEKLY", time(8, 0), "UTC", 0, None, after)
    biweekly = compute_next_run_at("BIWEEKLY", time(8, 0), "UTC", 0, None, after)
    assert (biweekly - weekly).days == 7


def test_monthly_picks_day_of_month_next_month_if_passed():
    after = datetime(2026, 7, 19, 6, 0)
    result = compute_next_run_at("MONTHLY", time(8, 0), "UTC", None, 1, after)
    assert result == datetime(2026, 8, 1, 8, 0)


def test_monthly_same_month_if_day_not_yet_passed():
    after = datetime(2026, 7, 1, 6, 0)
    result = compute_next_run_at("MONTHLY", time(8, 0), "UTC", None, 15, after)
    assert result == datetime(2026, 7, 15, 8, 0)


def test_timezone_converts_local_time_to_utc():
    # Europe/Brussels is UTC+2 in July (CEST). 08:00 local == 06:00 UTC.
    after = datetime(2026, 7, 19, 0, 0)  # UTC
    result = compute_next_run_at("DAILY", time(8, 0), "Europe/Brussels", None, None, after)
    assert result == datetime(2026, 7, 19, 6, 0)
