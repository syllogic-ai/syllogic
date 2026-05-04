"""MCP-layer tests for broker trade import + P&L tools."""
from decimal import Decimal

import pytest

from app.models import Account, BrokerTrade, Holding, User
from app.mcp.tools.investments import (
    import_broker_trades_impl,
    get_realized_pnl_impl,
    get_unrealized_pnl_impl,
)


@pytest.fixture
def investment_account(db_session):
    import uuid
    user = User(
        id=f"test-user-{uuid.uuid4()}",
        email=f"{uuid.uuid4()}@test.local",
        functional_currency="EUR",
    )
    db_session.add(user)
    db_session.flush()
    account = Account(
        user_id=user.id,
        name="Test Brokerage",
        account_type="investment_brokerage",
        currency="USD",
        is_active=True,
    )
    db_session.add(account)
    db_session.commit()
    yield {"user_id": user.id, "account_id": str(account.id)}

    db_session.query(BrokerTrade).filter(BrokerTrade.account_id == account.id).delete()
    db_session.query(Holding).filter(Holding.account_id == account.id).delete()
    db_session.delete(account)
    db_session.delete(user)
    db_session.commit()


def test_import_broker_trades_impl_inserts_trades(db_session, investment_account):
    result = import_broker_trades_impl(
        db_session,
        user_id=investment_account["user_id"],
        account_id=investment_account["account_id"],
        trades=[
            {"symbol": "AAPL", "trade_date": "2024-01-10", "side": "buy", "quantity": "10", "price": "150", "currency": "USD"},
        ],
        dry_run=False,
    )
    assert result["inserted"] == 1
    assert result["skipped_duplicate"] == 0
    assert result["errors"] == []
    assert result["affected_symbols"] == ["AAPL"]


def test_get_realized_pnl_impl_returns_native_only_when_fx_missing(db_session, investment_account):
    # Seed trades
    import_broker_trades_impl(
        db_session,
        user_id=investment_account["user_id"],
        account_id=investment_account["account_id"],
        trades=[
            {"symbol": "AAPL", "trade_date": "2024-01-10", "side": "buy", "quantity": "10", "price": "150", "currency": "USD"},
            {"symbol": "AAPL", "trade_date": "2024-06-01", "side": "sell", "quantity": "10", "price": "200", "currency": "USD"},
        ],
        dry_run=False,
    )

    result = get_realized_pnl_impl(db_session, user_id=investment_account["user_id"])

    assert len(result) == 1
    assert result[0]["symbol"] == "AAPL"
    assert result[0]["realized_native"] == "500"


def test_get_unrealized_pnl_impl_skips_symbols_without_latest_price(
    db_session, investment_account
):
    import_broker_trades_impl(
        db_session,
        user_id=investment_account["user_id"],
        account_id=investment_account["account_id"],
        trades=[
            {"symbol": "AAPL", "trade_date": "2024-01-10", "side": "buy", "quantity": "10", "price": "150", "currency": "USD"},
        ],
        dry_run=False,
    )

    # No HoldingValuation seeded → unrealized P&L list is empty for that symbol
    result = get_unrealized_pnl_impl(db_session, user_id=investment_account["user_id"])
    assert result == []
