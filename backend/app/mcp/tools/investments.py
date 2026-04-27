"""
Investments tools for the MCP server.

Exposes:
- list_holdings: per-account holdings with latest valuation
- get_portfolio_summary: aggregate portfolio value across investment accounts
- get_portfolio_history: daily portfolio value history (sum of investment account balances)
- search_symbol: lookup symbols seen in user's holdings
"""
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.mcp.dependencies import get_db, validate_date
from app.models import (
    Account,
    AccountBalance,
    BrokerTrade,
    Holding,
    HoldingValuation,
    User,
)
from app.services.broker_trade_service import import_trades as _import_trades_service
from app.services.broker_trade_service import ImportError as _BrokerImportError
from app.services.exchange_rate_service import ExchangeRateService
from app.services.pnl_service import (
    Trade,
    realized_pnl_from_trades,
    unrealized_pnl_from_trades,
)


INVESTMENT_ACCOUNT_TYPES = ("investment_manual", "investment_brokerage")


def _latest_valuations_for_user(db: Session, user_id: str):
    """Return mapping of holding_id -> latest HoldingValuation for the user."""
    holding_ids_subq = (
        db.query(Holding.id)
        .filter(Holding.user_id == user_id)
        .subquery()
    )

    latest_dates = (
        db.query(
            HoldingValuation.holding_id.label("hid"),
            func.max(HoldingValuation.date).label("max_date"),
        )
        .filter(HoldingValuation.holding_id.in_(holding_ids_subq))
        .group_by(HoldingValuation.holding_id)
        .subquery()
    )

    rows = (
        db.query(HoldingValuation)
        .join(
            latest_dates,
            (HoldingValuation.holding_id == latest_dates.c.hid)
            & (HoldingValuation.date == latest_dates.c.max_date),
        )
        .all()
    )
    return {v.holding_id: v for v in rows}


def list_holdings_impl(
    db: Session,
    user_id: str,
    account_id: Optional[str] = None,
) -> list[dict]:
    """List a user's holdings with latest valuation."""
    query = db.query(Holding).filter(Holding.user_id == user_id)
    if account_id:
        query = query.filter(Holding.account_id == account_id)
    holdings = query.order_by(Holding.symbol).all()

    valuations = _latest_valuations_for_user(db, user_id)

    out = []
    for h in holdings:
        v = valuations.get(h.id)
        out.append(
            {
                "id": str(h.id),
                "account_id": str(h.account_id),
                "symbol": h.symbol,
                "name": h.name,
                "currency": h.currency,
                "instrument_type": h.instrument_type,
                "quantity": str(h.quantity) if h.quantity is not None else "0",
                "avg_cost": str(h.avg_cost) if h.avg_cost is not None else None,
                "source": h.source,
                "as_of_date": h.as_of_date.isoformat() if h.as_of_date else None,
                "latest_price": str(v.price) if v else None,
                "latest_valuation_date": v.date.isoformat() if v else None,
                "current_value_user_currency": str(v.value_user_currency) if v else None,
                "is_stale": bool(v.is_stale) if v else None,
                "last_price_error": h.last_price_error,
            }
        )
    return out


def list_holdings(user_id: str, account_id: Optional[str] = None) -> list[dict]:
    with get_db() as db:
        return list_holdings_impl(db, user_id, account_id)


def get_portfolio_summary_impl(db: Session, user_id: str) -> dict:
    """Aggregate portfolio value across the user's investment accounts."""
    user = db.query(User).filter(User.id == user_id).first()
    currency = getattr(user, "functional_currency", "EUR") if user else "EUR"

    accounts = (
        db.query(Account)
        .filter(
            Account.user_id == user_id,
            Account.account_type.in_(INVESTMENT_ACCOUNT_TYPES),
            Account.is_active == True,  # noqa: E712
        )
        .all()
    )
    account_ids = [a.id for a in accounts]

    valuations = _latest_valuations_for_user(db, user_id)

    # Sum value per account from latest valuations of holdings in those accounts.
    holdings = (
        db.query(Holding)
        .filter(Holding.user_id == user_id, Holding.account_id.in_(account_ids))
        .all()
    ) if account_ids else []

    per_account: dict = {}
    total = Decimal("0")
    stale_count = 0
    for h in holdings:
        v = valuations.get(h.id)
        if v is None:
            continue
        val = Decimal(v.value_user_currency or 0)
        total += val
        if v.is_stale:
            stale_count += 1
        per_account.setdefault(str(h.account_id), Decimal("0"))
        per_account[str(h.account_id)] += val

    accounts_out = []
    for a in accounts:
        accounts_out.append(
            {
                "id": str(a.id),
                "name": a.name,
                "account_type": a.account_type,
                "currency": a.currency,
                "value_user_currency": str(per_account.get(str(a.id), Decimal("0"))),
            }
        )

    return {
        "currency": currency,
        "total_value": str(total),
        "holdings_count": len(holdings),
        "stale_valuations": stale_count,
        "accounts": accounts_out,
    }


def get_portfolio_summary(user_id: str) -> dict:
    with get_db() as db:
        return get_portfolio_summary_impl(db, user_id)


def get_portfolio_history_impl(
    db: Session,
    user_id: str,
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
) -> list[dict]:
    """Return daily portfolio value history (sum across investment accounts) in functional currency."""
    from_dt = validate_date(from_date)
    to_dt = validate_date(to_date)

    account_ids = [
        a.id
        for a in db.query(Account.id)
        .filter(
            Account.user_id == user_id,
            Account.account_type.in_(INVESTMENT_ACCOUNT_TYPES),
        )
        .all()
    ]
    if not account_ids:
        return []

    query = db.query(AccountBalance).filter(AccountBalance.account_id.in_(account_ids))
    if from_dt:
        query = query.filter(AccountBalance.date >= from_dt)
    if to_dt:
        query = query.filter(AccountBalance.date <= to_dt)

    rows = query.order_by(AccountBalance.date).all()

    by_date: dict = {}
    for r in rows:
        key = r.date.isoformat() if hasattr(r.date, "isoformat") else str(r.date)
        by_date.setdefault(key, Decimal("0"))
        by_date[key] += Decimal(r.balance_in_functional_currency or 0)

    return [{"date": d, "value_user_currency": str(v)} for d, v in sorted(by_date.items())]


def get_portfolio_history(
    user_id: str,
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
) -> list[dict]:
    with get_db() as db:
        return get_portfolio_history_impl(db, user_id, from_date, to_date)


def search_symbol_impl(db: Session, user_id: str, query: str) -> list[dict]:
    """Search the user's existing holdings for a symbol/name match."""
    if not query:
        return []
    pattern = f"%{query.lower()}%"
    rows = (
        db.query(Holding.symbol, Holding.name, Holding.currency, Holding.instrument_type)
        .filter(Holding.user_id == user_id)
        .filter(
            (func.lower(Holding.symbol).like(pattern))
            | (func.lower(func.coalesce(Holding.name, "")).like(pattern))
        )
        .distinct()
        .limit(50)
        .all()
    )
    return [
        {
            "symbol": r[0],
            "name": r[1],
            "currency": r[2],
            "instrument_type": r[3],
        }
        for r in rows
    ]


def search_symbol(user_id: str, query: str) -> list[dict]:
    with get_db() as db:
        return search_symbol_impl(db, user_id, query)


def import_broker_trades_impl(
    db: Session,
    user_id: str,
    account_id: str,
    trades: list[dict],
    dry_run: bool = False,
) -> dict:
    try:
        return _import_trades_service(
            db=db,
            user_id=user_id,
            account_id=account_id,
            trades=trades,
            dry_run=dry_run,
        )
    except _BrokerImportError as e:
        return {
            "inserted": 0,
            "skipped_duplicate": 0,
            "errors": [{"index": -1, "trade": None, "reason": str(e)}],
            "affected_symbols": [],
        }


def import_broker_trades(
    user_id: str,
    account_id: str,
    trades: list[dict],
    dry_run: bool = False,
) -> dict:
    with get_db() as db:
        return import_broker_trades_impl(db, user_id, account_id, trades, dry_run)


def _user_base_currency(db: Session, user_id: str) -> str:
    user = db.query(User).filter(User.id == user_id).first()
    return getattr(user, "functional_currency", "EUR") if user else "EUR"


def _trades_for_user(
    db: Session,
    user_id: str,
    account_id: Optional[str] = None,
    symbol: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> list[Trade]:
    """Load BrokerTrade rows scoped to the user, return as pure-engine `Trade` objects."""
    account_ids_subq = (
        db.query(Account.id)
        .filter(Account.user_id == user_id)
        .subquery()
    )
    q = db.query(BrokerTrade).filter(BrokerTrade.account_id.in_(account_ids_subq))
    if account_id:
        q = q.filter(BrokerTrade.account_id == account_id)
    if symbol:
        q = q.filter(BrokerTrade.symbol == symbol.upper())
    if start_date:
        q = q.filter(BrokerTrade.trade_date >= validate_date(start_date))
    if end_date:
        q = q.filter(BrokerTrade.trade_date <= validate_date(end_date))
    rows = q.order_by(BrokerTrade.trade_date, BrokerTrade.id).all()
    return [
        Trade(
            symbol=r.symbol,
            trade_date=r.trade_date,
            side=r.side,
            quantity=Decimal(r.quantity),
            price=Decimal(r.price),
            currency=r.currency,
            fees=Decimal(r.fees or 0),
        )
        for r in rows
    ]


def get_realized_pnl_impl(
    db: Session,
    user_id: str,
    account_id: Optional[str] = None,
    symbol: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> list[dict]:
    base = _user_base_currency(db, user_id)
    trades = _trades_for_user(db, user_id, account_id, symbol, start_date, end_date)
    if not trades:
        return []
    fx = ExchangeRateService(db)
    rows = realized_pnl_from_trades(trades, base_currency=base, fx_service=fx)
    return [_jsonify_pnl_row(r) for r in rows]


def get_realized_pnl(
    user_id: str,
    account_id: Optional[str] = None,
    symbol: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> list[dict]:
    with get_db() as db:
        return get_realized_pnl_impl(db, user_id, account_id, symbol, start_date, end_date)


def get_unrealized_pnl_impl(
    db: Session,
    user_id: str,
    account_id: Optional[str] = None,
    symbol: Optional[str] = None,
) -> list[dict]:
    base = _user_base_currency(db, user_id)
    trades = _trades_for_user(db, user_id, account_id, symbol)
    if not trades:
        return []

    # Latest valuation per symbol — pick most recent HoldingValuation joined to Holding
    holdings_q = db.query(Holding).filter(Holding.user_id == user_id)
    if account_id:
        holdings_q = holdings_q.filter(Holding.account_id == account_id)
    if symbol:
        holdings_q = holdings_q.filter(Holding.symbol == symbol.upper())
    holdings = holdings_q.all()

    valuations = _latest_valuations_for_user(db, user_id)
    latest_prices: dict[str, Decimal] = {}
    latest_dates: list[date] = []
    for h in holdings:
        v = valuations.get(h.id)
        if v is not None and v.price is not None:
            latest_prices[h.symbol] = Decimal(v.price)
            latest_dates.append(v.date)

    as_of = max(latest_dates) if latest_dates else date.today()

    fx = ExchangeRateService(db)
    rows = unrealized_pnl_from_trades(
        trades,
        base_currency=base,
        fx_service=fx,
        latest_prices=latest_prices,
        as_of_date=as_of,
    )
    return [_jsonify_pnl_row(r) for r in rows]


def get_unrealized_pnl(
    user_id: str,
    account_id: Optional[str] = None,
    symbol: Optional[str] = None,
) -> list[dict]:
    with get_db() as db:
        return get_unrealized_pnl_impl(db, user_id, account_id, symbol)


def _dec_str(v: Decimal) -> str:
    """Stringify a Decimal, stripping trailing zeros (e.g. '500' not '500.0000000000000000')."""
    normalized = v.normalize()
    # normalize() can produce scientific notation for very large/small values; use 'f' format
    return format(normalized, "f")


def _jsonify_pnl_row(row: dict) -> dict:
    """Convert Decimals to strings recursively for JSON-friendly output."""
    out = {}
    for k, v in row.items():
        if isinstance(v, Decimal):
            out[k] = _dec_str(v)
        elif isinstance(v, list):
            out[k] = [
                {kk: (_dec_str(vv) if isinstance(vv, Decimal) else vv) for kk, vv in item.items()}
                if isinstance(item, dict) else item
                for item in v
            ]
        else:
            out[k] = v
    return out
