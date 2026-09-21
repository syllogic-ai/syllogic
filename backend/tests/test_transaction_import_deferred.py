"""Tests for the deferred (worker-backed) transaction import path.

`defer_processing=True` must commit the rows inline and hand every expensive
step -- LLM categorization, FX fetches, balance/timeseries recalculation,
subscription detection -- to the post-import Celery pipeline.
"""

import os
import sys
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from fastapi import HTTPException

from app.database import SessionLocal, Base, engine
from app.models import Account, Transaction
from app.db_helpers import get_or_create_system_user, set_request_user_id, clear_request_user_id
from app.routes.transaction_import import (
    TransactionImportItem,
    TransactionImportRequest,
    import_transactions,
)


@pytest.fixture
def user_id():
    db = SessionLocal()
    try:
        Base.metadata.create_all(bind=engine)
        user = get_or_create_system_user(db)
        uid = str(user.id)
    finally:
        db.close()

    token = set_request_user_id(uid)
    try:
        yield uid
    finally:
        clear_request_user_id(token)


@pytest.fixture
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def _make_account(db, user_id: str) -> Account:
    account = Account(
        user_id=user_id,
        name=f"Deferred Test Account {uuid.uuid4().hex[:8]}",
        account_type="checking",
        institution="Test Bank",
        currency="EUR",
        balance_available=Decimal("1000.00"),
        starting_balance=Decimal("1000.00"),
        functional_balance=Decimal("1000.00"),
    )
    db.add(account)
    db.commit()
    db.refresh(account)
    return account


def _request(account: Account, **overrides) -> TransactionImportRequest:
    payload = {
        "transactions": [
            TransactionImportItem(
                account_id=account.id,
                amount=Decimal("25.50"),
                description=f"TESCO {uuid.uuid4().hex[:8]}",
                booked_at=datetime.now(timezone.utc),
                transaction_type="debit",
            )
        ],
        "defer_processing": True,
    }
    payload.update(overrides)
    return TransactionImportRequest(**payload)


def test_deferred_import_commits_row_and_queues_pipeline(db, user_id):
    account = _make_account(db, user_id)

    fake_result = MagicMock()
    fake_result.id = "task-123"

    with (
        patch(
            "tasks.post_import_pipeline.post_import_pipeline.delay", return_value=fake_result
        ) as delay,
        patch("app.routes.categories.categorize_transactions_batch") as categorize,
        patch("app.routes.transaction_import.AccountBalanceService") as balance_service,
        patch("app.routes.transaction_import.ExchangeRateService") as fx_service,
    ):
        response = import_transactions(_request(account), db=db)

    assert response.success is True
    assert response.transactions_inserted == 1
    assert response.deferred is True
    assert response.task_id == "task-123"

    # None of the slow work happened on the request thread.
    categorize.assert_not_called()
    balance_service.assert_not_called()
    fx_service.assert_not_called()

    # The pipeline got the committed ids to finish the job.
    delay.assert_called_once()
    kwargs = delay.call_args.kwargs
    assert kwargs["user_id"] == user_id
    assert kwargs["account_ids"] == [str(account.id)]
    assert kwargs["transaction_ids"] == response.transaction_ids

    stored = db.query(Transaction).filter(Transaction.id == response.transaction_ids[0]).one()
    assert stored.amount == Decimal("-25.50")  # debit normalized to negative


def test_deferred_import_sets_functional_amount_for_matching_currency(db, user_id):
    """Same-currency rows are converted inline (no network) so the new row
    renders with a correct functional amount before the worker runs."""
    account = _make_account(db, user_id)
    fake_result = MagicMock()
    fake_result.id = "task-456"

    with patch("tasks.post_import_pipeline.post_import_pipeline.delay", return_value=fake_result):
        response = import_transactions(_request(account), db=db)

    stored = db.query(Transaction).filter(Transaction.id == response.transaction_ids[0]).one()
    assert stored.functional_amount == stored.amount


def test_deferred_import_falls_back_to_inline_pipeline_when_broker_is_down(db, user_id):
    """The rows are already committed when the enqueue fails, so the pipeline
    has to run inline rather than leaving them unprocessed forever."""
    account = _make_account(db, user_id)

    with (
        patch(
            "tasks.post_import_pipeline.post_import_pipeline.delay",
            side_effect=OSError("broker unreachable"),
        ),
        patch("tasks.post_import_pipeline._run_post_import_pipeline") as run_inline,
    ):
        response = import_transactions(_request(account), db=db)

    assert response.success is True
    assert response.deferred is False
    assert response.task_id is None
    run_inline.assert_called_once()
    assert run_inline.call_args.kwargs["transaction_ids"] == response.transaction_ids


def test_deferred_import_rejects_daily_balances(db, user_id):
    account = _make_account(db, user_id)
    request = _request(
        account,
        # DailyBalanceImport.date is an ISO string (that is what the CSV
        # importer sends); a date object fails validation before the route
        # ever gets to reject the combination under test.
        daily_balances=[
            {
                "date": datetime.now(timezone.utc).date().isoformat(),
                "balance": Decimal("100.00"),
            }
        ],
    )

    with pytest.raises(HTTPException) as exc:
        import_transactions(request, db=db)

    assert exc.value.status_code == 400
    assert "daily_balances" in exc.value.detail
