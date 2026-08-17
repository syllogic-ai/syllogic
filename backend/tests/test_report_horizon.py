"""Tests for the digest horizon helper.

Run with:
    cd backend && .venv/bin/pytest tests/test_report_horizon.py -v
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.report_horizon import horizon_days, horizon_start, period_label  # noqa: E402


def test_horizon_days_per_frequency():
    assert horizon_days("DAILY") == 1
    assert horizon_days("WEEKLY") == 7
    assert horizon_days("BIWEEKLY") == 14
    assert horizon_days("MONTHLY") == 30


def test_horizon_days_is_case_insensitive():
    assert horizon_days("weekly") == 7


def test_unknown_frequency_falls_back_to_30_days():
    # A report must still send rather than raise on an unexpected value.
    assert horizon_days("FORTNIGHTLY") == 30
    assert horizon_days("") == 30
    assert horizon_days(None) == 30


def test_horizon_start_subtracts_the_window():
    now = datetime(2026, 7, 20, 8, 0, 0)
    assert horizon_start("WEEKLY", now) == now - timedelta(days=7)
    assert horizon_start("DAILY", now) == now - timedelta(days=1)


def test_period_label_per_frequency():
    assert period_label("DAILY") == "Last 24 hours"
    assert period_label("WEEKLY") == "Last 7 days"
    assert period_label("BIWEEKLY") == "Last 14 days"
    assert period_label("MONTHLY") == "Last 30 days"
    assert period_label("NONSENSE") == "Last 30 days"
