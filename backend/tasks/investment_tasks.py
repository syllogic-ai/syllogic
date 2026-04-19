from __future__ import annotations
from datetime import date
import logging
from uuid import UUID
from celery import shared_task

from app.database import SessionLocal
from app.models import Account, BrokerConnection
from app.services.investment_sync_service import InvestmentSyncService
from app.services.exchange_rate_service import ExchangeRateService
from app.integrations.ibkr_flex_adapter import FlexStatementNotReady

logger = logging.getLogger(__name__)


class _FxAdapter:
    """Adapts ExchangeRateService.convert_amount to the FxConverter protocol."""
    def __init__(self, db):
        self.db = db
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


@shared_task(name="tasks.investment_tasks.daily_investment_sync_all")
def daily_investment_sync_all() -> dict:
    db = SessionLocal()
    try:
        broker_account_ids = [
            a.id for a in db.query(Account)
            .join(BrokerConnection, BrokerConnection.account_id == Account.id)
            .filter(Account.is_active == True, Account.account_type == "investment_brokerage")
            .all()
        ]
        manual_account_ids = [
            a.id for a in db.query(Account)
            .filter(Account.is_active == True, Account.account_type == "investment_manual")
            .all()
        ]
        all_ids = list(broker_account_ids) + list(manual_account_ids)
        for aid in all_ids:
            sync_investment_account.delay(str(aid))
        return {"queued": len(all_ids)}
    finally:
        db.close()


@shared_task(
    name="tasks.investment_tasks.sync_investment_account",
    bind=True,
    autoretry_for=(FlexStatementNotReady,),
    retry_backoff=True,
    retry_backoff_max=1800,
    retry_jitter=True,
    max_retries=6,
)
def sync_investment_account(self, account_id: str) -> dict:
    db = SessionLocal()
    try:
        svc = InvestmentSyncService(db=db, fx=_FxAdapter(db))
        svc.sync_account(UUID(account_id))
        return {"account_id": account_id, "status": "ok"}
    except FlexStatementNotReady:
        raise
    except Exception as e:
        logger.exception("Investment sync failed for %s: %s", account_id, e)
        return {"account_id": account_id, "status": "error", "error": str(e)}
    finally:
        db.close()
