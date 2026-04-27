"""
Broker trade import orchestration.

Validates ownership, generates stable external_ids for dedup, bulk-inserts
into `broker_trades`, and recomputes `Holding.quantity` and `Holding.avg_cost`
for every affected (account_id, symbol) pair using FIFO.
"""
from __future__ import annotations

import hashlib
from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.models import Account, BrokerTrade, Holding
from app.services.pnl_service import Trade, compute_fifo


VALID_SIDES = ("buy", "sell")


def _normalize_quantity(q: Decimal) -> str:
    # Stable representation for hashing: strip trailing zeros, no scientific notation.
    s = format(q.normalize(), "f")
    return s if s != "-0" else "0"


def _generate_external_id(
    trade_date: date,
    symbol: str,
    side: str,
    quantity: Decimal,
    price: Decimal,
    ordinal: int,
) -> str:
    """Stable hash of the trade fields plus an ordinal disambiguator.

    Format: `<16-hex>#<N>`. Same statement re-uploaded → same id (no-op).
    Two genuinely identical trades on the same day → distinct ids via ordinal.
    """
    key = "|".join([
        trade_date.isoformat(),
        symbol.upper(),
        side.lower(),
        _normalize_quantity(quantity),
        _normalize_quantity(price),
    ])
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]
    return f"{digest}#{ordinal}"


class ImportError(Exception):
    """Raised for import-level (not per-trade) failures."""


@dataclass
class _ValidatedTrade:
    index: int
    symbol: str
    trade_date: date
    side: str
    quantity: Decimal
    price: Decimal
    currency: str
    fees: Decimal
    external_id: str | None
    broker_ref: str | None


def _validate_trade(index: int, raw: dict[str, Any]) -> tuple[_ValidatedTrade | None, dict | None]:
    """Returns (validated, None) on success or (None, error_dict) on failure."""
    try:
        symbol = str(raw["symbol"]).strip()
        if not symbol:
            raise ValueError("symbol required")
        trade_date = date.fromisoformat(str(raw["trade_date"]))
        side = str(raw["side"]).lower()
        if side not in VALID_SIDES:
            raise ValueError(f"side must be one of {VALID_SIDES}, got {side!r}")
        quantity = Decimal(str(raw["quantity"]))
        if quantity <= 0:
            raise ValueError("quantity must be positive")
        price = Decimal(str(raw["price"]))
        if price < 0:
            raise ValueError("price must be non-negative")
        currency = str(raw["currency"]).upper()
        if len(currency) != 3:
            raise ValueError("currency must be a 3-letter ISO code")
        fees_raw = raw.get("fees")
        fees = Decimal(str(fees_raw)) if fees_raw is not None else Decimal("0")
        if fees < 0:
            raise ValueError("fees must be non-negative")
        external_id = raw.get("external_id")
        broker_ref = raw.get("broker_ref")
    except (KeyError, ValueError, TypeError, ArithmeticError) as e:
        return None, {"index": index, "trade": raw, "reason": str(e)}

    return _ValidatedTrade(
        index=index,
        symbol=symbol,
        trade_date=trade_date,
        side=side,
        quantity=quantity,
        price=price,
        currency=currency,
        fees=fees,
        external_id=external_id,
        broker_ref=broker_ref,
    ), None


def import_trades(
    db: Session,
    user_id: str,
    account_id: str,
    trades: list[dict[str, Any]],
    dry_run: bool,
) -> dict[str, Any]:
    """Import a batch of broker trades. See spec §"New MCP tools"."""
    account = (
        db.query(Account)
        .filter(Account.id == account_id, Account.user_id == user_id)
        .first()
    )
    if account is None:
        raise ImportError(f"account not found or not owned by user: {account_id}")
    if account.account_type not in ("investment_manual", "investment_brokerage"):
        raise ImportError(f"account is not an investment account: {account.account_type}")

    validated: list[_ValidatedTrade] = []
    errors: list[dict] = []
    for i, raw in enumerate(trades):
        ok, err = _validate_trade(i, raw)
        if err is not None:
            errors.append(err)
        else:
            validated.append(ok)

    if not validated:
        return {
            "inserted": 0,
            "skipped_duplicate": 0,
            "errors": errors,
            "affected_symbols": [],
        }

    # Step 4 (next task) implements the actual insert + holding recompute.
    return {
        "inserted": 0,
        "skipped_duplicate": 0,
        "errors": errors,
        "affected_symbols": [],
    }
