from __future__ import annotations
from datetime import date
import logging
import os
from uuid import UUID
from celery import shared_task
from sqlalchemy import func

from app.database import SessionLocal
from app.models import Account, BrokerConnection, User
from app.services.investment_sync_service import InvestmentSyncService
from app.services.exchange_rate_service import ExchangeRateService
from app.integrations.ibkr_flex_adapter import FlexStatementNotReady

logger = logging.getLogger(__name__)


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _resolve_demo_user_id(db) -> str | None:
    """Resolve the shared demo user's id when demo mode is enabled.

    The demo portfolio is seeded directly with deterministic valuations and
    must NOT be touched by the real IBKR/price sync (no valid Flex token, and
    live price fetches would make the data non-deterministic)."""
    if not _env_bool("DEMO_MODE", default=False):
        return None
    user_id = os.getenv("DEMO_SHARED_USER_ID")
    if user_id:
        return user_id
    email = os.getenv("DEMO_SHARED_USER_EMAIL")
    if not email:
        return None
    user = db.query(User).filter(func.lower(User.email) == email.strip().lower()).first()
    return user.id if user else None


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
        demo_user_id = _resolve_demo_user_id(db)

        # Fail safe: when demo mode is enabled but the demo identity cannot be
        # resolved, skip entirely rather than risk syncing the demo portfolio.
        # Its seeded holdings have no valid Flex token and must keep their
        # deterministic valuations untouched.
        if _env_bool("DEMO_MODE", default=False) and not demo_user_id:
            logger.warning(
                "Skipping investment sync: DEMO_MODE enabled but demo user "
                "identity is not configured/resolvable"
            )
            return {
                "queued": 0,
                "demo_excluded": False,
                "skipped": True,
                "reason": "MISSING_DEMO_USER_IDENTITY",
            }

        broker_q = (
            db.query(Account)
            .join(BrokerConnection, BrokerConnection.account_id == Account.id)
            .filter(Account.is_active == True, Account.account_type == "investment_brokerage")
        )
        manual_q = (
            db.query(Account)
            .filter(Account.is_active == True, Account.account_type == "investment_manual")
        )
        if demo_user_id:
            broker_q = broker_q.filter(Account.user_id != demo_user_id)
            manual_q = manual_q.filter(Account.user_id != demo_user_id)

        broker_account_ids = [a.id for a in broker_q.all()]
        manual_account_ids = [a.id for a in manual_q.all()]
        all_ids = list(broker_account_ids) + list(manual_account_ids)
        for aid in all_ids:
            sync_investment_account.delay(str(aid))
        return {"queued": len(all_ids), "demo_excluded": bool(demo_user_id)}
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
    except Exception:
        logger.exception("Investment sync failed for %s", account_id)
        raise
    finally:
        db.close()
