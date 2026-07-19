"""Tests for report Celery tasks.

Run with:
    cd backend && .venv/bin/pytest tests/test_report_tasks.py -v
"""
from __future__ import annotations

import base64
import os
import sys
import uuid
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _set_test_env() -> None:
    key = base64.urlsafe_b64encode(b"p" * 32).decode("utf-8").rstrip("=")
    os.environ["DATA_ENCRYPTION_KEY_CURRENT"] = key
    os.environ["DATA_ENCRYPTION_KEY_ID"] = "k-test-report-tasks"
    os.environ.pop("DATA_ENCRYPTION_KEY_PREVIOUS", None)


_set_test_env()

from app.database import SessionLocal  # noqa: E402
from app.models import Report, ReportRun, User  # noqa: E402
from tasks import report_tasks  # noqa: E402


def _seed_due_report(db) -> Report:
    user = User(id=f"test-user-{uuid.uuid4()}", email=f"{uuid.uuid4()}@example.com", name="Test")
    db.add(user)
    db.flush()
    report = Report(
        user_id=user.id,
        name="Daily",
        frequency="DAILY",
        recipient_emails=["me@example.com"],
        is_active=True,
        next_run_at=datetime.utcnow() - timedelta(minutes=1),
    )
    db.add(report)
    db.flush()
    return report


def test_check_due_reports_enqueues_and_reschedules():
    db = SessionLocal()
    try:
        report = _seed_due_report(db)
        db.commit()

        with patch.object(report_tasks.send_report_run, "delay") as mock_delay:
            report_tasks.check_due_reports()

        db.refresh(report)
        assert report.next_run_at > datetime.utcnow()
        mock_delay.assert_called_once()

        runs = db.query(ReportRun).filter(ReportRun.report_id == report.id).all()
        assert len(runs) >= 1
    finally:
        db.rollback()
        db.close()


def test_send_report_run_success_marks_succeeded():
    db = SessionLocal()
    try:
        report = _seed_due_report(db)
        run = ReportRun(report_id=report.id, status="SCHEDULED", recipient_emails=report.recipient_emails)
        db.add(run)
        db.commit()
        run_id = str(run.id)

        fake_render = MagicMock(returncode=0, stdout='{"html": "<p>hi</p>", "text": "hi"}', stderr="")
        mock_adapter = MagicMock()
        with patch.object(report_tasks.subprocess, "run", return_value=fake_render), \
             patch.object(report_tasks, "get_mail_adapter", return_value=mock_adapter):
            report_tasks.send_report_run(run_id)

        db.refresh(run)
        assert run.status == "SUCCEEDED"
        assert run.finished_at is not None
        mock_adapter.send.assert_called_once()
    finally:
        db.rollback()
        db.close()


def test_send_report_run_failure_marks_failed_without_raising():
    db = SessionLocal()
    try:
        report = _seed_due_report(db)
        run = ReportRun(report_id=report.id, status="SCHEDULED", recipient_emails=report.recipient_emails)
        db.add(run)
        db.commit()
        run_id = str(run.id)

        with patch.object(report_tasks, "get_mail_adapter", side_effect=RuntimeError("no provider")):
            report_tasks.send_report_run(run_id)  # must not raise

        db.refresh(run)
        assert run.status == "FAILED"
        assert "no provider" in run.error_message
    finally:
        db.rollback()
        db.close()
