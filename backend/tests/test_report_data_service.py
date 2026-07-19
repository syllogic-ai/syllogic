"""Tests for report data aggregation.

Run with:
    cd backend && .venv/bin/pytest tests/test_report_data_service.py -v
"""
from __future__ import annotations

import base64
import os
import sys
import uuid
from datetime import datetime, timedelta
from decimal import Decimal

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _set_test_env() -> None:
    key = base64.urlsafe_b64encode(b"p" * 32).decode("utf-8").rstrip("=")
    os.environ["DATA_ENCRYPTION_KEY_CURRENT"] = key
    os.environ["DATA_ENCRYPTION_KEY_ID"] = "k-test-report-data"
    os.environ.pop("DATA_ENCRYPTION_KEY_PREVIOUS", None)


_set_test_env()

from app.database import SessionLocal  # noqa: E402
from app.models import Account, Report, Transaction, User  # noqa: E402
from app.services.report_data_service import build_report_payload  # noqa: E402


def _seed_user_with_account_and_transactions(db):
    user = User(id=f"test-user-{uuid.uuid4()}", email=f"{uuid.uuid4()}@example.com", name="Test User")
    db.add(user)
    db.flush()

    account = Account(
        user_id=user.id,
        name="Checking",
        account_type="checking",
        currency="EUR",
        functional_balance=Decimal("1234.56"),
    )
    db.add(account)
    db.flush()

    now = datetime.utcnow()
    for i, (amount, ttype, desc) in enumerate([
        (Decimal("-50.00"), "debit", "Groceries"),
        (Decimal("-20.00"), "debit", "Coffee"),
        (Decimal("2000.00"), "credit", "Salary"),
    ]):
        db.add(Transaction(
            user_id=user.id,
            account_id=account.id,
            transaction_type=ttype,
            amount=amount,
            currency="EUR",
            description=desc,
            booked_at=now - timedelta(days=i),
        ))
    db.flush()
    return user, account


def test_build_report_payload_recent_all():
    db = SessionLocal()
    try:
        user, account = _seed_user_with_account_and_transactions(db)
        report = Report(
            user_id=user.id,
            name="Test report",
            account_ids=[str(account.id)],
            transaction_mode="RECENT",
            transaction_count=2,
            transaction_direction="ALL",
            frequency="DAILY",
        )
        db.add(report)
        db.flush()

        payload = build_report_payload(db, report)
        assert payload["accounts"][0]["balance"] == "1234.56"
        assert payload["transactions"]["mode_label"] == "Last 2 transactions"
        assert len(payload["transactions"]["items"]) == 2
    finally:
        db.rollback()
        db.close()


def test_build_report_payload_top_n_all_orders_by_absolute_magnitude():
    db = SessionLocal()
    try:
        user, account = _seed_user_with_account_and_transactions(db)
        now = datetime.utcnow()
        # Mixed large debit/credit on top of the -50/-20/+2000 seeded above.
        db.add(Transaction(
            user_id=user.id,
            account_id=account.id,
            transaction_type="debit",
            amount=Decimal("-5000.00"),
            currency="EUR",
            description="Big rent",
            booked_at=now - timedelta(days=5),
        ))
        db.flush()

        report = Report(
            user_id=user.id,
            name="Test report",
            account_ids=[str(account.id)],
            transaction_mode="TOP_N",
            transaction_count=2,
            transaction_direction="ALL",
            frequency="DAILY",
        )
        db.add(report)
        db.flush()

        payload = build_report_payload(db, report)
        items = payload["transactions"]["items"]
        assert len(items) == 2
        assert items[0]["description"] == "Big rent"  # abs(5000) largest
        assert items[1]["description"] == "Salary"  # abs(2000) next largest
    finally:
        db.rollback()
        db.close()


def test_build_report_payload_functional_balance_uses_user_functional_currency():
    db = SessionLocal()
    try:
        user, account = _seed_user_with_account_and_transactions(db)
        user.functional_currency = "GBP"
        db.flush()

        report = Report(
            user_id=user.id,
            name="Test report",
            account_ids=[str(account.id)],
            transaction_mode="RECENT",
            transaction_count=2,
            transaction_direction="ALL",
            frequency="DAILY",
        )
        db.add(report)
        db.flush()

        payload = build_report_payload(db, report)
        assert payload["accounts"][0]["balance"] == "1234.56"
        assert payload["accounts"][0]["currency"] == "GBP"
    finally:
        db.rollback()
        db.close()


def test_build_report_payload_top_n_expenses():
    db = SessionLocal()
    try:
        user, account = _seed_user_with_account_and_transactions(db)
        report = Report(
            user_id=user.id,
            name="Test report",
            account_ids=[str(account.id)],
            transaction_mode="TOP_N",
            transaction_count=1,
            transaction_direction="EXPENSE",
            frequency="DAILY",
        )
        db.add(report)
        db.flush()

        payload = build_report_payload(db, report)
        assert payload["transactions"]["mode_label"] == "Top 1 expenses"
        items = payload["transactions"]["items"]
        assert len(items) == 1
        assert items[0]["description"] == "Groceries"  # largest debit amount
        assert items[0]["direction"] == "out"
    finally:
        db.rollback()
        db.close()
