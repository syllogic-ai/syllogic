"""REST endpoints for investment connections, holdings, and portfolio."""
from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Optional
from uuid import UUID

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
    BrokerConnection,
    Holding,
    HoldingValuation,
    User,
)
from app.schemas import (
    BrokerConnectionCreate,
    HoldingCreate,
    HoldingUpdate,
    HoldingResponse,
    ManualAccountCreate,
    PortfolioSummary,
    SymbolSearchResult,
    ValuationPoint,
)
from app.services import credentials_crypto

logger = __import__("logging").getLogger(__name__)

# ---------------------------------------------------------------------------
# Helper: in-process sync (FastAPI BackgroundTask, no Celery/Redis required)
# ---------------------------------------------------------------------------


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
    from app.services.exchange_rate_service import ExchangeRateService

    class _FxAdapter:
        def __init__(self, db):
            self._svc = ExchangeRateService(db=db)

        def convert(self, amount, src, dst, on):
            if src.upper() == dst.upper():
                return amount
            result = self._svc.convert_amount(
                amount=amount, from_currency=src, to_currency=dst, for_date=on,
            )
            return result if result is not None else amount

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


# ---------------------------------------------------------------------------
# Broker connections
# ---------------------------------------------------------------------------


@router.post("/broker-connections")
def create_broker_connection(
    payload: BrokerConnectionCreate,
    background_tasks: BackgroundTasks,
    user_id: Optional[str] = None,
    db: Session = Depends(get_db),
):
    user_id = get_user_id(user_id)

    # Create the underlying brokerage account.
    account = Account(
        user_id=user_id,
        name=payload.account_name,
        account_type="investment_brokerage",
        currency=payload.base_currency,
        provider=payload.provider,
    )
    db.add(account)
    db.flush()

    creds = {
        "flex_token": payload.flex_token,
        "query_id_positions": payload.query_id_positions,
        "query_id_trades": payload.query_id_trades,
    }
    encrypted = credentials_crypto.encrypt(creds)

    conn = BrokerConnection(
        user_id=user_id,
        account_id=account.id,
        provider=payload.provider,
        credentials_encrypted=encrypted,
        last_sync_status="pending",
    )
    db.add(conn)
    db.commit()
    db.refresh(conn)

    # Kick off background sync.
    background_tasks.add_task(_run_sync_in_process, account.id)

    return {
        "connection_id": str(conn.id),
        "account_id": str(account.id),
        "provider": conn.provider,
        "last_sync_status": conn.last_sync_status,
    }


@router.get("/broker-connections")
def list_broker_connections(
    user_id: Optional[str] = None,
    db: Session = Depends(get_db),
):
    user_id = get_user_id(user_id)
    conns = db.query(BrokerConnection).filter(BrokerConnection.user_id == user_id).all()
    return [
        {
            "id": str(c.id),
            "account_id": str(c.account_id),
            "provider": c.provider,
            "last_sync_at": c.last_sync_at.isoformat() if c.last_sync_at else None,
            "last_sync_status": c.last_sync_status,
            "last_sync_error": c.last_sync_error,
        }
        for c in conns
    ]


@router.post("/broker-connections/{connection_id}/sync")
def trigger_sync(
    connection_id: UUID,
    background_tasks: BackgroundTasks,
    user_id: Optional[str] = None,
    db: Session = Depends(get_db),
):
    user_id = get_user_id(user_id)
    conn = (
        db.query(BrokerConnection)
        .filter(BrokerConnection.id == connection_id, BrokerConnection.user_id == user_id)
        .first()
    )
    if not conn:
        raise HTTPException(status_code=404, detail="Broker connection not found")
    background_tasks.add_task(_run_sync_in_process, conn.account_id)
    return {"status": "queued", "account_id": str(conn.account_id)}


@router.post("/sync-all")
def trigger_sync_all(
    background_tasks: BackgroundTasks,
    user_id: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """Queue a price-refresh sync for every active investment account belonging
    to the user (manual + brokerage). Uses Celery when Redis is available,
    otherwise falls back to FastAPI BackgroundTasks (in-process)."""
    user_id = get_user_id(user_id)
    accounts = (
        db.query(Account)
        .filter(
            Account.user_id == user_id,
            Account.is_active.is_(True),
            Account.account_type.in_(["investment_manual", "investment_brokerage"]),
        )
        .all()
    )
    for account in accounts:
        background_tasks.add_task(_run_sync_in_process, account.id)
    return {"status": "queued", "count": len(accounts)}


@router.delete("/broker-connections/{connection_id}", status_code=204)
def delete_broker_connection(
    connection_id: UUID,
    user_id: Optional[str] = None,
    db: Session = Depends(get_db),
):
    user_id = get_user_id(user_id)
    conn = (
        db.query(BrokerConnection)
        .filter(BrokerConnection.id == connection_id, BrokerConnection.user_id == user_id)
        .first()
    )
    if not conn:
        raise HTTPException(status_code=404, detail="Broker connection not found")
    db.delete(conn)
    db.commit()
    return None


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
    account = (
        db.query(Account)
        .filter(Account.id == account_id, Account.user_id == user_id)
        .first()
    )
    if not account or account.account_type != "investment_manual":
        raise HTTPException(status_code=404, detail="Manual investment account not found")

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
    db.add(holding)
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
    user_currency = (
        getattr(user, "functional_currency", None) or "EUR"
    ).upper()

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
        cost_basis_user = _convert_cost_to_user(
            h.avg_cost, h.quantity, h.currency, h.as_of_date
        )
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
    holding = (
        db.query(Holding)
        .filter(Holding.id == holding_id, Holding.user_id == user_id)
        .first()
    )
    if not holding:
        raise HTTPException(status_code=404, detail="Holding not found")
    if holding.source != "manual":
        raise HTTPException(status_code=400, detail="Only manual holdings can be edited")

    payload = updates.model_dump(exclude_unset=True)
    lookup_changed = (
        ("symbol" in payload and payload["symbol"] != holding.symbol)
        or ("provider_symbol" in payload and payload["provider_symbol"] != holding.provider_symbol)
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
    holding = (
        db.query(Holding)
        .filter(Holding.id == holding_id, Holding.user_id == user_id)
        .first()
    )
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
            Account.account_type.in_(["investment_brokerage", "investment_manual"]),
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
                allocation_by_type[h.instrument_type] = (
                    allocation_by_type.get(h.instrument_type, Decimal("0"))
                    + Decimal(latest.value_user_currency)
                )
                allocation_by_currency[h.currency] = (
                    allocation_by_currency.get(h.currency, Decimal("0"))
                    + Decimal(latest.value_user_currency)
                )

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
                today_change += Decimal(
                    latest_balance.balance_in_functional_currency
                ) - Decimal(prior_balance.balance_in_functional_currency)

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
    holding = (
        db.query(Holding)
        .filter(Holding.id == holding_id, Holding.user_id == user_id)
        .first()
    )
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
    return [
        ValuationPoint(date=r.date, value=Decimal(r.value_user_currency))
        for r in rows
    ]


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
            Account.account_type.in_(["investment_brokerage", "investment_manual"]),
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
