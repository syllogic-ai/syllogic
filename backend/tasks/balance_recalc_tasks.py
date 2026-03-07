"""
Celery task for asynchronous balance recalculation after transaction deletions.
"""
import logging
from typing import List

from celery_app import celery_app
from app.database import SessionLocal
from app.db_helpers import set_request_user_id, clear_request_user_id
from app.services.account_balance_service import AccountBalanceService

logger = logging.getLogger(__name__)


@celery_app.task(bind=True, max_retries=3)
def recalculate_balances_after_deletion(
    self,
    user_id: str,
    account_ids: List[str],
):
    """
    Recalculate account balances and timeseries after transactions have been deleted.

    Args:
        user_id: User ID
        account_ids: List of account IDs whose balances need recalculation
    """
    logger.info(
        f"[BALANCE_RECALC] Starting recalculation for user {user_id}, "
        f"accounts: {account_ids}"
    )

    request_token = set_request_user_id(user_id)
    db = SessionLocal()

    try:
        balance_service = AccountBalanceService(db)

        balance_result = balance_service.calculate_account_balances(
            user_id, account_ids=account_ids
        )
        logger.info(f"[BALANCE_RECALC] Balance calculation result: {balance_result}")

        timeseries_result = balance_service.calculate_account_timeseries(
            user_id, account_ids=account_ids
        )
        logger.info(f"[BALANCE_RECALC] Timeseries calculation result: {timeseries_result}")

        return {
            "success": True,
            "balance_result": balance_result,
            "timeseries_result": timeseries_result,
        }

    except Exception as e:
        logger.error(f"[BALANCE_RECALC] Failed: {e}")
        import traceback
        logger.error(traceback.format_exc())
        raise self.retry(exc=e, countdown=30)

    finally:
        db.close()
        clear_request_user_id(request_token)
