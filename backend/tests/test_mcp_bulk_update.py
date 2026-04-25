"""Tests for SYL-33: dry_run and rich response on bulk_update_transaction_categories."""
from datetime import datetime
from decimal import Decimal

import pytest

from app.mcp.tools import transactions as tx_tools
from app.models import Transaction, Account, Category, User


@pytest.fixture
def bulk_data(db_session):
    user = User(id="bulk-user", email="bulk@test.com")
    other_user = User(id="other-user", email="other@test.com")
    db_session.add_all([user, other_user])
    acc = Account(user_id=user.id, name="A", account_type="checking")
    other_acc = Account(user_id=other_user.id, name="B", account_type="checking")
    db_session.add_all([acc, other_acc])
    db_session.flush()
    target = Category(user_id=user.id, name="Groceries", category_type="expense")
    other_cat = Category(user_id=user.id, name="Other", category_type="expense")
    db_session.add_all([target, other_cat])
    db_session.flush()
    # 3 to update (t1, t2, t3), 1 already in target (t4), 1 belongs to other user (t5)
    t1 = Transaction(user_id=user.id, account_id=acc.id, amount=Decimal("-10"),
                     currency="EUR", description="D1", merchant="M1",
                     category_id=other_cat.id, booked_at=datetime(2026, 4, 1),
                     transaction_type="debit")
    t2 = Transaction(user_id=user.id, account_id=acc.id, amount=Decimal("-20"),
                     currency="EUR", description="D2", merchant="M2",
                     category_id=other_cat.id, booked_at=datetime(2026, 4, 2),
                     transaction_type="debit")
    t3 = Transaction(user_id=user.id, account_id=acc.id, amount=Decimal("-30"),
                     currency="EUR", description="D3", merchant="M3",
                     category_id=None, booked_at=datetime(2026, 4, 3),
                     transaction_type="debit")
    t4 = Transaction(user_id=user.id, account_id=acc.id, amount=Decimal("-40"),
                     currency="EUR", description="D4", merchant="M4",
                     category_id=target.id, booked_at=datetime(2026, 4, 4),
                     transaction_type="debit")
    t5 = Transaction(user_id=other_user.id, account_id=other_acc.id, amount=Decimal("-50"),
                     currency="EUR", description="D5", merchant="M5",
                     category_id=other_cat.id, booked_at=datetime(2026, 4, 5),
                     transaction_type="debit")
    db_session.add_all([t1, t2, t3, t4, t5])
    db_session.commit()
    try:
        yield user, target, [t1, t2, t3, t4, t5]
    finally:
        # Clean up committed data in FK order so tests are idempotent across runs.
        db_session.query(Transaction).filter(Transaction.user_id == user.id).delete()
        db_session.query(Transaction).filter(Transaction.user_id == other_user.id).delete()
        db_session.query(Category).filter(Category.user_id == user.id).delete()
        db_session.query(Account).filter(Account.user_id == user.id).delete()
        db_session.query(Account).filter(Account.user_id == other_user.id).delete()
        db_session.query(User).filter(User.id.in_([user.id, other_user.id])).delete()
        db_session.commit()


def test_bulk_update_dry_run_no_mutation(bulk_data, db_session):
    user, target, txns = bulk_data
    ids = [str(t.id) for t in txns[:3]]
    result = tx_tools.bulk_update_transaction_categories(
        user_id=user.id, category_id=str(target.id),
        transaction_ids=ids, dry_run=True,
    )
    assert result["success"] is True
    assert result["would_update_count"] == 3
    assert result["requested_count"] == 3
    assert len(result["sample_changes"]) == 3
    assert result["sample_changes"][0]["description"] in ("D1", "D2", "D3")
    # Verify DB untouched
    for t in txns[:3]:
        db_session.refresh(t)
        assert t.category_id != target.id


def test_bulk_update_rich_response_categorizes_ids(bulk_data):
    user, target, txns = bulk_data
    bogus = "00000000-0000-0000-0000-000000000000"
    ids = [str(txns[0].id), str(txns[3].id), str(txns[4].id), bogus, "not-a-uuid"]
    result = tx_tools.bulk_update_transaction_categories(
        user_id=user.id, category_id=str(target.id), transaction_ids=ids,
    )
    assert result["success"] is True
    assert result["updated_count"] == 1  # only txns[0] is actually changed
    assert result["requested_count"] == 5
    assert result["invalid_ids"] == ["not-a-uuid"]
    assert bogus in result["not_found_ids"] or str(txns[4].id) in result["not_found_ids"]
    assert str(txns[3].id) in result["skipped_already_in_category_ids"]


def test_bulk_update_hard_cap():
    result = tx_tools.bulk_update_transaction_categories(
        user_id="x", category_id="00000000-0000-0000-0000-000000000001",
        transaction_ids=[f"id-{i}" for i in range(2001)],
    )
    assert result["success"] is False
    assert "2000" in result["error"]


def test_bulk_update_dry_run_matches_real_run(bulk_data):
    user, target, txns = bulk_data
    ids = [str(t.id) for t in txns[:3]]

    preview = tx_tools.bulk_update_transaction_categories(
        user_id=user.id, category_id=str(target.id),
        transaction_ids=ids, dry_run=True,
    )
    real = tx_tools.bulk_update_transaction_categories(
        user_id=user.id, category_id=str(target.id), transaction_ids=ids,
    )

    assert preview["would_update_count"] == real["updated_count"]
    preview_ids = {s["id"] for s in preview["sample_changes"]}
    real_ids = {s["id"] for s in real["sample_changes"]}
    assert preview_ids == real_ids
