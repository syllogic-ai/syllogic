"""Tests for the broker trade import service."""
from datetime import date
from decimal import Decimal

import pytest

from app.services.broker_trade_service import _generate_external_id


def test_generate_external_id_is_deterministic():
    a = _generate_external_id(
        trade_date=date.fromisoformat("2024-01-10"),
        symbol="AAPL",
        side="buy",
        quantity=Decimal("10"),
        price=Decimal("150.00"),
        ordinal=0,
    )
    b = _generate_external_id(
        trade_date=date.fromisoformat("2024-01-10"),
        symbol="AAPL",
        side="buy",
        quantity=Decimal("10"),
        price=Decimal("150.00"),
        ordinal=0,
    )
    assert a == b
    assert a.endswith("#0")


def test_generate_external_id_differs_by_ordinal():
    base_kwargs = dict(
        trade_date=date.fromisoformat("2024-01-10"),
        symbol="AAPL",
        side="buy",
        quantity=Decimal("10"),
        price=Decimal("150.00"),
    )
    a = _generate_external_id(**base_kwargs, ordinal=0)
    b = _generate_external_id(**base_kwargs, ordinal=1)
    assert a != b
    assert a.endswith("#0")
    assert b.endswith("#1")


def test_generate_external_id_differs_by_inputs():
    base_kwargs = dict(
        trade_date=date.fromisoformat("2024-01-10"),
        side="buy",
        quantity=Decimal("10"),
        price=Decimal("150.00"),
        ordinal=0,
    )
    a = _generate_external_id(symbol="AAPL", **base_kwargs)
    b = _generate_external_id(symbol="MSFT", **base_kwargs)
    assert a != b


from app.services.broker_trade_service import import_trades, ImportError as BrokerImportError
from app.models import BrokerTrade, Holding


@pytest.fixture
def investment_account(db_session):
    """Create a user + investment account; clean up after."""
    from app.models import User, Account
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

    # Teardown
    db_session.query(BrokerTrade).filter(BrokerTrade.account_id == account.id).delete()
    db_session.query(Holding).filter(Holding.account_id == account.id).delete()
    db_session.delete(account)
    db_session.delete(user)
    db_session.commit()


def test_import_trades_rejects_unknown_account(db_session):
    with pytest.raises(BrokerImportError, match="account not found"):
        import_trades(
            db_session,
            user_id="nobody",
            account_id="00000000-0000-0000-0000-000000000000",
            trades=[],
            dry_run=False,
        )


def test_import_trades_rejects_account_not_owned(db_session, investment_account):
    with pytest.raises(BrokerImportError, match="account not found"):
        import_trades(
            db_session,
            user_id="someone-else",
            account_id=investment_account["account_id"],
            trades=[],
            dry_run=False,
        )


def test_import_trades_rejects_non_investment_account(db_session):
    from app.models import User, Account
    import uuid

    user = User(
        id=f"test-user-{uuid.uuid4()}",
        email=f"{uuid.uuid4()}@test.local",
        functional_currency="EUR",
    )
    account = Account(
        user_id=user.id,
        name="Checking",
        account_type="bank",
        currency="EUR",
        is_active=True,
    )
    db_session.add_all([user, account])
    db_session.commit()

    try:
        with pytest.raises(BrokerImportError, match="not an investment account"):
            import_trades(
                db_session,
                user_id=user.id,
                account_id=str(account.id),
                trades=[],
                dry_run=False,
            )
    finally:
        db_session.delete(account)
        db_session.delete(user)
        db_session.commit()


def test_import_trades_validates_each_trade(db_session, investment_account):
    bad_trades = [
        # Missing side
        {"symbol": "AAPL", "trade_date": "2024-01-10", "quantity": "10", "price": "150", "currency": "USD"},
        # Negative quantity
        {"symbol": "MSFT", "trade_date": "2024-01-10", "side": "buy", "quantity": "-1", "price": "100", "currency": "USD"},
        # Bad currency length
        {"symbol": "VWRA", "trade_date": "2024-01-10", "side": "buy", "quantity": "1", "price": "100", "currency": "USDD"},
        # Bad side
        {"symbol": "BTC", "trade_date": "2024-01-10", "side": "short", "quantity": "1", "price": "30000", "currency": "USD"},
        # Bad date
        {"symbol": "AAPL", "trade_date": "not-a-date", "side": "buy", "quantity": "1", "price": "100", "currency": "USD"},
    ]
    result = import_trades(
        db_session,
        user_id=investment_account["user_id"],
        account_id=investment_account["account_id"],
        trades=bad_trades,
        dry_run=False,
    )
    assert result["inserted"] == 0
    assert result["skipped_duplicate"] == 0
    assert len(result["errors"]) == 5
    # Each error references its index
    assert {e["index"] for e in result["errors"]} == {0, 1, 2, 3, 4}
