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
