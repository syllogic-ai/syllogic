"""Tests for Report / ReportRun models.

Run with:
    cd backend && .venv/bin/pytest tests/test_report_models.py -v
"""
from __future__ import annotations

import base64
import os
import sys
import uuid
from datetime import datetime, time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _set_test_env() -> None:
    key = base64.urlsafe_b64encode(b"p" * 32).decode("utf-8").rstrip("=")
    os.environ["DATA_ENCRYPTION_KEY_CURRENT"] = key
    os.environ["DATA_ENCRYPTION_KEY_ID"] = "k-test-report-models"
    os.environ.pop("DATA_ENCRYPTION_KEY_PREVIOUS", None)


_set_test_env()

from app.database import SessionLocal  # noqa: E402
from app.models import Report, ReportRun, User  # noqa: E402


def _make_user(db) -> User:
    user = User(id=f"test-user-{uuid.uuid4()}", email=f"{uuid.uuid4()}@example.com", name="Test User")
    db.add(user)
    db.flush()
    return user


def test_create_report_and_run_round_trip():
    db = SessionLocal()
    try:
        user = _make_user(db)
        account_id = str(uuid.uuid4())
        report = Report(
            user_id=user.id,
            name="Weekly summary",
            account_ids=[account_id],
            transaction_mode="TOP_N",
            transaction_count=5,
            transaction_direction="EXPENSE",
            frequency="WEEKLY",
            send_time=time(8, 0),
            send_day_of_week=0,
            timezone="Europe/Brussels",
            recipient_emails=["me@example.com"],
        )
        db.add(report)
        db.flush()

        run = ReportRun(
            report_id=report.id,
            scheduled_for=datetime(2026, 7, 20, 8, 0),
            status="SCHEDULED",
            recipient_emails=["me@example.com"],
        )
        db.add(run)
        db.flush()

        fetched = db.query(Report).filter(Report.id == report.id).one()
        assert fetched.transaction_direction == "EXPENSE"
        # JSONB list columns must round-trip exactly, not e.g. degrade to a
        # string or drop entries.
        assert fetched.recipient_emails == ["me@example.com"]
        assert fetched.account_ids == [account_id]

        fetched_run = db.query(ReportRun).filter(ReportRun.report_id == report.id).one()
        assert fetched_run.status == "SCHEDULED"
        assert fetched_run.recipient_emails == ["me@example.com"]
    finally:
        db.rollback()
        db.close()
