"""Unit tests for the pure FIFO P&L engine."""
from datetime import date
from decimal import Decimal

import pytest

from app.services.pnl_service import compute_fifo, OverSellError, Trade


def _t(symbol, d, side, qty, price, currency="USD", fees="0"):
    return Trade(
        symbol=symbol,
        trade_date=date.fromisoformat(d),
        side=side,
        quantity=Decimal(str(qty)),
        price=Decimal(str(price)),
        currency=currency,
        fees=Decimal(str(fees)),
    )


def test_compute_fifo_single_buy_full_sell_with_fees():
    """Buy fees increase cost basis; sell fees reduce proceeds."""
    trades = [
        _t("AAPL", "2024-01-10", "buy", 10, 150, fees="5"),    # cost = 1500 + 5 = 1505
        _t("AAPL", "2024-06-01", "sell", 10, 200, fees="3"),   # proceeds = 2000 - 3 = 1997
    ]

    result = compute_fifo(trades)

    assert len(result.realized) == 1
    closed = result.realized[0]
    assert closed.symbol == "AAPL"
    assert closed.quantity == Decimal("10")
    assert closed.cost_native == Decimal("1505")
    assert closed.proceeds_native == Decimal("1997")
    assert closed.pnl_native == Decimal("492")
    assert closed.currency == "USD"
    assert result.open_lots == []


def test_compute_fifo_partial_sell_leaves_open_lot():
    trades = [
        _t("MSFT", "2024-01-10", "buy", 10, 100),
        _t("MSFT", "2024-02-10", "buy", 5, 120),
        _t("MSFT", "2024-06-01", "sell", 12, 150),
    ]

    result = compute_fifo(trades)

    # Sell 12: consumes 10 from first lot + 2 from second lot
    assert len(result.realized) == 2
    assert result.realized[0].quantity == Decimal("10")
    assert result.realized[0].cost_native == Decimal("1000")
    assert result.realized[0].proceeds_native == Decimal("1500")
    assert result.realized[0].pnl_native == Decimal("500")
    assert result.realized[1].quantity == Decimal("2")
    assert result.realized[1].cost_native == Decimal("240")
    assert result.realized[1].proceeds_native == Decimal("300")
    assert result.realized[1].pnl_native == Decimal("60")

    assert len(result.open_lots) == 1
    assert result.open_lots[0].symbol == "MSFT"
    assert result.open_lots[0].quantity_remaining == Decimal("3")
    assert result.open_lots[0].cost_per_share_native == Decimal("120")


def test_compute_fifo_oversell_raises():
    trades = [
        _t("VWRA", "2024-01-10", "buy", 5, 100),
        _t("VWRA", "2024-06-01", "sell", 10, 110),
    ]

    with pytest.raises(OverSellError) as exc:
        compute_fifo(trades)

    assert exc.value.symbol == "VWRA"
    assert exc.value.qty_attempted == Decimal("10")
    assert exc.value.qty_available == Decimal("5")


def test_compute_fifo_buy_fees_carry_into_open_lot_cost():
    """A buy with fees but no sell yet: open lot's cost_per_share reflects fees."""
    trades = [_t("AAPL", "2024-01-10", "buy", 10, 100, fees="20")]

    result = compute_fifo(trades)

    assert result.realized == []
    assert len(result.open_lots) == 1
    # (100*10 + 20) / 10 = 102
    assert result.open_lots[0].cost_per_share_native == Decimal("102")


def test_compute_fifo_sell_fees_prorated_across_lots():
    """When a sell consumes multiple lots, the sell's fee is prorated by quantity."""
    trades = [
        _t("MSFT", "2024-01-10", "buy", 10, 100),    # cost basis 100/share, 0 fees
        _t("MSFT", "2024-02-10", "buy", 10, 100),    # cost basis 100/share, 0 fees
        _t("MSFT", "2024-06-01", "sell", 20, 150, fees="10"),  # prorate 10 across 20 shares
    ]

    result = compute_fifo(trades)

    assert len(result.realized) == 2
    # Each closed lot of 10 shares gets 5 fee → proceeds = 1500 - 5 = 1495 per lot
    for lot in result.realized:
        assert lot.proceeds_native == Decimal("1495")
        assert lot.cost_native == Decimal("1000")
        assert lot.pnl_native == Decimal("495")


def test_compute_fifo_multi_symbol_independent():
    trades = [
        _t("AAPL", "2024-01-10", "buy", 10, 150),
        _t("MSFT", "2024-01-15", "buy", 5, 100),
        _t("AAPL", "2024-06-01", "sell", 10, 200),
    ]

    result = compute_fifo(trades)

    assert len(result.realized) == 1
    assert result.realized[0].symbol == "AAPL"
    assert {l.symbol for l in result.open_lots} == {"MSFT"}


from unittest.mock import MagicMock


def test_realized_pnl_enriches_with_base_currency_fx():
    """The DB-aware wrapper applies FX-on-close-date for base currency."""
    from app.services.pnl_service import realized_pnl_from_trades

    trades = [
        _t("AAPL", "2024-01-10", "buy", 10, 150, currency="USD"),
        _t("AAPL", "2024-06-01", "sell", 10, 200, currency="USD"),
    ]

    fx = MagicMock()
    # 1 USD = 0.92 EUR on close date
    fx.get_exchange_rate.return_value = Decimal("0.92")

    result = realized_pnl_from_trades(trades, base_currency="EUR", fx_service=fx)

    assert len(result) == 1
    row = result[0]
    assert row["symbol"] == "AAPL"
    assert row["currency"] == "USD"
    assert row["realized_native"] == Decimal("500")
    assert row["realized_base"] == Decimal("460.00")
    assert len(row["lots_closed"]) == 1
    assert row["lots_closed"][0]["pnl_base"] == Decimal("460.00")
    fx.get_exchange_rate.assert_called_with("USD", "EUR", date.fromisoformat("2024-06-01"))
