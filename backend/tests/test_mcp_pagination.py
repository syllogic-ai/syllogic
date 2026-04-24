"""Tests for cursor pagination, sort_by, and account_id filter on MCP search/list tools."""
from datetime import datetime, timedelta
from decimal import Decimal

import pytest

from app.mcp.tools import transactions as tx_tools
from app.models import Transaction, Account, Category, User


@pytest.fixture
def seeded_user(db_session):
    """Create a user with 2 accounts and 10 transactions spanning 10 days."""
    user = User(id="test-user-1", email="test@test.com")
    db_session.add(user)
    acc1 = Account(user_id=user.id, name="ABN", account_type="checking")
    acc2 = Account(user_id=user.id, name="Revolut", account_type="checking")
    db_session.add_all([acc1, acc2])
    db_session.flush()
    cat = Category(user_id=user.id, name="Food", category_type="expense")
    db_session.add(cat)
    db_session.flush()
    base = datetime(2026, 4, 1)
    for i in range(10):
        db_session.add(Transaction(
            user_id=user.id,
            account_id=acc1.id if i % 2 == 0 else acc2.id,
            amount=Decimal(f"-{(i + 1) * 10}"),
            currency="EUR",
            description=f"Purchase {i}",
            merchant=f"Merchant {i}",
            category_id=cat.id if i < 5 else None,
            booked_at=base + timedelta(days=i),
            transaction_type="debit",
        ))
    db_session.commit()
    try:
        yield user, acc1, acc2, cat
    finally:
        # Clean up committed data so tests are idempotent.
        db_session.query(Transaction).filter(Transaction.user_id == user.id).delete()
        db_session.query(Category).filter(Category.user_id == user.id).delete()
        db_session.query(Account).filter(Account.user_id == user.id).delete()
        db_session.query(User).filter(User.id == user.id).delete()
        db_session.commit()


def test_list_transactions_sort_by_amount_desc(seeded_user):
    user, _, _, _ = seeded_user
    result = tx_tools.list_transactions(
        user_id=user.id, sort_by="amount_desc", limit=3
    )
    # amount_desc over negative expenses: -10 is largest, -100 smallest
    amounts = [r["amount"] for r in result["transactions"]]
    assert amounts == sorted(amounts, reverse=True)
    assert len(result["transactions"]) == 3


@pytest.fixture
def user_with_tied_booked_at(db_session):
    """Seed a user whose transactions all share the same booked_at timestamp.

    Exercises the tie-breaker in _paginate_query: pagination must visit every
    row exactly once when the primary sort column is constant across rows.
    """
    user = User(id="test-user-ties", email="ties@test.com")
    db_session.add(user)
    acc = Account(user_id=user.id, name="ABN", account_type="checking")
    db_session.add(acc)
    db_session.flush()
    same_ts = datetime(2026, 4, 15, 12, 0, 0)
    for i in range(7):
        db_session.add(Transaction(
            user_id=user.id,
            account_id=acc.id,
            amount=Decimal(f"-{(i + 1) * 5}"),
            currency="EUR",
            description=f"Tied purchase {i}",
            merchant=f"Merchant {i}",
            booked_at=same_ts,
            transaction_type="debit",
        ))
    db_session.commit()
    try:
        yield user
    finally:
        db_session.query(Transaction).filter(Transaction.user_id == user.id).delete()
        db_session.query(Account).filter(Account.user_id == user.id).delete()
        db_session.query(User).filter(User.id == user.id).delete()
        db_session.commit()


def test_booked_at_asc_cursor_pagination_with_ties(user_with_tied_booked_at):
    """Ascending-sort cursor walk must not skip or duplicate rows on ties.

    Regression test: the id tie-breaker must match the primary sort
    direction. If the secondary order_by is id.desc() but the cursor
    filter uses `id > last_id` for ascending sorts, rows tied on
    booked_at silently disappear between pages.
    """
    user = user_with_tied_booked_at
    collected_ids: list[str] = []
    cursor = None
    # 7 rows, page size 2 -> need at least 4 iterations; cap to avoid looping forever.
    for _ in range(10):
        result = tx_tools.list_transactions(
            user_id=user.id,
            sort_by="booked_at_asc",
            limit=2,
            cursor=cursor,
        )
        page_ids = [t["id"] for t in result["transactions"]]
        collected_ids.extend(page_ids)
        cursor = result["next_cursor"]
        if cursor is None:
            break

    assert cursor is None, "pagination did not terminate"
    # No duplicates.
    assert len(collected_ids) == len(set(collected_ids)), (
        f"cursor walk produced duplicates: {collected_ids}"
    )
    # No gaps - every seeded row is present.
    assert len(collected_ids) == 7, (
        f"cursor walk skipped rows; got {len(collected_ids)}/7: {collected_ids}"
    )


def test_list_transactions_cursor_round_trip(seeded_user):
    user, _, _, _ = seeded_user
    page1 = tx_tools.list_transactions(user_id=user.id, limit=4, sort_by="booked_at_desc")
    assert len(page1["transactions"]) == 4
    assert page1["next_cursor"] is not None

    page2 = tx_tools.list_transactions(
        user_id=user.id, limit=4, sort_by="booked_at_desc", cursor=page1["next_cursor"]
    )
    assert len(page2["transactions"]) == 4

    ids_page1 = {t["id"] for t in page1["transactions"]}
    ids_page2 = {t["id"] for t in page2["transactions"]}
    assert ids_page1.isdisjoint(ids_page2), "Pages must not overlap"

    page3 = tx_tools.list_transactions(
        user_id=user.id, limit=4, sort_by="booked_at_desc", cursor=page2["next_cursor"]
    )
    # Total 10 rows, 4+4+2 = 10, final page returns fewer than limit → no next_cursor
    assert len(page3["transactions"]) == 2
    assert page3["next_cursor"] is None
