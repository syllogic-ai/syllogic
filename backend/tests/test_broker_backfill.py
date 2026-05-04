"""Tests for backfill_history and compute_open_quantity_series."""
from __future__ import annotations

import uuid
from datetime import date, timedelta
from decimal import Decimal

import pytest

from app.integrations.price_provider.base import PriceQuote
from app.models import (
    Account,
    AccountBalance,
    BrokerTrade,
    Holding,
    HoldingValuation,
    PriceSnapshot,
    User,
)
from app.services.broker_trade_service import backfill_history, import_trades
from app.services.pnl_service import Trade, compute_open_quantity_series


# ---------------------------------------------------------------------------
# Pure helper
# ---------------------------------------------------------------------------


def _t(symbol, d, side, qty):
    return Trade(
        symbol=symbol,
        trade_date=date.fromisoformat(d),
        side=side,
        quantity=Decimal(qty),
        price=Decimal("0"),
        currency="USD",
    )


def test_open_quantity_series_buys_only():
    s = compute_open_quantity_series(
        [_t("AAPL", "2024-01-10", "buy", "10")],
        start=date.fromisoformat("2024-01-09"),
        end=date.fromisoformat("2024-01-12"),
    )
    series = s["AAPL"]
    assert series[date.fromisoformat("2024-01-09")] == Decimal("0")
    assert series[date.fromisoformat("2024-01-10")] == Decimal("10")
    assert series[date.fromisoformat("2024-01-11")] == Decimal("10")
    assert series[date.fromisoformat("2024-01-12")] == Decimal("10")


def test_open_quantity_series_sell_partial():
    s = compute_open_quantity_series(
        [
            _t("AAPL", "2024-01-10", "buy", "10"),
            _t("AAPL", "2024-01-15", "sell", "3"),
        ],
        start=date.fromisoformat("2024-01-09"),
        end=date.fromisoformat("2024-01-16"),
    )
    series = s["AAPL"]
    assert series[date.fromisoformat("2024-01-10")] == Decimal("10")
    assert series[date.fromisoformat("2024-01-14")] == Decimal("10")
    assert series[date.fromisoformat("2024-01-15")] == Decimal("7")
    assert series[date.fromisoformat("2024-01-16")] == Decimal("7")


def test_open_quantity_series_seeds_from_pre_start_trades():
    """Trades before `start` apply to the running total so the series begins at the right level."""
    s = compute_open_quantity_series(
        [_t("AAPL", "2024-01-01", "buy", "10")],
        start=date.fromisoformat("2024-02-01"),
        end=date.fromisoformat("2024-02-03"),
    )
    series = s["AAPL"]
    assert series[date.fromisoformat("2024-02-01")] == Decimal("10")
    assert series[date.fromisoformat("2024-02-03")] == Decimal("10")


# ---------------------------------------------------------------------------
# backfill_history with a fake price provider
# ---------------------------------------------------------------------------


class _FakePriceProvider:
    name = "fake"

    def __init__(self, closes: dict[date, Decimal], currency: str = "USD"):
        self._closes = closes
        self._ccy = currency

    def get_daily_close(self, symbol, on):
        return None

    def get_daily_closes(self, symbols, on):
        return {}

    def get_daily_closes_range(self, symbol, start, end):
        return [
            PriceQuote(symbol=symbol, currency=self._ccy, date=d, close=c)
            for d, c in sorted(self._closes.items())
            if start <= d <= end
        ]

    def search_symbols(self, query):
        return []


class _FakeFx:
    """FX service stub returning a fixed rate."""

    def __init__(self, rate: Decimal = Decimal("1.0")):
        self._rate = rate

    def get_exchange_rate_with_fallback(self, base, target, for_date):
        if base == target:
            return Decimal("1.0")
        return self._rate

    def get_exchange_rate(self, base, target, for_date):
        return self.get_exchange_rate_with_fallback(base, target, for_date)


@pytest.fixture
def investment_account_with_aapl(db_session):
    """Create a user + investment account with one AAPL buy trade + holding."""
    user = User(
        id=f"test-user-{uuid.uuid4()}",
        email=f"{uuid.uuid4()}@test.local",
        functional_currency="USD",
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
    db_session.flush()

    trade_date = date.today() - timedelta(days=4)
    trade = BrokerTrade(
        account_id=account.id,
        symbol="AAPL",
        trade_date=trade_date,
        side="buy",
        quantity=Decimal("10"),
        price=Decimal("150"),
        currency="USD",
        fees=Decimal("0"),
        external_id="test-aapl-1",
    )
    db_session.add(trade)

    holding = Holding(
        user_id=user.id,
        account_id=account.id,
        symbol="AAPL",
        currency="USD",
        instrument_type="equity",
        quantity=Decimal("10"),
        avg_cost=Decimal("150"),
        as_of_date=trade_date,
        source="trade_import",
    )
    db_session.add(holding)
    db_session.commit()

    yield {
        "user_id": user.id,
        "account": account,
        "holding": holding,
        "trade_date": trade_date,
    }

    # Teardown — clean up valuations + balances we created.
    db_session.query(HoldingValuation).filter(
        HoldingValuation.holding_id == holding.id
    ).delete()
    db_session.query(AccountBalance).filter(
        AccountBalance.account_id == account.id
    ).delete()
    db_session.query(BrokerTrade).filter(BrokerTrade.account_id == account.id).delete()
    db_session.query(PriceSnapshot).filter(PriceSnapshot.symbol == "AAPL").delete()
    db_session.delete(holding)
    db_session.delete(account)
    db_session.delete(user)
    db_session.commit()


def test_backfill_history_creates_valuations_for_each_day(
    db_session, investment_account_with_aapl
):
    ctx = investment_account_with_aapl
    trade_date = ctx["trade_date"]
    today = date.today()

    # Fake closes for the trade window — provide one close on the trade date
    # and one a couple days later. The intermediate days should forward-fill.
    closes = {
        trade_date: Decimal("150"),
        trade_date + timedelta(days=2): Decimal("160"),
    }
    provider = _FakePriceProvider(closes)
    fx = _FakeFx()

    result = backfill_history(
        db_session,
        ctx["account"],
        ["AAPL"],
        price_provider=provider,
        fx_service=fx,
    )

    # We get rows from trade_date through today, inclusive.
    expected_days = (today - trade_date).days + 1
    assert result["valuations_upserted"] == expected_days

    rows = (
        db_session.query(HoldingValuation)
        .filter(HoldingValuation.holding_id == ctx["holding"].id)
        .order_by(HoldingValuation.date)
        .all()
    )
    assert len(rows) == expected_days
    # First row uses the trade_date close; the day after should forward-fill it.
    assert Decimal(rows[0].price) == Decimal("150")
    assert Decimal(rows[0].value_user_currency) == Decimal("1500.00")
    if len(rows) > 1:
        assert Decimal(rows[1].price) == Decimal("150")  # forward-filled
    if len(rows) > 2:
        # 3rd day: price bumps to 160
        assert Decimal(rows[2].price) == Decimal("160")
        assert Decimal(rows[2].value_user_currency) == Decimal("1600.00")


def test_backfill_history_creates_account_balances(
    db_session, investment_account_with_aapl
):
    ctx = investment_account_with_aapl
    trade_date = ctx["trade_date"]
    today = date.today()
    closes = {trade_date: Decimal("150")}

    backfill_history(
        db_session,
        ctx["account"],
        ["AAPL"],
        price_provider=_FakePriceProvider(closes),
        fx_service=_FakeFx(),
    )

    balances = (
        db_session.query(AccountBalance)
        .filter(AccountBalance.account_id == ctx["account"].id)
        .all()
    )
    expected_days = (today - trade_date).days + 1
    assert len(balances) == expected_days
    # Each day should be 10 * 150 = 1500 in USD (= functional currency here).
    for b in balances:
        assert Decimal(b.balance_in_account_currency) == Decimal("1500.00")
        assert Decimal(b.balance_in_functional_currency) == Decimal("1500.00")


def test_backfill_history_is_idempotent(db_session, investment_account_with_aapl):
    ctx = investment_account_with_aapl
    trade_date = ctx["trade_date"]
    closes = {trade_date: Decimal("150")}
    provider = _FakePriceProvider(closes)
    fx = _FakeFx()

    backfill_history(db_session, ctx["account"], ["AAPL"], price_provider=provider, fx_service=fx)
    first_count = db_session.query(HoldingValuation).filter(
        HoldingValuation.holding_id == ctx["holding"].id
    ).count()

    backfill_history(db_session, ctx["account"], ["AAPL"], price_provider=provider, fx_service=fx)
    second_count = db_session.query(HoldingValuation).filter(
        HoldingValuation.holding_id == ctx["holding"].id
    ).count()

    assert first_count == second_count


def test_backfill_history_partial_import_preserves_other_holdings_balance(
    db_session, investment_account_with_aapl
):
    """A second backfill with only some symbols must NOT erase other holdings'
    contributions to AccountBalance — the per-day total must reflect ALL
    holdings in the account."""
    ctx = investment_account_with_aapl
    trade_date = ctx["trade_date"]
    today = date.today()

    # Add a second holding (MSFT) with a manual valuation row on the same date.
    msft = Holding(
        user_id=ctx["user_id"],
        account_id=ctx["account"].id,
        symbol="MSFT",
        currency="USD",
        instrument_type="equity",
        quantity=Decimal("5"),
        avg_cost=Decimal("300"),
        as_of_date=trade_date,
        source="manual",
    )
    db_session.add(msft)
    db_session.flush()
    db_session.add(HoldingValuation(
        holding_id=msft.id,
        date=trade_date,
        quantity=Decimal("5"),
        price=Decimal("300"),
        value_user_currency=Decimal("1500.00"),
        is_stale=False,
    ))
    db_session.commit()

    try:
        # Backfill ONLY AAPL (subset).
        backfill_history(
            db_session,
            ctx["account"],
            ["AAPL"],
            price_provider=_FakePriceProvider({trade_date: Decimal("150")}),
            fx_service=_FakeFx(),
        )

        # Trade-day balance should sum BOTH holdings: 1500 (AAPL) + 1500 (MSFT) = 3000
        bal = (
            db_session.query(AccountBalance)
            .filter(
                AccountBalance.account_id == ctx["account"].id,
                AccountBalance.date == trade_date,
            )
            .one()
        )
        assert Decimal(bal.balance_in_functional_currency) == Decimal("3000.00")
    finally:
        db_session.query(HoldingValuation).filter(
            HoldingValuation.holding_id == msft.id
        ).delete()
        db_session.delete(msft)
        db_session.commit()


def test_backfill_history_no_quotes_no_rows(db_session, investment_account_with_aapl):
    """If the price provider returns no data we do not insert valuations."""
    ctx = investment_account_with_aapl

    result = backfill_history(
        db_session,
        ctx["account"],
        ["AAPL"],
        price_provider=_FakePriceProvider({}),
        fx_service=_FakeFx(),
    )
    assert result["valuations_upserted"] == 0
    rows = db_session.query(HoldingValuation).filter(
        HoldingValuation.holding_id == ctx["holding"].id
    ).count()
    assert rows == 0
