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
from app.services.ownership_service import attribute_amount, entity_ids_for_people, get_owners
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
    person_ids: Optional[list[str]] = None,
) -> list[dict]:
    """List a user's holdings with latest valuation.

    When person_ids is provided, only holdings whose account_id is in the
    person-owned account set are returned. When exactly one person_id is given,
    current_value_user_currency is share-weighted to that person's ownership
    fraction (quantity is left unweighted so lot-level data remains intact).
    """
    # Resolve allowed accounts from person_ids
    filter_by_person = person_ids is not None and len(person_ids) > 0
    single_person = filter_by_person and len(person_ids) == 1
    allowed_account_ids: Optional[set] = None
    if filter_by_person:
        allowed_account_ids = set(
            str(uid) for uid in entity_ids_for_people(db, "account", person_ids)
        )
        if not allowed_account_ids:
            return []

    query = db.query(Holding).filter(Holding.user_id == user_id)
    if account_id:
        query = query.filter(Holding.account_id == account_id)
    if allowed_account_ids is not None:
        query = query.filter(Holding.account_id.in_(allowed_account_ids))
    holdings = query.order_by(Holding.symbol).all()

    valuations = _latest_valuations_for_user(db, user_id)

    # Cache owners per account for share-weighting
    owners_cache: dict = {}
    if single_person:
        for h in holdings:
            acc_id = str(h.account_id)
            if acc_id not in owners_cache:
                owners_cache[acc_id] = get_owners(db, "account", h.account_id)

    out = []
    for h in holdings:
        v = valuations.get(h.id)
        value_str = str(v.value_user_currency) if v else None
        if single_person and v is not None and v.value_user_currency is not None:
            owners = owners_cache[str(h.account_id)]
            weighted_value = attribute_amount(
                float(v.value_user_currency), owners, person_ids[0]
            )
            value_str = str(Decimal(str(weighted_value)))
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
                "current_value_user_currency": value_str,
                "is_stale": bool(v.is_stale) if v else None,
                "last_price_error": h.last_price_error,
            }
        )
    return out


def list_holdings(
    user_id: str,
    account_id: Optional[str] = None,
    person_ids: Optional[list[str]] = None,
) -> list[dict]:
    with get_db() as db:
        return list_holdings_impl(db, user_id, account_id, person_ids)


def get_portfolio_summary_impl(
    db: Session,
    user_id: str,
    person_ids: Optional[list[str]] = None,
) -> dict:
    """Aggregate portfolio value across the user's investment accounts.

    When person_ids is provided, only investment accounts owned by any of the
    specified people are included. When exactly one person_id is given, each
    account's value contribution is share-weighted by that person's ownership.
    """
    user = db.query(User).filter(User.id == user_id).first()
    currency = getattr(user, "functional_currency", "EUR") if user else "EUR"

    filter_by_person = person_ids is not None and len(person_ids) > 0
    single_person = filter_by_person and len(person_ids) == 1

    # Resolve allowed account ids from person ownership
    allowed_account_ids: Optional[set] = None
    if filter_by_person:
        allowed_account_ids = set(
            str(uid) for uid in entity_ids_for_people(db, "account", person_ids)
        )
        if not allowed_account_ids:
            return {
                "currency": currency,
                "total_value": "0",
                "holdings_count": 0,
                "stale_valuations": 0,
                "accounts": [],
            }

    accounts_query = (
        db.query(Account)
        .filter(
            Account.user_id == user_id,
            Account.account_type.in_(INVESTMENT_ACCOUNT_TYPES),
            Account.is_active == True,  # noqa: E712
        )
    )
    if allowed_account_ids is not None:
        accounts_query = accounts_query.filter(Account.id.in_(allowed_account_ids))
    accounts = accounts_query.all()
    account_ids = [a.id for a in accounts]

    valuations = _latest_valuations_for_user(db, user_id)

    # Cache owners per account for share-weighting
    owners_cache: dict = {}
    if single_person:
        for a in accounts:
            owners_cache[str(a.id)] = get_owners(db, "account", a.id)

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
        if single_person:
            owners = owners_cache[str(h.account_id)]
            val = Decimal(str(attribute_amount(float(val), owners, person_ids[0])))
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


def get_portfolio_summary(
    user_id: str,
    person_ids: Optional[list[str]] = None,
) -> dict:
    with get_db() as db:
        return get_portfolio_summary_impl(db, user_id, person_ids)


def get_portfolio_history_impl(
    db: Session,
    user_id: str,
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    person_ids: Optional[list[str]] = None,
) -> list[dict]:
    """Return daily portfolio value history (sum across investment accounts) in functional currency.

    When person_ids is provided, only investment accounts owned by any of the
    specified people are included. When exactly one person_id is given, each
    account's balance contribution is share-weighted by that person's ownership.
    """
    from_dt = validate_date(from_date)
    to_dt = validate_date(to_date)

    filter_by_person = person_ids is not None and len(person_ids) > 0
    single_person = filter_by_person and len(person_ids) == 1

    # Resolve allowed account ids from person ownership
    allowed_person_ids: Optional[set] = None
    if filter_by_person:
        allowed_person_ids = set(
            str(uid) for uid in entity_ids_for_people(db, "account", person_ids)
        )
        if not allowed_person_ids:
            return []

    accounts_query = (
        db.query(Account)
        .filter(
            Account.user_id == user_id,
            Account.account_type.in_(INVESTMENT_ACCOUNT_TYPES),
        )
    )
    if allowed_person_ids is not None:
        accounts_query = accounts_query.filter(Account.id.in_(allowed_person_ids))
    account_objs = accounts_query.all()
    account_ids = [a.id for a in account_objs]

    if not account_ids:
        return []

    # Cache owners per account for share-weighting
    owners_cache: dict = {}
    if single_person:
        for a in account_objs:
            owners_cache[str(a.id)] = get_owners(db, "account", a.id)

    query = db.query(AccountBalance).filter(AccountBalance.account_id.in_(account_ids))
    if from_dt:
        query = query.filter(AccountBalance.date >= from_dt)
    if to_dt:
        query = query.filter(AccountBalance.date <= to_dt)

    rows = query.order_by(AccountBalance.date).all()

    by_date: dict = {}
    for r in rows:
        key = r.date.isoformat() if hasattr(r.date, "isoformat") else str(r.date)
        val = Decimal(r.balance_in_functional_currency or 0)
        if single_person:
            owners = owners_cache.get(str(r.account_id), [])
            val = Decimal(str(attribute_amount(float(val), owners, person_ids[0])))
        by_date.setdefault(key, Decimal("0"))
        by_date[key] += val

    return [{"date": d, "value_user_currency": str(v)} for d, v in sorted(by_date.items())]


def get_portfolio_history(
    user_id: str,
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    person_ids: Optional[list[str]] = None,
) -> list[dict]:
    with get_db() as db:
        return get_portfolio_history_impl(db, user_id, from_date, to_date, person_ids)


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
    allowed_account_ids: Optional[set] = None,
) -> list[Trade]:
    """Load BrokerTrade rows scoped to the user, return as pure-engine `Trade` objects.

    allowed_account_ids: if provided, further restricts to those account IDs
    (used for person_ids ownership filtering).
    """
    account_ids_subq = (
        db.query(Account.id)
        .filter(Account.user_id == user_id)
        .subquery()
    )
    q = db.query(BrokerTrade).filter(BrokerTrade.account_id.in_(account_ids_subq))
    if account_id:
        q = q.filter(BrokerTrade.account_id == account_id)
    if allowed_account_ids is not None:
        q = q.filter(BrokerTrade.account_id.in_(allowed_account_ids))
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
    person_ids: Optional[list[str]] = None,
) -> list[dict]:
    # Resolve allowed accounts from person_ids
    allowed_account_ids: Optional[set] = None
    if person_ids is not None and len(person_ids) > 0:
        allowed_account_ids = set(
            str(uid) for uid in entity_ids_for_people(db, "account", person_ids)
        )
        if not allowed_account_ids:
            return []

    base = _user_base_currency(db, user_id)
    trades = _trades_for_user(
        db, user_id, account_id, symbol, start_date, end_date, allowed_account_ids
    )
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
    person_ids: Optional[list[str]] = None,
) -> list[dict]:
    with get_db() as db:
        return get_realized_pnl_impl(
            db, user_id, account_id, symbol, start_date, end_date, person_ids
        )


def get_unrealized_pnl_impl(
    db: Session,
    user_id: str,
    account_id: Optional[str] = None,
    symbol: Optional[str] = None,
    person_ids: Optional[list[str]] = None,
) -> list[dict]:
    # Resolve allowed accounts from person_ids
    allowed_account_ids: Optional[set] = None
    if person_ids is not None and len(person_ids) > 0:
        allowed_account_ids = set(
            str(uid) for uid in entity_ids_for_people(db, "account", person_ids)
        )
        if not allowed_account_ids:
            return []

    base = _user_base_currency(db, user_id)
    trades = _trades_for_user(db, user_id, account_id, symbol, allowed_account_ids=allowed_account_ids)
    if not trades:
        return []

    # Latest valuation per symbol — pick most recent HoldingValuation joined to Holding
    holdings_q = db.query(Holding).filter(Holding.user_id == user_id)
    if account_id:
        holdings_q = holdings_q.filter(Holding.account_id == account_id)
    if allowed_account_ids is not None:
        holdings_q = holdings_q.filter(Holding.account_id.in_(allowed_account_ids))
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
    person_ids: Optional[list[str]] = None,
) -> list[dict]:
    with get_db() as db:
        return get_unrealized_pnl_impl(db, user_id, account_id, symbol, person_ids)


def get_holding_trades_impl(db: Session, user_id: str, holding_id: str) -> list[dict]:
    """Return broker trades behind a holding, chronologically, with running quantity."""
    holding = (
        db.query(Holding)
        .filter(Holding.id == holding_id, Holding.user_id == user_id)
        .first()
    )
    if not holding:
        return []
    trades = (
        db.query(BrokerTrade)
        .filter(
            BrokerTrade.account_id == holding.account_id,
            BrokerTrade.symbol == holding.symbol,
        )
        .order_by(BrokerTrade.trade_date.asc(), BrokerTrade.id.asc())
        .all()
    )
    out: list[dict] = []
    running = Decimal("0")
    for t in trades:
        qty = Decimal(t.quantity)
        price = Decimal(t.price)
        fees = Decimal(t.fees or 0)
        if t.side == "buy":
            running += qty
            cost_native = qty * price + fees
            proceeds_native = None
        else:
            running -= qty
            cost_native = None
            proceeds_native = qty * price - fees
        out.append(
            {
                "id": str(t.id),
                "trade_date": t.trade_date.isoformat(),
                "symbol": t.symbol,
                "side": t.side,
                "quantity": _dec_str_local(qty),
                "price": _dec_str_local(price),
                "currency": t.currency,
                "fees": _dec_str_local(fees),
                "external_id": t.external_id,
                "cost_native": _dec_str_local(cost_native) if cost_native is not None else None,
                "proceeds_native": _dec_str_local(proceeds_native) if proceeds_native is not None else None,
                "running_quantity": _dec_str_local(running),
            }
        )
    return out


def get_holding_trades(user_id: str, holding_id: str) -> list[dict]:
    with get_db() as db:
        return get_holding_trades_impl(db, user_id, holding_id)


def _dec_str_local(v: Decimal) -> str:
    return format(v.normalize(), "f")


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
