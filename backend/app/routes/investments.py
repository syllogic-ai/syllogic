"""REST endpoints for investment connections, holdings, and portfolio."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Optional
from uuid import UUID, uuid4

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from sqlalchemy import desc
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import get_db
from app.db_helpers import get_user_id
from app.integrations.price_provider import get_price_provider
from app.models import (
    Account,
    AccountBalance,
    BrokerTrade,
    Holding,
    HoldingValuation,
    PriceSnapshot,
    Transaction,
    User,
)
from app.schemas import (
    HoldingBuy,
    HoldingCreate,
    HoldingLot,
    HoldingSell,
    HoldingTrade,
    HoldingUpdate,
    HoldingResponse,
    ManualAccountCreate,
    PortfolioSummary,
    SymbolSearchResult,
    ValuationPoint,
)
from app.services.account_balance_service import AccountBalanceService

# Account types that hold investments, not spendable cash — excluded as a
# funding source for a purchase.
_INVESTMENT_ACCOUNT_TYPES = {"investment", "investment_manual"}

logger = __import__("logging").getLogger(__name__)

# ---------------------------------------------------------------------------
# Helper: in-process sync (FastAPI BackgroundTask, no Celery/Redis required)
# ---------------------------------------------------------------------------


class _FxAdapter:
    def __init__(self, db):
        from app.services.exchange_rate_service import ExchangeRateService

        self._svc = ExchangeRateService(db=db)

    def convert(self, amount, src, dst, on):
        if src.upper() == dst.upper():
            return amount
        result = self._svc.convert_amount(
            amount=amount,
            from_currency=src,
            to_currency=dst,
            for_date=on,
        )
        return result if result is not None else amount


def _seed_price_snapshot(db: Session, symbol: str, price: Decimal, currency: str, on: date) -> None:
    """Record the trade price as `symbol`'s latest cached price, so the
    holding values against it immediately instead of waiting on the next
    background sync's external price fetch. A trade is the freshest price
    observation available, so this overwrites same-day snapshots too
    (including one from an earlier trade today); a later background sync
    still supersedes it with the real market close."""
    existing = db.query(PriceSnapshot).filter_by(symbol=symbol, date=on).first()
    if existing is not None:
        existing.close = price
        existing.currency = currency
        existing.provider = "manual"
    else:
        db.add(
            PriceSnapshot(symbol=symbol, currency=currency, date=on, close=price, provider="manual")
        )


def _revalue_account_now(db: Session, account_id: UUID) -> None:
    """Synchronously recompute this account's holding valuations and
    balance, so a buy/sell response reflects the trade immediately rather
    than waiting for the async background sync."""
    from app.services.holding_valuation_service import HoldingValuationService

    HoldingValuationService(db=db, fx=_FxAdapter(db)).compute(account_id, date.today())


def _run_sync_in_process(account_id: UUID) -> None:
    """Sync one investment account in the FastAPI worker process.

    Used as a FastAPI BackgroundTask for user-triggered refreshes so the
    result is guaranteed regardless of whether the Celery broker is
    reachable from the backend service (scheduled nightly syncs still go
    through Celery beat → worker as before).
    """
    from uuid import UUID as _UUID
    from app.database import SessionLocal
    from app.services.investment_sync_service import InvestmentSyncService

    logger.info("[INVESTMENT_SYNC] Starting in-process sync for account %s", account_id)
    db = SessionLocal()
    try:
        svc = InvestmentSyncService(db=db, fx=_FxAdapter(db))
        svc.sync_account(_UUID(str(account_id)))
        logger.info("[INVESTMENT_SYNC] Completed in-process sync for account %s", account_id)
    except Exception:
        logger.exception("[INVESTMENT_SYNC] Failed in-process sync for account %s", account_id)
    finally:
        db.close()


router = APIRouter()


@router.post("/sync-all")
def trigger_sync_all(
    background_tasks: BackgroundTasks,
    user_id: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """Queue a price-refresh sync for every active manual investment account
    belonging to the user. Uses Celery when Redis is available, otherwise
    falls back to FastAPI BackgroundTasks (in-process)."""
    user_id = get_user_id(user_id)
    accounts = (
        db.query(Account)
        .filter(
            Account.user_id == user_id,
            Account.is_active.is_(True),
            Account.account_type == "investment_manual",
        )
        .all()
    )
    for account in accounts:
        background_tasks.add_task(_run_sync_in_process, account.id)
    return {"status": "queued", "count": len(accounts)}


# ---------------------------------------------------------------------------
# Manual investment accounts
# ---------------------------------------------------------------------------


@router.post("/manual-accounts")
def create_manual_account(
    payload: ManualAccountCreate,
    user_id: Optional[str] = None,
    db: Session = Depends(get_db),
):
    user_id = get_user_id(user_id)
    account = Account(
        user_id=user_id,
        name=payload.name,
        account_type="investment_manual",
        currency=payload.base_currency,
        provider="manual",
    )
    db.add(account)
    db.commit()
    db.refresh(account)
    return {
        "account_id": str(account.id),
        "name": account.name,
        "currency": account.currency,
    }


@router.post("/manual-accounts/{account_id}/holdings")
def create_manual_holding(
    account_id: UUID,
    payload: HoldingCreate,
    background_tasks: BackgroundTasks,
    user_id: Optional[str] = None,
    db: Session = Depends(get_db),
):
    user_id = get_user_id(user_id)
    account = db.query(Account).filter(Account.id == account_id, Account.user_id == user_id).first()
    if not account or account.account_type != "investment_manual":
        raise HTTPException(status_code=404, detail="Manual investment account not found")

    funding_account = (
        db.query(Account)
        .filter(Account.id == payload.funding_account_id, Account.user_id == user_id)
        .first()
    )
    if not funding_account:
        raise HTTPException(status_code=404, detail="Funding account not found")
    if funding_account.account_type in _INVESTMENT_ACCOUNT_TYPES:
        raise HTTPException(
            status_code=400,
            detail="Funding account must be a cash account, not an investment account",
        )
    if funding_account.currency != payload.currency:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Funding account currency ({funding_account.currency}) must match "
                f"the holding currency ({payload.currency})"
            ),
        )

    cost = payload.quantity * payload.avg_cost

    # Resolve symbol metadata via the price provider.
    name: Optional[str] = None
    try:
        provider = get_price_provider()
        matches = provider.search_symbols(payload.symbol)
        if matches:
            top = matches[0]
            name = getattr(top, "name", None)
    except Exception:
        # Symbol lookup is best-effort; do not fail the holding creation.
        name = None

    holding = Holding(
        user_id=user_id,
        account_id=account.id,
        symbol=payload.symbol,
        provider_symbol=payload.provider_symbol or None,
        name=name,
        currency=payload.currency,
        instrument_type=payload.instrument_type,
        quantity=payload.quantity,
        avg_cost=payload.avg_cost,
        as_of_date=payload.as_of_date,
        source="manual",
    )
    funding_transaction = Transaction(
        user_id=user_id,
        account_id=funding_account.id,
        transaction_type="debit",
        amount=-cost,
        currency=funding_account.currency,
        description=f"Investment purchase: {payload.symbol}",
        booked_at=datetime.now(timezone.utc),
        pending=False,
        include_in_analytics=False,
    )
    db.add(holding)
    db.add(funding_transaction)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail=(
                f"A {payload.instrument_type} holding for {payload.symbol} already "
                "exists in this account. Edit the existing holding instead of adding a new one."
            ),
        )
    db.refresh(holding)

    AccountBalanceService(db).calculate_account_balances(
        user_id, account_ids=[str(funding_account.id)]
    )

    # Trigger an async revaluation so the new holding gets priced.
    background_tasks.add_task(_run_sync_in_process, account.id)

    return {
        "holding_id": str(holding.id),
        "account_id": str(account.id),
        "symbol": holding.symbol,
        "name": holding.name,
        "quantity": str(holding.quantity),
    }


# ---------------------------------------------------------------------------
# Buy / sell against an account's in-portfolio cash balance
# ---------------------------------------------------------------------------


def _find_cash_holding(db: Session, account_id: UUID, currency: str) -> Optional[Holding]:
    return (
        db.query(Holding)
        .filter(
            Holding.account_id == account_id,
            Holding.instrument_type == "cash",
            Holding.currency == currency,
        )
        .first()
    )


@router.post("/manual-accounts/{account_id}/holdings/buy")
def buy_holding(
    account_id: UUID,
    payload: HoldingBuy,
    background_tasks: BackgroundTasks,
    user_id: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """Buy an equity/ETF using cash already held (as a "cash" holding) in
    this investment account — no external funding account involved."""
    user_id = get_user_id(user_id)
    account = db.query(Account).filter(Account.id == account_id, Account.user_id == user_id).first()
    if not account or account.account_type != "investment_manual":
        raise HTTPException(status_code=404, detail="Manual investment account not found")

    cost = payload.quantity * payload.price

    cash_holding = _find_cash_holding(db, account.id, payload.currency)
    available = Decimal(cash_holding.quantity) if cash_holding else Decimal("0")
    if cash_holding is None or available < cost:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Not enough {payload.currency} cash in this account to buy "
                f"{payload.symbol}. Available: {available}, required: {cost}"
            ),
        )

    existing = (
        db.query(Holding)
        .filter(
            Holding.account_id == account.id,
            Holding.symbol == payload.symbol,
            Holding.instrument_type == payload.instrument_type,
        )
        .first()
    )
    if existing is not None and existing.source != "manual":
        raise HTTPException(
            status_code=400,
            detail="This symbol is tracked by a synced source and cannot be traded manually",
        )

    name: Optional[str] = None
    try:
        provider = get_price_provider()
        matches = provider.search_symbols(payload.symbol)
        if matches:
            name = getattr(matches[0], "name", None)
    except Exception:
        name = None

    cash_holding.quantity = available - cost

    if existing is not None:
        old_qty = Decimal(existing.quantity)
        old_cost = Decimal(existing.avg_cost) if existing.avg_cost is not None else Decimal("0")
        new_qty = old_qty + payload.quantity
        existing.avg_cost = ((old_qty * old_cost) + cost) / new_qty
        existing.quantity = new_qty
        existing.as_of_date = payload.as_of_date or existing.as_of_date
        if payload.provider_symbol:
            existing.provider_symbol = payload.provider_symbol
        holding = existing
    else:
        holding = Holding(
            user_id=user_id,
            account_id=account.id,
            symbol=payload.symbol,
            provider_symbol=payload.provider_symbol or None,
            name=name,
            currency=payload.currency,
            instrument_type=payload.instrument_type,
            quantity=payload.quantity,
            avg_cost=payload.price,
            as_of_date=payload.as_of_date,
            source="manual",
        )
        db.add(holding)

    trade_date = payload.as_of_date or date.today()
    db.add(
        BrokerTrade(
            account_id=account.id,
            symbol=payload.symbol,
            trade_date=trade_date,
            side="buy",
            quantity=payload.quantity,
            price=payload.price,
            currency=payload.currency,
            external_id=f"manual:{uuid4()}",
        )
    )

    db.commit()
    db.refresh(holding)
    db.refresh(cash_holding)

    _seed_price_snapshot(
        db,
        holding.provider_symbol or holding.symbol,
        payload.price,
        payload.currency,
        date.today(),
    )
    _revalue_account_now(db, account.id)
    db.refresh(holding)
    db.refresh(cash_holding)

    # A later background sync fetches the real market close for `symbol`
    # and supersedes the trade-price placeholder seeded above.
    background_tasks.add_task(_run_sync_in_process, account.id)

    return {
        "holding_id": str(holding.id),
        "account_id": str(account.id),
        "symbol": holding.symbol,
        "quantity": str(holding.quantity),
        "avg_cost": str(holding.avg_cost),
        "cash_remaining": str(cash_holding.quantity),
    }


@router.post("/holdings/{holding_id}/sell")
def sell_holding(
    holding_id: UUID,
    payload: HoldingSell,
    background_tasks: BackgroundTasks,
    user_id: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """Sell (fully or partially) an equity/ETF holding, crediting the
    proceeds back to the matching-currency "cash" holding in the same
    investment account (creating one if it doesn't exist yet)."""
    user_id = get_user_id(user_id)
    holding = db.query(Holding).filter(Holding.id == holding_id, Holding.user_id == user_id).first()
    if not holding:
        raise HTTPException(status_code=404, detail="Holding not found")
    if holding.source != "manual":
        raise HTTPException(status_code=400, detail="Only manual holdings can be sold")
    if holding.instrument_type == "cash":
        raise HTTPException(status_code=400, detail="Cash holdings cannot be sold")

    current_qty = Decimal(holding.quantity)
    if payload.quantity > current_qty:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot sell {payload.quantity} {holding.symbol} — only {current_qty} held",
        )

    account_id = holding.account_id
    symbol = holding.symbol
    lookup_symbol = holding.provider_symbol or holding.symbol
    currency = holding.currency
    proceeds = payload.quantity * payload.price

    cash_holding = _find_cash_holding(db, account_id, holding.currency)
    if cash_holding is not None:
        cash_holding.quantity = Decimal(cash_holding.quantity) + proceeds
    else:
        cash_holding = Holding(
            user_id=user_id,
            account_id=account_id,
            symbol=holding.currency,
            name=f"Cash ({holding.currency})",
            currency=holding.currency,
            instrument_type="cash",
            quantity=proceeds,
            avg_cost=Decimal("1"),
            as_of_date=payload.as_of_date or date.today(),
            source="manual",
        )
        db.add(cash_holding)

    remaining_qty = current_qty - payload.quantity
    sold_out = remaining_qty == 0
    if sold_out:
        db.delete(holding)
    else:
        holding.quantity = remaining_qty
        holding.as_of_date = payload.as_of_date or holding.as_of_date

    trade_date = payload.as_of_date or date.today()
    db.add(
        BrokerTrade(
            account_id=account_id,
            symbol=symbol,
            trade_date=trade_date,
            side="sell",
            quantity=payload.quantity,
            price=payload.price,
            currency=currency,
            external_id=f"manual:{uuid4()}",
        )
    )

    db.commit()
    db.refresh(cash_holding)

    _seed_price_snapshot(db, lookup_symbol, payload.price, currency, date.today())
    _revalue_account_now(db, account_id)
    db.refresh(cash_holding)

    background_tasks.add_task(_run_sync_in_process, account_id)

    return {
        "holding_id": str(holding_id),
        "sold_out": sold_out,
        "remaining_quantity": str(remaining_qty),
        "cash_balance": str(cash_holding.quantity),
    }


# ---------------------------------------------------------------------------
# Holdings
# ---------------------------------------------------------------------------


@router.get("/holdings", response_model=list[HoldingResponse])
def list_holdings(
    account_id: Optional[UUID] = None,
    user_id: Optional[str] = None,
    db: Session = Depends(get_db),
):
    user_id = get_user_id(user_id)
    user = db.query(User).filter(User.id == user_id).first()
    user_currency = (getattr(user, "functional_currency", None) or "EUR").upper()

    from app.services.exchange_rate_service import ExchangeRateService

    fx_svc = ExchangeRateService(db=db)

    def _convert_cost_to_user(
        avg_cost: Optional[Decimal],
        qty: Decimal,
        src_currency: str,
        on: Optional[date],
    ) -> Optional[Decimal]:
        if avg_cost is None:
            return None
        cost_native = Decimal(avg_cost) * Decimal(qty)
        src = (src_currency or user_currency).upper()
        if src == user_currency:
            return cost_native.quantize(Decimal("0.01"))
        for_date = on or date.today()
        # Use the fallback resolver: DB → yfinance backfill at as_of date →
        # today's FX. Avoids `cost_basis_user_currency = null` (which
        # makes the dashboard render P&L as "—") for older as_of dates
        # that don't have FX history yet.
        rate = fx_svc.get_exchange_rate_with_fallback(
            base_currency=src,
            target_currency=user_currency,
            for_date=for_date,
        )
        if rate is None:
            return None
        return (cost_native * Decimal(rate)).quantize(Decimal("0.01"))

    query = db.query(Holding).filter(Holding.user_id == user_id)
    if account_id is not None:
        query = query.filter(Holding.account_id == account_id)

    results: list[HoldingResponse] = []
    for h in query.all():
        latest_val = (
            db.query(HoldingValuation)
            .filter(HoldingValuation.holding_id == h.id)
            .order_by(desc(HoldingValuation.date))
            .first()
        )
        cost_basis_user = _convert_cost_to_user(h.avg_cost, h.quantity, h.currency, h.as_of_date)
        results.append(
            HoldingResponse(
                id=h.id,
                account_id=h.account_id,
                symbol=h.symbol,
                provider_symbol=h.provider_symbol,
                name=h.name,
                currency=h.currency,
                instrument_type=h.instrument_type,
                quantity=h.quantity,
                avg_cost=h.avg_cost,
                as_of_date=h.as_of_date,
                source=h.source,
                current_price=latest_val.price if latest_val else None,
                current_value_user_currency=(
                    latest_val.value_user_currency if latest_val else None
                ),
                cost_basis_user_currency=cost_basis_user,
                is_stale=bool(latest_val.is_stale) if latest_val else False,
            )
        )
    return results


@router.patch("/holdings/{holding_id}")
def update_holding(
    holding_id: UUID,
    updates: HoldingUpdate,
    background_tasks: BackgroundTasks,
    user_id: Optional[str] = None,
    db: Session = Depends(get_db),
):
    user_id = get_user_id(user_id)
    holding = db.query(Holding).filter(Holding.id == holding_id, Holding.user_id == user_id).first()
    if not holding:
        raise HTTPException(status_code=404, detail="Holding not found")
    if holding.source != "manual":
        raise HTTPException(status_code=400, detail="Only manual holdings can be edited")

    payload = updates.model_dump(exclude_unset=True)
    lookup_changed = ("symbol" in payload and payload["symbol"] != holding.symbol) or (
        "provider_symbol" in payload and payload["provider_symbol"] != holding.provider_symbol
    )
    for field, value in payload.items():
        setattr(holding, field, value)
    db.commit()
    db.refresh(holding)

    # Re-price the account if the lookup symbol changed so the new ticker
    # gets fetched from the price provider immediately.
    if lookup_changed:
        background_tasks.add_task(_run_sync_in_process, holding.account_id)

    return {"id": str(holding.id), "symbol": holding.symbol, "quantity": str(holding.quantity)}


@router.delete("/holdings/{holding_id}", status_code=204)
def delete_holding(
    holding_id: UUID,
    user_id: Optional[str] = None,
    db: Session = Depends(get_db),
):
    user_id = get_user_id(user_id)
    holding = db.query(Holding).filter(Holding.id == holding_id, Holding.user_id == user_id).first()
    if not holding:
        raise HTTPException(status_code=404, detail="Holding not found")
    if holding.source != "manual":
        raise HTTPException(status_code=400, detail="Only manual holdings can be deleted")
    db.delete(holding)
    db.commit()
    return None


# ---------------------------------------------------------------------------
# Portfolio
# ---------------------------------------------------------------------------


@router.get("/portfolio/summary", response_model=PortfolioSummary)
def portfolio_summary(
    user_id: Optional[str] = None,
    db: Session = Depends(get_db),
):
    user_id = get_user_id(user_id)
    user = db.query(User).filter(User.id == user_id).first()
    currency = getattr(user, "functional_currency", "EUR") or "EUR"

    accounts = (
        db.query(Account)
        .filter(
            Account.user_id == user_id,
            Account.account_type == "investment_manual",
        )
        .all()
    )

    total_value = Decimal("0")
    today_change = Decimal("0")
    allocation_by_type: dict[str, Decimal] = {}
    allocation_by_currency: dict[str, Decimal] = {}
    accounts_payload: list[dict] = []

    for account in accounts:
        # Account total = sum of latest valuations across its holdings.
        account_value = Decimal("0")
        holdings = db.query(Holding).filter(Holding.account_id == account.id).all()
        for h in holdings:
            latest = (
                db.query(HoldingValuation)
                .filter(HoldingValuation.holding_id == h.id)
                .order_by(desc(HoldingValuation.date))
                .first()
            )
            if latest:
                account_value += Decimal(latest.value_user_currency)
                allocation_by_type[h.instrument_type] = allocation_by_type.get(
                    h.instrument_type, Decimal("0")
                ) + Decimal(latest.value_user_currency)
                allocation_by_currency[h.currency] = allocation_by_currency.get(
                    h.currency, Decimal("0")
                ) + Decimal(latest.value_user_currency)

        total_value += account_value

        # Today change: today's snapshot vs the immediately prior snapshot.
        # Skip if no snapshot for today (e.g. weekend, holiday, missed Celery run)
        # so we don't surface a stale delta as "today's" movement.
        today_iso = date.today()
        latest_balance = (
            db.query(AccountBalance)
            .filter(
                AccountBalance.account_id == account.id,
                AccountBalance.date == today_iso,
            )
            .order_by(desc(AccountBalance.date))
            .first()
        )
        if latest_balance is not None:
            prior_balance = (
                db.query(AccountBalance)
                .filter(
                    AccountBalance.account_id == account.id,
                    AccountBalance.date < today_iso,
                )
                .order_by(desc(AccountBalance.date))
                .first()
            )
            if prior_balance is not None:
                today_change += Decimal(latest_balance.balance_in_functional_currency) - Decimal(
                    prior_balance.balance_in_functional_currency
                )

        accounts_payload.append(
            {
                "id": str(account.id),
                "name": account.name,
                "type": account.account_type,
                "currency": account.currency,
                "value": str(account_value),
            }
        )

    return PortfolioSummary(
        total_value=total_value,
        total_value_today_change=today_change,
        currency=currency,
        accounts=accounts_payload,
        allocation_by_type=allocation_by_type,
        allocation_by_currency=allocation_by_currency,
    )


@router.get("/holdings/{holding_id}/history", response_model=list[ValuationPoint])
def holding_history(
    holding_id: UUID,
    days: int = Query(30, ge=1, le=3650),
    user_id: Optional[str] = None,
    db: Session = Depends(get_db),
):
    user_id = get_user_id(user_id)
    holding = db.query(Holding).filter(Holding.id == holding_id, Holding.user_id == user_id).first()
    if not holding:
        raise HTTPException(status_code=404, detail="Holding not found")
    cutoff = date.today() - timedelta(days=days)
    rows = (
        db.query(HoldingValuation)
        .filter(
            HoldingValuation.holding_id == holding_id,
            HoldingValuation.date >= cutoff,
        )
        .order_by(HoldingValuation.date.asc())
        .all()
    )
    return [ValuationPoint(date=r.date, value=Decimal(r.value_user_currency)) for r in rows]


@router.get("/portfolio/history", response_model=list[ValuationPoint])
def portfolio_history(
    days: int = Query(30, ge=1, le=3650),
    user_id: Optional[str] = None,
    db: Session = Depends(get_db),
):
    user_id = get_user_id(user_id)
    cutoff = date.today() - timedelta(days=days)

    accounts = (
        db.query(Account.id)
        .filter(
            Account.user_id == user_id,
            Account.account_type == "investment_manual",
        )
        .all()
    )
    account_ids = [a.id for a in accounts]
    if not account_ids:
        return []

    rows = (
        db.query(AccountBalance)
        .filter(
            AccountBalance.account_id.in_(account_ids),
            AccountBalance.date >= cutoff,
        )
        .order_by(AccountBalance.date.asc())
        .all()
    )

    by_date: dict[date, Decimal] = {}
    for r in rows:
        d = r.date.date() if isinstance(r.date, datetime) else r.date
        by_date[d] = by_date.get(d, Decimal("0")) + Decimal(r.balance_in_functional_currency)

    return [ValuationPoint(date=d, value=v) for d, v in sorted(by_date.items())]


@router.get("/holdings/{holding_id}/trades", response_model=list[HoldingTrade])
def holding_trades(
    holding_id: UUID,
    user_id: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """Manual holdings return their buy/sell history recorded by the
    buy/sell routes. Other sources (broker-import) have no trade ledger
    yet, so this returns an empty list for them."""
    user_id = get_user_id(user_id)
    holding = db.query(Holding).filter(Holding.id == holding_id, Holding.user_id == user_id).first()
    if not holding:
        raise HTTPException(status_code=404, detail="Holding not found")
    if holding.source != "manual":
        return []

    rows = (
        db.query(BrokerTrade)
        .filter(BrokerTrade.account_id == holding.account_id, BrokerTrade.symbol == holding.symbol)
        .order_by(BrokerTrade.trade_date.asc(), BrokerTrade.created_at.asc())
        .all()
    )

    out: list[HoldingTrade] = []
    running_qty = Decimal("0")
    for t in rows:
        qty = Decimal(t.quantity)
        price = Decimal(t.price)
        running_qty = running_qty + qty if t.side == "buy" else running_qty - qty
        out.append(
            HoldingTrade(
                id=t.id,
                trade_date=t.trade_date,
                symbol=t.symbol,
                side=t.side,
                quantity=qty,
                price=price,
                currency=t.currency,
                fees=Decimal("0"),
                external_id=t.external_id,
                cost_native=qty * price if t.side == "buy" else None,
                proceeds_native=qty * price if t.side == "sell" else None,
                running_quantity=running_qty,
            )
        )
    out.reverse()
    return out


@router.get("/holdings/{holding_id}/lots", response_model=list[HoldingLot])
def holding_lots(
    holding_id: UUID,
    user_id: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """Manual holdings have no trade-import data source, so there are no
    FIFO lots to compute — always returns an empty list once the holding's
    existence is confirmed."""
    user_id = get_user_id(user_id)
    holding = db.query(Holding).filter(Holding.id == holding_id, Holding.user_id == user_id).first()
    if not holding:
        raise HTTPException(status_code=404, detail="Holding not found")
    return []


# ---------------------------------------------------------------------------
# Symbol search
# ---------------------------------------------------------------------------


@router.get("/symbols/search", response_model=list[SymbolSearchResult])
def search_symbols(q: str = Query(..., min_length=1)):
    provider = get_price_provider()
    matches = provider.search_symbols(q)
    return [
        SymbolSearchResult(
            symbol=getattr(m, "symbol", ""),
            name=getattr(m, "name", ""),
            exchange=getattr(m, "exchange", None),
            currency=getattr(m, "currency", None),
        )
        for m in matches
    ]
