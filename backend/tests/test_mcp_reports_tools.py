"""Tests for the report MCP tools module.

Run with:
    cd backend && .venv/bin/pytest tests/test_mcp_reports_tools.py -v
"""
from __future__ import annotations

import base64
import os
import sys
import uuid
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _set_test_env() -> None:
    key = base64.urlsafe_b64encode(b"p" * 32).decode("utf-8").rstrip("=")
    os.environ["DATA_ENCRYPTION_KEY_CURRENT"] = key
    os.environ["DATA_ENCRYPTION_KEY_ID"] = "k-test-mcp-reports"
    os.environ.pop("DATA_ENCRYPTION_KEY_PREVIOUS", None)


_set_test_env()

from app.database import SessionLocal  # noqa: E402
from app.models import User  # noqa: E402
from app.mcp.tools import reports as report_tools  # noqa: E402


def _seed_user(db) -> User:
    user = User(id=f"test-user-{uuid.uuid4()}", email=f"{uuid.uuid4()}@example.com", name="Test User")
    db.add(user)
    db.commit()
    return user


def _cleanup(db, user_id: str) -> None:
    db.rollback()
    db.query(User).filter(User.id == user_id).delete()
    db.commit()


def test_create_report_success_shape():
    db = SessionLocal()
    user = _seed_user(db)
    try:
        result = report_tools.create_report(
            user_id=user.id, name="Weekly summary", frequency="WEEKLY",
            send_day_of_week=0, recipient_emails=["me@example.com"],
        )
        assert result["success"] is True
        assert result["report"]["name"] == "Weekly summary"
        assert result["report"]["frequency"] == "WEEKLY"
    finally:
        _cleanup(db, user.id)
        db.close()


def test_create_report_validation_error_shape():
    db = SessionLocal()
    user = _seed_user(db)
    try:
        result = report_tools.create_report(
            user_id=user.id, name="Bad", frequency="YEARLY", recipient_emails=["me@example.com"],
        )
        assert result["success"] is False
        assert "error" in result
    finally:
        _cleanup(db, user.id)
        db.close()


def test_list_reports_returns_dicts():
    db = SessionLocal()
    user = _seed_user(db)
    try:
        report_tools.create_report(
            user_id=user.id, name="R1", frequency="DAILY", recipient_emails=["me@example.com"],
        )
        out = report_tools.list_reports(user_id=user.id)
        assert isinstance(out, list)
        assert len(out) == 1
        assert out[0]["name"] == "R1"
    finally:
        _cleanup(db, user.id)
        db.close()


def test_get_report_not_found_returns_none():
    db = SessionLocal()
    user = _seed_user(db)
    try:
        out = report_tools.get_report(user_id=user.id, report_id=str(uuid.uuid4()))
        assert out is None
    finally:
        _cleanup(db, user.id)
        db.close()


def test_update_report_success_and_error_shapes():
    db = SessionLocal()
    user = _seed_user(db)
    try:
        created = report_tools.create_report(
            user_id=user.id, name="R1", frequency="DAILY", recipient_emails=["me@example.com"],
        )
        report_id = created["report"]["id"]

        ok = report_tools.update_report(user_id=user.id, report_id=report_id, is_active=False)
        assert ok["success"] is True
        assert ok["report"]["is_active"] is False

        bad = report_tools.update_report(user_id=user.id, report_id=str(uuid.uuid4()), is_active=False)
        assert bad["success"] is False
    finally:
        _cleanup(db, user.id)
        db.close()


def test_delete_report_success_and_not_found():
    db = SessionLocal()
    user = _seed_user(db)
    try:
        created = report_tools.create_report(
            user_id=user.id, name="R1", frequency="DAILY", recipient_emails=["me@example.com"],
        )
        report_id = created["report"]["id"]

        ok = report_tools.delete_report(user_id=user.id, report_id=report_id)
        assert ok["success"] is True

        again = report_tools.delete_report(user_id=user.id, report_id=report_id)
        assert again["success"] is False
    finally:
        _cleanup(db, user.id)
        db.close()


def test_send_test_report_enqueues():
    db = SessionLocal()
    user = _seed_user(db)
    try:
        created = report_tools.create_report(
            user_id=user.id, name="R1", frequency="DAILY", recipient_emails=["me@example.com"],
        )
        report_id = created["report"]["id"]
        with patch("app.services.report_service.send_report_run") as mock_task:
            result = report_tools.send_test_report(user_id=user.id, report_id=report_id)
        assert result["success"] is True
        assert result["run"]["is_test"] is True
        mock_task.delay.assert_called_once()
    finally:
        _cleanup(db, user.id)
        db.close()


def test_list_report_runs():
    db = SessionLocal()
    user = _seed_user(db)
    try:
        created = report_tools.create_report(
            user_id=user.id, name="R1", frequency="DAILY", recipient_emails=["me@example.com"],
        )
        report_id = created["report"]["id"]
        with patch("app.services.report_service.send_report_run"):
            report_tools.send_test_report(user_id=user.id, report_id=report_id)
        runs = report_tools.list_report_runs(user_id=user.id, report_id=report_id)
        assert len(runs) == 1
        assert runs[0]["is_test"] is True
    finally:
        _cleanup(db, user.id)
        db.close()
