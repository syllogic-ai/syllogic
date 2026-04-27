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


def _trade(symbol, d, side, qty, price, currency="USD", external_id=None):
    t = {
        "symbol": symbol,
        "trade_date": d,
        "side": side,
        "quantity": qty,
        "price": price,
        "currency": currency,
    }
    if external_id is not None:
        t["external_id"] = external_id
    return t


def test_import_trades_inserts_and_dedups(db_session, investment_account):
    payload = [
        _trade("AAPL", "2024-01-10", "buy", "10", "150"),
        _trade("AAPL", "2024-06-01", "sell", "5", "200"),
    ]

    first = import_trades(
        db_session,
        user_id=investment_account["user_id"],
        account_id=investment_account["account_id"],
        trades=payload,
        dry_run=False,
    )
    assert first["inserted"] == 2
    assert first["skipped_duplicate"] == 0
    assert first["errors"] == []
    assert set(first["affected_symbols"]) == {"AAPL"}

    second = import_trades(
        db_session,
        user_id=investment_account["user_id"],
        account_id=investment_account["account_id"],
        trades=payload,
        dry_run=False,
    )
    assert second["inserted"] == 0
    assert second["skipped_duplicate"] == 2

    # Persisted rows
    rows = (
        db_session.query(BrokerTrade)
        .filter(BrokerTrade.account_id == investment_account["account_id"])
        .all()
    )
    assert len(rows) == 2


def test_import_trades_assigns_distinct_external_ids_for_same_day_duplicates(
    db_session, investment_account
):
    """Two genuine identical trades on the same day must both be stored."""
    payload = [
        _trade("AAPL", "2024-01-10", "buy", "10", "150"),
        _trade("AAPL", "2024-01-10", "buy", "10", "150"),
    ]
    result = import_trades(
        db_session,
        user_id=investment_account["user_id"],
        account_id=investment_account["account_id"],
        trades=payload,
        dry_run=False,
    )
    assert result["inserted"] == 2
    rows = (
        db_session.query(BrokerTrade)
        .filter(BrokerTrade.account_id == investment_account["account_id"])
        .all()
    )
    assert {r.external_id for r in rows} != {None}
    assert len({r.external_id for r in rows}) == 2


def test_import_trades_dry_run_rolls_back(db_session, investment_account):
    payload = [_trade("AAPL", "2024-01-10", "buy", "10", "150")]
    result = import_trades(
        db_session,
        user_id=investment_account["user_id"],
        account_id=investment_account["account_id"],
        trades=payload,
        dry_run=True,
    )
    assert result["inserted"] == 1  # reported as if inserted
    rows = (
        db_session.query(BrokerTrade)
        .filter(BrokerTrade.account_id == investment_account["account_id"])
        .all()
    )
    assert rows == []  # but actually rolled back


def test_import_trades_caller_supplied_external_id_wins(db_session, investment_account):
    payload = [
        _trade("AAPL", "2024-01-10", "buy", "10", "150", external_id="BROKER-CONFIRM-001"),
    ]
    result = import_trades(
        db_session,
        user_id=investment_account["user_id"],
        account_id=investment_account["account_id"],
        trades=payload,
        dry_run=False,
    )
    assert result["inserted"] == 1
    row = (
        db_session.query(BrokerTrade)
        .filter(BrokerTrade.account_id == investment_account["account_id"])
        .one()
    )
    assert row.external_id == "BROKER-CONFIRM-001"


def test_import_trades_recomputes_holding_quantity_and_avg_cost(db_session, investment_account):
    """After import, Holding.quantity = sum(buys) - sum(sells); avg_cost = weighted avg of open lots."""
    payload = [
        _trade("AAPL", "2024-01-10", "buy", "10", "100"),  # cost 1000
        _trade("AAPL", "2024-02-10", "buy", "5", "120"),   # cost 600
        _trade("AAPL", "2024-06-01", "sell", "8", "150"),  # consumes 8 from first lot
    ]
    result = import_trades(
        db_session,
        user_id=investment_account["user_id"],
        account_id=investment_account["account_id"],
        trades=payload,
        dry_run=False,
    )
    assert result["inserted"] == 3

    holding = (
        db_session.query(Holding)
        .filter(
            Holding.account_id == investment_account["account_id"],
            Holding.symbol == "AAPL",
        )
        .one()
    )
    # Remaining: 2 from first lot @ 100 + 5 from second lot @ 120 = 7 shares
    assert holding.quantity == Decimal("7")
    # Weighted avg of remaining open lots: (2*100 + 5*120) / 7 = 800/7
    assert holding.avg_cost == (Decimal("800") / Decimal("7")).quantize(Decimal("0.00000001"))
    assert holding.source == "trade_import"
