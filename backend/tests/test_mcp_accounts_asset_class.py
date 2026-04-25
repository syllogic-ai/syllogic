"""Tests for asset_class on MCP list_accounts / get_account responses."""
from __future__ import annotations

import uuid
from decimal import Decimal

import pytest

from app.models import Account, User
from app.mcp.tools.accounts import list_accounts, get_account


@pytest.fixture
def seeded_user(db_session):
    user_id = str(uuid.uuid4())
    user = User(id=user_id, email=f"{user_id}@test.com")
    db_session.add(user)
    db_session.flush()

    rows = [
        Account(
            user_id=user_id,
            name="Op Checking",
            account_type="checking",
            institution="ING",
            currency="EUR",
            provider="manual",
            is_active=True,
            starting_balance=Decimal("0"),
        ),
        Account(
            user_id=user_id,
            name="Long Term Savings",
            account_type="savings",
            institution="ABN",
            currency="EUR",
            provider="manual",
            is_active=True,
            starting_balance=Decimal("0"),
        ),
        Account(
            user_id=user_id,
            name="Brokerage",
            account_type="brokerage",
            institution="IBKR",
            currency="EUR",
            provider="ibkr",
            is_active=True,
            starting_balance=Decimal("0"),
        ),
    ]
    for r in rows:
        db_session.add(r)
    db_session.commit()
    try:
        yield user_id
    finally:
        db_session.query(Account).filter(Account.user_id == user_id).delete()
        db_session.query(User).filter(User.id == user_id).delete()
        db_session.commit()


def test_list_accounts_includes_asset_class(seeded_user):
    accounts = list_accounts(user_id=seeded_user)
    by_name = {a["name"]: a for a in accounts}
    assert by_name["Op Checking"]["asset_class"] == "cash"
    assert by_name["Long Term Savings"]["asset_class"] == "savings"
    assert by_name["Brokerage"]["asset_class"] == "investment"


def test_list_accounts_filters_by_asset_class(seeded_user):
    only_savings = list_accounts(user_id=seeded_user, asset_class="savings")
    assert [a["name"] for a in only_savings] == ["Long Term Savings"]
    assert all(a["asset_class"] == "savings" for a in only_savings)


def test_list_accounts_filter_unknown_asset_class_returns_empty(seeded_user):
    assert list_accounts(user_id=seeded_user, asset_class="zzz") == []


def test_get_account_includes_asset_class(seeded_user):
    accounts = list_accounts(user_id=seeded_user)
    savings_id = next(a["id"] for a in accounts if a["name"] == "Long Term Savings")
    detail = get_account(user_id=seeded_user, account_id=savings_id)
    assert detail is not None
    assert detail["asset_class"] == "savings"
