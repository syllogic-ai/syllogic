"""
Pure FIFO P&L engine.

`compute_fifo` is a pure function over a list of trades — no DB access,
no FX, no I/O. DB- and FX-aware wrappers live below.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Iterable


@dataclass(frozen=True)
class Trade:
    """Input trade for the FIFO engine."""
    symbol: str
    trade_date: date
    side: str  # "buy" | "sell"
    quantity: Decimal
    price: Decimal
    currency: str
    fees: Decimal = Decimal("0")  # native currency, non-negative


@dataclass(frozen=True)
class ClosedLot:
    """A realized P&L lot — the result of a sell matching against open buy lots."""
    symbol: str
    currency: str
    open_date: date
    close_date: date
    quantity: Decimal
    cost_native: Decimal
    proceeds_native: Decimal
    pnl_native: Decimal


@dataclass(frozen=True)
class OpenLot:
    """A remaining unmatched buy lot."""
    symbol: str
    currency: str
    open_date: date
    quantity_remaining: Decimal
    cost_per_share_native: Decimal


@dataclass
class FifoResult:
    realized: list[ClosedLot] = field(default_factory=list)
    open_lots: list[OpenLot] = field(default_factory=list)


class OverSellError(Exception):
    """Raised when a sell exceeds available open quantity for a symbol."""
    def __init__(self, symbol: str, trade_date: date, qty_attempted: Decimal, qty_available: Decimal):
        self.symbol = symbol
        self.trade_date = trade_date
        self.qty_attempted = qty_attempted
        self.qty_available = qty_available
        super().__init__(
            f"Sell of {qty_attempted} {symbol} on {trade_date} exceeds available {qty_available}"
        )


@dataclass
class _MutableLot:
    open_date: date
    quantity_remaining: Decimal
    cost_per_share_native: Decimal
    currency: str


def compute_fifo(trades: Iterable[Trade]) -> FifoResult:
    """
    Apply FIFO matching to a sequence of trades.

    Trades are processed in chronological order (then by side, buys first on
    ties so a same-day buy can cover a same-day sell).

    Currency is tracked per-symbol; if a symbol's trades use mixed currencies
    they are still matched (currency redenomination is out of scope for the
    pure engine — caller decides whether to split).
    """
    sorted_trades = sorted(trades, key=lambda t: (t.trade_date, 0 if t.side == "buy" else 1))

    open_by_symbol: dict[str, list[_MutableLot]] = {}
    realized: list[ClosedLot] = []

    for t in sorted_trades:
        lots = open_by_symbol.setdefault(t.symbol, [])
        if t.side == "buy":
            # Buy fees increase cost basis: cost_per_share = (price*qty + fees) / qty
            cost_per_share = (
                (t.price * t.quantity + t.fees) / t.quantity
                if t.quantity > 0
                else t.price
            )
            lots.append(_MutableLot(
                open_date=t.trade_date,
                quantity_remaining=t.quantity,
                cost_per_share_native=cost_per_share,
                currency=t.currency,
            ))
            continue

        # sell — fees reduce proceeds, prorated by consumed quantity vs total sell qty
        remaining = t.quantity
        sell_total_qty = t.quantity
        # Pre-compute available quantity before iterating (for oversell error reporting)
        available_at_start = sum((l.quantity_remaining for l in lots), Decimal("0"))
        while remaining > 0:
            if not lots:
                raise OverSellError(t.symbol, t.trade_date, t.quantity, available_at_start)
            lot = lots[0]
            consumed = min(lot.quantity_remaining, remaining)
            cost = consumed * lot.cost_per_share_native
            fee_share = (t.fees * consumed / sell_total_qty) if sell_total_qty > 0 else Decimal("0")
            proceeds = consumed * t.price - fee_share
            realized.append(ClosedLot(
                symbol=t.symbol,
                currency=t.currency,
                open_date=lot.open_date,
                close_date=t.trade_date,
                quantity=consumed,
                cost_native=cost,
                proceeds_native=proceeds,
                pnl_native=proceeds - cost,
            ))
            lot.quantity_remaining -= consumed
            remaining -= consumed
            if lot.quantity_remaining == 0:
                lots.pop(0)

    open_lots: list[OpenLot] = []
    for sym, lots in open_by_symbol.items():
        for lot in lots:
            open_lots.append(OpenLot(
                symbol=sym,
                currency=lot.currency,
                open_date=lot.open_date,
                quantity_remaining=lot.quantity_remaining,
                cost_per_share_native=lot.cost_per_share_native,
            ))

    return FifoResult(realized=realized, open_lots=open_lots)


def realized_pnl_from_trades(
    trades: Iterable[Trade],
    base_currency: str,
    fx_service,
) -> list[dict]:
    """
    Run FIFO and enrich each closed lot with base-currency P&L.

    `fx_service` must implement `get_exchange_rate(src, dst, on: date) -> Decimal | None`
    (matches `app.services.exchange_rate_service.ExchangeRateService`).

    Groups closed lots by symbol; per-lot FX is taken on the lot's close_date.
    Lots whose FX lookup fails contribute 0 to `realized_base` and are flagged
    via a `fx_missing` boolean on the lot dict.
    """
    fifo = compute_fifo(trades)

    by_symbol: dict[str, list[ClosedLot]] = {}
    for lot in fifo.realized:
        by_symbol.setdefault(lot.symbol, []).append(lot)

    out: list[dict] = []
    for symbol, lots in by_symbol.items():
        symbol_currency = lots[0].currency
        realized_native_total = Decimal("0")
        realized_base_total = Decimal("0")
        lot_dicts = []
        for lot in lots:
            rate = fx_service.get_exchange_rate(lot.currency, base_currency, lot.close_date)
            if rate is None:
                pnl_base = Decimal("0")
                fx_missing = True
            else:
                pnl_base = (lot.pnl_native * rate).quantize(Decimal("0.01"))
                fx_missing = False
            realized_native_total += lot.pnl_native
            realized_base_total += pnl_base
            lot_dicts.append({
                "open_date": lot.open_date.isoformat(),
                "close_date": lot.close_date.isoformat(),
                "quantity": lot.quantity,
                "cost_native": lot.cost_native,
                "proceeds_native": lot.proceeds_native,
                "pnl_native": lot.pnl_native,
                "pnl_base": pnl_base,
                "fx_missing": fx_missing,
            })
        out.append({
            "symbol": symbol,
            "currency": symbol_currency,
            "realized_native": realized_native_total,
            "realized_base": realized_base_total,
            "lots_closed": lot_dicts,
        })
    return out
