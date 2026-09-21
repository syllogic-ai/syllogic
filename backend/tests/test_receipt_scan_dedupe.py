"""Tests for reconciling bank rows against the receipt splits that cover
them (Phase 7 of the receipt-ingestion rework). See
docs/specs/receipt-ingestion-implementation.md 7.1.

The inversion against `test_recurring_transaction_dedupe.py` is the thing
under test: there the placeholder loses, here the *bank* row does, because
the splits are the side carrying the categories.

Run with:
    cd backend && .venv/bin/pytest tests/test_receipt_scan_dedupe.py -v
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import func

from app.models import (
    Account,
    Category,
    ReceiptLineItem,
    ReceiptScan,
    Transaction,
    User,
)
from app.services.receipt_scan_dedupe import supersede_receipt_duplicates

RECEIPT_DATE = datetime(2026, 4, 12)


@pytest.fixture
def user(db_session):
    user = User(
        id="u-receipt-dedupe",
        email="receipt-dedupe@example.com",
        functional_currency="EUR",
    )
    db_session.add(user)
    db_session.commit()
    return user


@pytest.fixture
def account(db_session, user):
    account = Account(
        id=uuid4(),
        user_id=user.id,
        name="Card",
        account_type="checking",
        currency="EUR",
        is_active=True,
    )
    db_session.add(account)
    db_session.commit()
    return account


@pytest.fixture
def categories(db_session, user):
    groceries = Category(id=uuid4(), user_id=user.id, name="Groceries", category_type="expense")
    treats = Category(id=uuid4(), user_id=user.id, name="Treats", category_type="expense")
    db_session.add_all([groceries, treats])
    db_session.commit()
    return groceries, treats


def _book_receipt(
    db_session,
    account,
    categories,
    *,
    merchant="Rimi",
    amounts=(Decimal("21.40"), Decimal("5.25")),
    booked_at=RECEIPT_DATE,
) -> ReceiptScan:
    """Book a receipt the way the confirm endpoint does: one transaction per
    category group, each `ReceiptLineItem` pointing at the row it landed in.
    That back-link is what marks a transaction as a split, so tests must set
    it rather than rely on `receipt_scan_id` alone."""
    scan = ReceiptScan(
        id=uuid4(),
        user_id=account.user_id,
        account_id=account.id,
        status="completed",
        merchant_name=merchant,
        printed_total=sum(amounts, Decimal("0")),
        receipt_date=booked_at,
        currency="EUR",
    )
    db_session.add(scan)
    db_session.commit()

    for position, (category, amount) in enumerate(zip(categories, amounts), start=1):
        split = Transaction(
            id=uuid4(),
            user_id=account.user_id,
            account_id=account.id,
            transaction_type="debit",
            amount=amount,
            currency="EUR",
            description=merchant,
            booked_at=booked_at,
            category_id=category.id,
            receipt_scan_id=scan.id,
            include_in_analytics=True,
        )
        db_session.add(split)
        db_session.flush()
        db_session.add(
            ReceiptLineItem(
                id=uuid4(),
                receipt_scan_id=scan.id,
                line_ref=f"L{position}",
                position=position,
                name=f"Line {position}",
                net_amount=amount,
                kind="item",
                category_id=category.id,
                booked_transaction_id=split.id,
            )
        )
    db_session.commit()
    return scan


def _add_bank_row(
    db_session,
    account,
    *,
    amount=Decimal("-26.65"),
    merchant="RIMI LATVIA SIA",
    booked_at=datetime(2026, 4, 14),
) -> Transaction:
    txn = Transaction(
        id=uuid4(),
        user_id=account.user_id,
        account_id=account.id,
        transaction_type="debit",
        amount=amount,
        currency="EUR",
        description=merchant,
        merchant=merchant,
        booked_at=booked_at,
        external_id=f"bank-{uuid4().hex[:8]}",
        include_in_analytics=True,
    )
    db_session.add(txn)
    db_session.commit()
    return txn


def _splits_of(db_session, scan) -> list[Transaction]:
    return (
        db_session.query(Transaction)
        .join(ReceiptLineItem, ReceiptLineItem.booked_transaction_id == Transaction.id)
        .filter(ReceiptLineItem.receipt_scan_id == scan.id)
        .order_by(Transaction.amount)
        .all()
    )


def test_bank_row_within_tolerance_drops_out_of_analytics(db_session, account, categories):
    """The splits keep their analytics flag; the charge that paid for them loses it."""
    scan = _book_receipt(db_session, account, categories)
    bank_row = _add_bank_row(db_session, account)

    outcome = supersede_receipt_duplicates(db_session, account.user_id)

    assert outcome["demoted"] == 1
    assert outcome["account_ids"] == [str(account.id)]

    db_session.refresh(bank_row)
    assert bank_row.include_in_analytics is False
    assert bank_row.receipt_scan_id == scan.id
    # Kept, not deleted -- the balance is computed from it.
    assert db_session.get(Transaction, bank_row.id) is not None

    for split in _splits_of(db_session, scan):
        assert split.include_in_analytics is True


def test_analytics_over_the_window_counts_the_amount_once(db_session, account, categories):
    scan = _book_receipt(db_session, account, categories)
    bank_row = _add_bank_row(db_session, account)

    supersede_receipt_duplicates(db_session, account.user_id)

    analytics_total = (
        db_session.query(func.coalesce(func.sum(func.abs(Transaction.amount)), 0))
        .filter(
            Transaction.user_id == account.user_id,
            Transaction.include_in_analytics.is_(True),
        )
        .scalar()
    )
    assert Decimal(analytics_total) == Decimal("26.65")

    # The balance side is untouched: both the splits and the bank row are
    # still there, which is exactly why analytics needs the flag.
    ledger_total = (
        db_session.query(func.sum(func.abs(Transaction.amount)))
        .filter(Transaction.user_id == account.user_id)
        .scalar()
    )
    assert Decimal(ledger_total) == Decimal("53.30")
    assert db_session.get(Transaction, bank_row.id).receipt_scan_id == scan.id


def test_row_outside_the_match_window_changes_nothing(db_session, account, categories):
    """8 days out, one past `MATCH_WINDOW_DAYS`. Same merchant, same amount."""
    _book_receipt(db_session, account, categories)
    bank_row = _add_bank_row(db_session, account, booked_at=datetime(2026, 4, 20))

    outcome = supersede_receipt_duplicates(db_session, account.user_id)

    assert outcome == {"demoted": 0, "account_ids": []}
    db_session.refresh(bank_row)
    assert bank_row.include_in_analytics is True
    assert bank_row.receipt_scan_id is None


def test_amount_matches_but_merchant_does_not_changes_nothing(db_session, account, categories):
    """An amount inside tolerance is not on its own evidence of a duplicate."""
    _book_receipt(db_session, account, categories)
    bank_row = _add_bank_row(db_session, account, merchant="MAXIMA XX")

    outcome = supersede_receipt_duplicates(db_session, account.user_id)

    assert outcome == {"demoted": 0, "account_ids": []}
    db_session.refresh(bank_row)
    assert bank_row.include_in_analytics is True
    assert bank_row.receipt_scan_id is None


def test_amount_outside_tolerance_changes_nothing(db_session, account, categories):
    """26.65 against 20.00 is 25% off, past AMOUNT_TOLERANCE_PERCENT."""
    _book_receipt(db_session, account, categories)
    bank_row = _add_bank_row(db_session, account, amount=Decimal("-20.00"))

    outcome = supersede_receipt_duplicates(db_session, account.user_id)

    assert outcome["demoted"] == 0
    db_session.refresh(bank_row)
    assert bank_row.include_in_analytics is True


def test_one_receipt_covers_only_one_bank_row(db_session, account, categories):
    """Two identical charges in the window, one receipt: the second stays in."""
    _book_receipt(db_session, account, categories)
    first = _add_bank_row(db_session, account, booked_at=datetime(2026, 4, 13))
    second = _add_bank_row(db_session, account, booked_at=datetime(2026, 4, 14))

    outcome = supersede_receipt_duplicates(db_session, account.user_id)

    assert outcome["demoted"] == 1
    db_session.refresh(first)
    db_session.refresh(second)
    assert first.include_in_analytics is False
    assert second.include_in_analytics is True


def test_rerunning_the_sweep_is_a_no_op(db_session, account, categories):
    """Demotion writes `receipt_scan_id` onto the bank row; a second pass must
    not then read that row back as a split, nor claim another charge."""
    _book_receipt(db_session, account, categories)
    _add_bank_row(db_session, account)

    assert supersede_receipt_duplicates(db_session, account.user_id)["demoted"] == 1
    assert supersede_receipt_duplicates(db_session, account.user_id)["demoted"] == 0

    later = _add_bank_row(db_session, account, booked_at=datetime(2026, 4, 15))
    assert supersede_receipt_duplicates(db_session, account.user_id)["demoted"] == 0
    db_session.refresh(later)
    assert later.include_in_analytics is True


def test_transaction_ids_narrows_the_sweep(db_session, account, categories):
    """The pipeline passes the import's own ids; rows outside it are left alone."""
    _book_receipt(db_session, account, categories)
    bank_row = _add_bank_row(db_session, account)

    assert supersede_receipt_duplicates(db_session, account.user_id, transaction_ids=[]) == {
        "demoted": 0,
        "account_ids": [],
    }
    outcome = supersede_receipt_duplicates(
        db_session, account.user_id, transaction_ids=[str(uuid4())]
    )
    assert outcome["demoted"] == 0

    outcome = supersede_receipt_duplicates(
        db_session, account.user_id, transaction_ids=[str(bank_row.id)]
    )
    assert outcome["demoted"] == 1
