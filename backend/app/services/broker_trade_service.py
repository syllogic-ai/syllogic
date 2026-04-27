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


def _hash_trade_key(
    trade_date: date,
    symbol: str,
    side: str,
    quantity: Decimal,
    price: Decimal,
) -> str:
    """16-hex stable digest of the trade collision key (date|symbol|side|qty|price)."""
    key = "|".join([
        trade_date.isoformat(),
        symbol.upper(),
        side.lower(),
        _normalize_quantity(quantity),
        _normalize_quantity(price),
    ])
    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]


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
    return f"{_hash_trade_key(trade_date, symbol, side, quantity, price)}#{ordinal}"


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

    # Generate external_ids for trades that didn't provide one.
    # Ordinal assignment is sequential (0, 1, 2, ...) per collision key. This
    # preserves idempotent re-upload (same trades → same ids → ON CONFLICT
    # dedup) while also being cross-batch aware: if a previous batch already
    # imported N same-key trades (#0..#N-1) and a new batch contains M more,
    # we look up the existing count and start new ordinals at N — so the new
    # rows don't collide with the existing #0..#N-1 and are correctly inserted.
    existing_max_by_digest: dict[str, int] = {}
    existing_rows = (
        db.query(BrokerTrade.external_id)
        .filter(BrokerTrade.account_id == account.id)
        .all()
    )
    for (eid,) in existing_rows:
        if not eid or "#" not in eid:
            continue
        prefix, _, ord_str = eid.rpartition("#")
        try:
            n = int(ord_str)
        except ValueError:
            continue
        prev = existing_max_by_digest.get(prefix)
        if prev is None or n > prev:
            existing_max_by_digest[prefix] = n

    batch_count_by_digest: dict[str, int] = defaultdict(int)
    for vt in validated:
        if vt.external_id:
            continue
        digest = _hash_trade_key(
            trade_date=vt.trade_date,
            symbol=vt.symbol,
            side=vt.side,
            quantity=vt.quantity,
            price=vt.price,
        )
        # Sequential within batch (0, 1, 2, ...). For re-uploads these match
        # existing ids and dedup. If the batch produces more same-key trades
        # than already exist, the surplus uses ordinals beyond the existing max.
        batch_idx = batch_count_by_digest[digest]
        batch_count_by_digest[digest] += 1
        existing_max = existing_max_by_digest.get(digest, -1)
        ordinal = batch_idx if batch_idx <= existing_max else max(batch_idx, existing_max + 1)
        vt.external_id = f"{digest}#{ordinal}"

    # Bulk insert with ON CONFLICT DO NOTHING; RETURNING tells us which rows actually inserted.
    rows = [
        {
            "account_id": account.id,
            "symbol": vt.symbol.upper(),
            "trade_date": vt.trade_date,
            "side": vt.side,
            "quantity": vt.quantity,
            "price": vt.price,
            "currency": vt.currency,
            "fees": vt.fees,
            "external_id": vt.external_id,
        }
        for vt in validated
    ]

    stmt = (
        pg_insert(BrokerTrade.__table__)
        .values(rows)
        .on_conflict_do_nothing(index_elements=["account_id", "external_id"])
        .returning(BrokerTrade.__table__.c.id, BrokerTrade.__table__.c.symbol)
    )
    inserted_rows = db.execute(stmt).fetchall()
    inserted = len(inserted_rows)
    skipped = len(validated) - inserted
    affected_symbols = sorted({vt.symbol.upper() for vt in validated})

    # Recompute holdings before deciding whether to commit so dry_run still
    # surfaces FIFO oversell errors and any other recompute failures.
    for symbol in affected_symbols:
        _recompute_holding(db, account, symbol)

    if dry_run:
        db.rollback()
    else:
        db.commit()

    return {
        "inserted": inserted,
        "skipped_duplicate": skipped,
        "errors": errors,
        "affected_symbols": affected_symbols,
    }


def _recompute_holding(db: Session, account: Account, symbol: str) -> None:
    """Rebuild Holding(account, symbol) from full BrokerTrade history using FIFO."""
    trades = (
        db.query(BrokerTrade)
        .filter(BrokerTrade.account_id == account.id, BrokerTrade.symbol == symbol)
        .order_by(BrokerTrade.trade_date)
        .all()
    )
    if not trades:
        return

    fifo_trades = [
        Trade(
            symbol=t.symbol,
            trade_date=t.trade_date,
            side=t.side,
            quantity=Decimal(t.quantity),
            price=Decimal(t.price),
            currency=t.currency,
            fees=Decimal(t.fees or 0),
        )
        for t in trades
    ]
    result = compute_fifo(fifo_trades)
    open_lots = [l for l in result.open_lots if l.symbol == symbol]

    quantity = sum((l.quantity_remaining for l in open_lots), Decimal("0"))
    if quantity > 0:
        total_cost = sum(
            (l.quantity_remaining * l.cost_per_share_native for l in open_lots),
            Decimal("0"),
        )
        avg_cost = (total_cost / quantity).quantize(Decimal("0.00000001"))
        currency = open_lots[0].currency
    else:
        avg_cost = None
        currency = trades[-1].currency

    last_date = max(t.trade_date for t in trades)

    holding = (
        db.query(Holding)
        .filter(
            Holding.account_id == account.id,
            Holding.symbol == symbol,
            Holding.instrument_type == "equity",
        )
        .first()
    )
    if holding is None:
        holding = Holding(
            user_id=account.user_id,
            account_id=account.id,
            symbol=symbol,
            currency=currency,
            instrument_type="equity",
            quantity=quantity,
            avg_cost=avg_cost,
            as_of_date=last_date,
            source="trade_import",
        )
        db.add(holding)
    else:
        holding.quantity = quantity
        holding.avg_cost = avg_cost
        holding.as_of_date = last_date
        holding.source = "trade_import"
        if not holding.currency:
            holding.currency = currency
