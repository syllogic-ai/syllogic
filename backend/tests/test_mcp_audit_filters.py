"""Tests for SYL-31 audit filters."""
from datetime import datetime
from decimal import Decimal

import pytest

from app.mcp.tools import transactions as tx_tools
from app.mcp.tools import analytics as an_tools
from app.models import Transaction, Account, Category, User


@pytest.fixture
def audit_data(db_session):
    user = User(id="audit-user", email="audit@test.com")
    db_session.add(user)
    acc = Account(user_id=user.id, name="A", account_type="checking")
    db_session.add(acc)
    db_session.flush()
    expense_cat = Category(user_id=user.id, name="Food", category_type="expense")
    income_cat = Category(user_id=user.id, name="Salary", category_type="income")
    db_session.add_all([expense_cat, income_cat])
    db_session.flush()
    # 3 uncategorized, 2 expense-categorized, 1 income-categorized
    specs = [
        (None, -10, "debit"), (None, -20, "debit"), (None, -30, "debit"),
        (expense_cat.id, -40, "debit"), (expense_cat.id, -50, "debit"),
        (income_cat.id, 100, "credit"),
    ]
    for i, (cid, amt, ttype) in enumerate(specs):
        db_session.add(Transaction(
            user_id=user.id,
            account_id=acc.id,
            amount=Decimal(str(amt)),
            currency="EUR",
            description=f"Txn {i}",
            merchant=f"M{i}",
            category_id=cid,
            booked_at=datetime(2026, 4, 1 + i),
            transaction_type=ttype,
        ))
    db_session.commit()
    try:
        yield user, acc, expense_cat, income_cat
    finally:
        # Clean up committed data so tests are idempotent across runs.
        db_session.query(Transaction).filter(Transaction.user_id == user.id).delete()
        db_session.query(Category).filter(Category.user_id == user.id).delete()
        db_session.query(Account).filter(Account.user_id == user.id).delete()
        db_session.query(User).filter(User.id == user.id).delete()
        db_session.commit()


def test_list_transactions_uncategorized(audit_data):
    user, *_ = audit_data
    result = tx_tools.list_transactions(user_id=user.id, uncategorized=True, limit=50)
    assert len(result["transactions"]) == 3
    assert all(t["category_id"] is None for t in result["transactions"])


def test_list_transactions_category_type(audit_data):
    user, *_ = audit_data
    result = tx_tools.list_transactions(user_id=user.id, category_type="expense", limit=50)
    assert len(result["transactions"]) == 2  # Only categorized-as-expense
    result_income = tx_tools.list_transactions(user_id=user.id, category_type="income", limit=50)
    assert len(result_income["transactions"]) == 1


def test_spending_by_category_include_uncategorized(audit_data):
    user, *_ = audit_data
    # Without flag: only categorized expense rows
    baseline = an_tools.get_spending_by_category(user_id=user.id)
    assert all(r["category_id"] is not None for r in baseline)

    enriched = an_tools.get_spending_by_category(user_id=user.id, include_uncategorized=True)
    names = [r["category_name"] for r in enriched]
    assert "Uncategorized" in names
    uncat = next(r for r in enriched if r["category_name"] == "Uncategorized")
    assert uncat["total"] == 60  # 10 + 20 + 30
    assert uncat["count"] == 3
    assert "merchant_count" in uncat
    assert uncat["merchant_count"] == 3


def test_top_merchants_category_filter(audit_data):
    user, _, expense_cat, _ = audit_data
    result = an_tools.get_top_merchants(user_id=user.id, category_id=str(expense_cat.id))
    # Only the 2 expense-categorized txns (M3, M4)
    merchants = {r["merchant"] for r in result}
    assert merchants == {"M3", "M4"}


def test_top_merchants_uncategorized(audit_data):
    user, *_ = audit_data
    result = an_tools.get_top_merchants(user_id=user.id, uncategorized=True)
    merchants = {r["merchant"] for r in result}
    assert merchants == {"M0", "M1", "M2"}


def test_top_merchants_mutual_exclusion(audit_data):
    user, _, expense_cat, _ = audit_data
    with pytest.raises(ValueError):
        an_tools.get_top_merchants(
            user_id=user.id, category_id=str(expense_cat.id), uncategorized=True,
        )


def test_uncategorized_excludes_system_categorized(db_session):
    """list_transactions(uncategorized=True) must require BOTH category_id IS NULL
    AND category_system_id IS NULL.  A row with only category_system_id set (AI-
    assigned, not user-confirmed) must NOT appear in the uncategorized list.
    """
    from app.models import Transaction, Account, Category, User
    from decimal import Decimal
    from datetime import datetime

    user = User(id="sys-cat-user", email="syscat@test.com")
    db_session.add(user)
    acc = Account(user_id=user.id, name="A", account_type="checking")
    db_session.add(acc)
    db_session.flush()

    sys_cat = Category(user_id=user.id, name="SysCat", category_type="expense")
    db_session.add(sys_cat)
    db_session.flush()

    # Row 1: category_system_id set, category_id NULL → AI-assigned, not uncategorized
    txn_sys = Transaction(
        user_id=user.id,
        account_id=acc.id,
        amount=Decimal("-15"),
        currency="EUR",
        description="AI-categorized txn",
        merchant="MerchSys",
        category_id=None,
        category_system_id=sys_cat.id,
        booked_at=datetime(2026, 5, 1),
        transaction_type="debit",
    )
    # Row 2: both NULL → truly uncategorized
    txn_none = Transaction(
        user_id=user.id,
        account_id=acc.id,
        amount=Decimal("-25"),
        currency="EUR",
        description="Fully uncategorized txn",
        merchant="MerchNone",
        category_id=None,
        category_system_id=None,
        booked_at=datetime(2026, 5, 2),
        transaction_type="debit",
    )
    db_session.add_all([txn_sys, txn_none])
    db_session.commit()

    try:
        result = tx_tools.list_transactions(user_id=user.id, uncategorized=True, limit=50)
        ids = {t["id"] for t in result["transactions"]}

        assert str(txn_none.id) in ids, "Truly uncategorized row must be returned"
        assert str(txn_sys.id) not in ids, (
            "Row with category_system_id set must NOT be returned as uncategorized"
        )
        assert len(result["transactions"]) == 1
    finally:
        db_session.query(Transaction).filter(Transaction.user_id == user.id).delete()
        db_session.query(Category).filter(Category.user_id == user.id).delete()
        db_session.query(Account).filter(Account.user_id == user.id).delete()
        db_session.query(User).filter(User.id == user.id).delete()
        db_session.commit()
