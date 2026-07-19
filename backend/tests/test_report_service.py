"""Tests for the shared report service layer.

Run with:
    cd backend && .venv/bin/pytest tests/test_report_service.py -v
"""
from __future__ import annotations

import base64
import os
import sys
import uuid
from datetime import datetime, time, timedelta
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _set_test_env() -> None:
    key = base64.urlsafe_b64encode(b"p" * 32).decode("utf-8").rstrip("=")
    os.environ["DATA_ENCRYPTION_KEY_CURRENT"] = key
    os.environ["DATA_ENCRYPTION_KEY_ID"] = "k-test-report-service"
    os.environ.pop("DATA_ENCRYPTION_KEY_PREVIOUS", None)


_set_test_env()

from app.database import SessionLocal  # noqa: E402
from app.models import Account, Report, ReportRun, User  # noqa: E402
from app.services import report_service  # noqa: E402


def _seed_user(db) -> User:
    user = User(id=f"test-user-{uuid.uuid4()}", email=f"{uuid.uuid4()}@example.com", name="Test User")
    db.add(user)
    db.flush()
    return user


def _base_payload(**overrides):
    payload = {
        "name": "Weekly summary",
        "frequency": "WEEKLY",
        "send_day_of_week": 0,
        "recipient_emails": ["me@example.com"],
    }
    payload.update(overrides)
    return payload


def test_create_report_success():
    db = SessionLocal()
    try:
        user = _seed_user(db)
        report = report_service.create_report(db, user.id, _base_payload())
        assert report.id is not None
        assert report.next_run_at is not None
        assert report.frequency == "WEEKLY"
    finally:
        db.query(User).filter(User.id == user.id).delete()
        db.commit()
        db.rollback()
        db.close()


def test_create_report_rejects_invalid_frequency():
    db = SessionLocal()
    try:
        user = _seed_user(db)
        try:
            report_service.create_report(db, user.id, _base_payload(frequency="YEARLY"))
            assert False, "expected ReportValidationError"
        except report_service.ReportValidationError:
            pass
    finally:
        db.query(User).filter(User.id == user.id).delete()
        db.commit()
        db.rollback()
        db.close()


def test_create_report_rejects_weekly_without_send_day_of_week():
    db = SessionLocal()
    try:
        user = _seed_user(db)
        payload = _base_payload()
        del payload["send_day_of_week"]
        try:
            report_service.create_report(db, user.id, payload)
            assert False, "expected ReportValidationError"
        except report_service.ReportValidationError:
            pass
    finally:
        db.query(User).filter(User.id == user.id).delete()
        db.commit()
        db.rollback()
        db.close()


def test_create_report_rejects_foreign_account_id():
    db = SessionLocal()
    try:
        user = _seed_user(db)
        other = _seed_user(db)
        acc = Account(user_id=other.id, name="Other's account", account_type="checking", currency="EUR")
        db.add(acc)
        db.flush()
        try:
            report_service.create_report(db, user.id, _base_payload(account_ids=[str(acc.id)]))
            assert False, "expected ReportValidationError"
        except report_service.ReportValidationError:
            pass
    finally:
        db.query(User).filter(User.id.in_([user.id, other.id])).delete(synchronize_session=False)
        db.commit()
        db.rollback()
        db.close()


def test_get_report_raises_not_found_for_foreign_report():
    db = SessionLocal()
    try:
        user = _seed_user(db)
        other = _seed_user(db)
        report = report_service.create_report(db, other.id, _base_payload())
        try:
            report_service.get_report(db, user.id, str(report.id))
            assert False, "expected ReportNotFoundError"
        except report_service.ReportNotFoundError:
            pass
    finally:
        db.query(User).filter(User.id.in_([user.id, other.id])).delete(synchronize_session=False)
        db.commit()
        db.rollback()
        db.close()


def test_update_report_partial_update_preserves_other_fields():
    db = SessionLocal()
    try:
        user = _seed_user(db)
        report = report_service.create_report(db, user.id, _base_payload())
        updated = report_service.update_report(db, user.id, str(report.id), {"is_active": False})
        assert updated.is_active is False
        assert updated.name == "Weekly summary"
        assert updated.frequency == "WEEKLY"
    finally:
        db.query(User).filter(User.id == user.id).delete()
        db.commit()
        db.rollback()
        db.close()


def test_update_report_rejects_frequency_change_without_day_field():
    db = SessionLocal()
    try:
        user = _seed_user(db)
        report = report_service.create_report(db, user.id, _base_payload(frequency="DAILY", send_day_of_week=None))
        try:
            report_service.update_report(db, user.id, str(report.id), {"frequency": "MONTHLY"})
            assert False, "expected ReportValidationError"
        except report_service.ReportValidationError:
            pass
        # Confirm no partial mutation was committed.
        db.rollback()
        fetched = report_service.get_report(db, user.id, str(report.id))
        assert fetched.frequency == "DAILY"
    finally:
        db.query(User).filter(User.id == user.id).delete()
        db.commit()
        db.rollback()
        db.close()


def test_update_report_rejects_explicit_null_account_ids():
    db = SessionLocal()
    try:
        user = _seed_user(db)
        report = report_service.create_report(db, user.id, _base_payload())
        try:
            report_service.update_report(db, user.id, str(report.id), {"account_ids": None})
            assert False, "expected ReportValidationError"
        except report_service.ReportValidationError:
            pass
    finally:
        db.query(User).filter(User.id == user.id).delete()
        db.commit()
        db.rollback()
        db.close()


def test_delete_report_removes_it():
    db = SessionLocal()
    try:
        user = _seed_user(db)
        report = report_service.create_report(db, user.id, _base_payload())
        report_id = str(report.id)
        report_service.delete_report(db, user.id, report_id)
        try:
            report_service.get_report(db, user.id, report_id)
            assert False, "expected ReportNotFoundError"
        except report_service.ReportNotFoundError:
            pass
    finally:
        db.query(User).filter(User.id == user.id).delete()
        db.commit()
        db.rollback()
        db.close()


def test_delete_report_raises_not_found_for_foreign_report():
    db = SessionLocal()
    try:
        user = _seed_user(db)
        other = _seed_user(db)
        report = report_service.create_report(db, other.id, _base_payload())
        try:
            report_service.delete_report(db, user.id, str(report.id))
            assert False, "expected ReportNotFoundError"
        except report_service.ReportNotFoundError:
            pass
    finally:
        db.query(User).filter(User.id.in_([user.id, other.id])).delete(synchronize_session=False)
        db.commit()
        db.rollback()
        db.close()


def test_send_test_report_creates_run_and_enqueues():
    db = SessionLocal()
    try:
        user = _seed_user(db)
        report = report_service.create_report(db, user.id, _base_payload())
        with patch("app.services.report_service.send_report_run") as mock_task:
            run = report_service.send_test_report(db, user.id, str(report.id))
        assert run.is_test is True
        assert run.status == "SCHEDULED"
        mock_task.delay.assert_called_once_with(str(run.id))
    finally:
        db.query(User).filter(User.id == user.id).delete()
        db.commit()
        db.rollback()
        db.close()


def test_list_report_runs_scoped_to_report():
    db = SessionLocal()
    try:
        user = _seed_user(db)
        report = report_service.create_report(db, user.id, _base_payload())
        db.add(ReportRun(report_id=report.id, status="SUCCEEDED", recipient_emails=["me@example.com"]))
        db.commit()
        runs = report_service.list_report_runs(db, user.id, str(report.id))
        assert len(runs) == 1
    finally:
        db.query(User).filter(User.id == user.id).delete()
        db.commit()
        db.rollback()
        db.close()
