"""
Shared post-import pipeline Celery task.

Runs 6 post-processing steps in order after any transaction import (CSV or Enable Banking):
  1. FX rate sync
  2. Functional amount calculation
  3. Batch AI categorization (for transactions without a user-assigned category)
  4. Balance calculation
  5. Balance timeseries
  6. Subscription detection
"""
import logging
from datetime import datetime
from decimal import Decimal
from typing import List, Optional

from celery_app import celery_app

from app.database import SessionLocal
from app.db_helpers import set_request_user_id, clear_request_user_id
from app.models import Transaction, User
from app.services.exchange_rate_service import ExchangeRateService
from app.services.account_balance_service import AccountBalanceService
from app.services.subscription_matcher import SubscriptionMatcher
from app.services.subscription_detector import SubscriptionDetector
from app.services.category_matcher import CategoryMatcher

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _sync_exchange_rates(db, user_id: str, transaction_ids: List[str]) -> None:
    """Fetch and store exchange rates for all currencies in the given transactions."""
    transactions = (
        db.query(Transaction)
        .filter(
            Transaction.id.in_(transaction_ids),
            Transaction.user_id == user_id,
        )
        .all()
    )

    if not transactions:
        return

    user = db.query(User).filter(User.id == user_id).first()
    functional_currency = user.functional_currency if user else "EUR"

    # Unique foreign currencies (skip functional currency — no rate needed)
    foreign_currencies = set()
    for txn in transactions:
        if txn.currency and txn.currency != functional_currency:
            foreign_currencies.add(txn.currency)

    if not foreign_currencies:
        return

    # Date range
    dates = [txn.booked_at.date() for txn in transactions if txn.booked_at]
    if not dates:
        return

    start_date = min(dates)
    end_date = max(dates)

    service = ExchangeRateService(db)
    target_currencies = [functional_currency]

    for currency in foreign_currencies:
        rates_by_date = service.fetch_exchange_rates_batch(
            base_currency=currency,
            target_currencies=target_currencies,
            start_date=start_date,
            end_date=end_date,
        )

        for rate_date, rate_dict in rates_by_date.items():
            if functional_currency in rate_dict:
                service.store_exchange_rates(
                    functional_currency,
                    {currency: rate_dict[functional_currency]},
                    rate_date,
                )


def _update_functional_amounts(db, user_id: str, transaction_ids: List[str]) -> None:
    """Set functional_amount on each transaction using stored exchange rates."""
    transactions = (
        db.query(Transaction)
        .filter(
            Transaction.id.in_(transaction_ids),
            Transaction.user_id == user_id,
        )
        .all()
    )

    if not transactions:
        return

    user = db.query(User).filter(User.id == user_id).first()
    functional_currency = user.functional_currency if user else "EUR"

    service = ExchangeRateService(db)

    for txn in transactions:
        if txn.currency == functional_currency:
            txn.functional_amount = txn.amount
        else:
            txn_date = txn.booked_at.date()
            rate = service.get_exchange_rate(
                base_currency=txn.currency,
                target_currency=functional_currency,
                for_date=txn_date,
            )
            txn.functional_amount = txn.amount * rate if rate else None

    db.commit()


def _batch_categorize_transactions(db, user_id: str, transaction_ids: List[str]) -> None:
    """Batch AI categorize touched transactions that have no user-assigned category.

    Overwrites any existing system-assigned category (category_system_id) so that
    transactions wrongly auto-categorized during a previous inline pass are corrected.
    User manual overrides (category_id) are always preserved.
    """
    if not transaction_ids:
        return

    transactions = (
        db.query(Transaction)
        .filter(
            Transaction.id.in_(transaction_ids),
            Transaction.user_id == user_id,
            Transaction.category_id.is_(None),  # Preserve user-assigned categories
        )
        .all()
    )

    if not transactions:
        logger.info("[POST_IMPORT_PIPELINE] No uncategorized transactions to process")
        return

    matcher = CategoryMatcher(db, user_id=user_id)

    batch_input = [
        {
            "index": i,
            "description": txn.description,
            "merchant": txn.merchant,
            "amount": float(txn.amount),
            "transaction_type": txn.transaction_type,
        }
        for i, txn in enumerate(transactions)
    ]

    results, total_tokens, total_cost = matcher.match_categories_batch_llm(batch_input)

    # If no results and no tokens were used, OpenAI is unavailable — bail out without
    # touching any existing system categories so the non-LLM fallback is preserved.
    if not results and total_tokens == 0:
        logger.info(
            "[POST_IMPORT_PIPELINE] Batch LLM unavailable (no API key?); "
            "skipping categorization, existing system categories preserved"
        )
        return

    assigned = 0
    for i, txn in enumerate(transactions):
        if i in results:
            category, _confidence = results[i]
            txn.category_system_id = category.id
            assigned += 1
        # When LLM ran but returned no match for a transaction, leave the existing
        # system category intact rather than wiping it.

    if assigned > 0:
        db.commit()

    logger.info(
        "[POST_IMPORT_PIPELINE] Batch categorized %d/%d transactions "
        "(tokens: %d, cost: $%.6f)",
        assigned,
        len(transactions),
        total_tokens,
        total_cost,
    )


def _calculate_balances(db, user_id: str, account_ids: List[str]) -> None:
    """Recalculate account balances for the given accounts."""
    service = AccountBalanceService(db)
    service.calculate_account_balances(user_id, account_ids=account_ids)


def _calculate_timeseries(db, user_id: str, account_ids: List[str]) -> None:
    """Compute daily balance snapshots for the given accounts."""
    service = AccountBalanceService(db)
    service.calculate_account_timeseries(user_id, account_ids=account_ids)


def _detect_subscriptions(
    db,
    user_id: str,
    transaction_ids: Optional[List[str]],
    account_ids: List[str],
) -> None:
    """Match existing subscriptions and detect new patterns.

    When transaction_ids is None (initial sync), the detector scans ALL user
    transactions to discover cross-account patterns.
    """
    # --- Match to existing subscriptions ---
    if transaction_ids is not None:
        transactions = (
            db.query(Transaction)
            .filter(
                Transaction.id.in_(transaction_ids),
                Transaction.user_id == user_id,
            )
            .all()
        )

        matcher = SubscriptionMatcher(db, user_id=user_id)
        matched_count = 0

        for txn in transactions:
            if float(txn.amount) >= 0 or txn.recurring_transaction_id:
                continue
            match = matcher.match_transaction(
                description=txn.description,
                merchant=txn.merchant,
                amount=txn.amount,
                account_id=str(txn.account_id),
            )
            if match:
                txn.recurring_transaction_id = match.id
                matched_count += 1

        if matched_count > 0:
            db.commit()
            logger.info(
                f"[POST_IMPORT_PIPELINE] Matched {matched_count} transactions to subscriptions"
            )

    # --- Detect new subscription patterns ---
    detector = SubscriptionDetector(db, user_id=user_id)
    # Pass None for initial sync so detector scans all user transactions
    detection = detector.detect_and_apply(transaction_ids, account_ids=account_ids)
    detected_count = detection.get("detected_count", 0)
    if detected_count > 0:
        logger.info(
            "[POST_IMPORT_PIPELINE] Detected %s new subscriptions "
            "(created=%s, updated=%s, linked=%s)",
            detected_count,
            detection.get("created_count", 0),
            detection.get("updated_count", 0),
            detection.get("linked_count", 0),
        )


# ---------------------------------------------------------------------------
# Core logic (extracted for testability)
# ---------------------------------------------------------------------------

def _run_post_import_pipeline(
    user_id: str,
    account_ids: List[str],
    transaction_ids: List[str],
    is_initial_sync: bool = False,
) -> None:
    """Run the full post-import pipeline.

    Creates its own DB session and user context, always cleans up.
    """
    db = SessionLocal()
    token = set_request_user_id(user_id)

    try:
        logger.info(
            "[POST_IMPORT_PIPELINE] Starting for user=%s accounts=%s txns=%s initial=%s",
            user_id,
            account_ids,
            len(transaction_ids) if transaction_ids else 0,
            is_initial_sync,
        )

        # Step 1: FX rate sync
        _sync_exchange_rates(db, user_id, transaction_ids)

        # Step 2: Functional amount calculation
        _update_functional_amounts(db, user_id, transaction_ids)

        # Step 3: Batch AI categorization (overwrites wrong system categories; preserves user overrides)
        _batch_categorize_transactions(db, user_id, transaction_ids)

        # Step 4: Balance calculation
        _calculate_balances(db, user_id, account_ids)

        # Step 5: Balance timeseries
        _calculate_timeseries(db, user_id, account_ids)

        # For initial sync, pass None so the detector scans ALL user transactions
        effective_txn_ids = None if is_initial_sync else transaction_ids
        _detect_subscriptions(db, user_id, effective_txn_ids, account_ids)

        logger.info("[POST_IMPORT_PIPELINE] Completed for user=%s", user_id)

    finally:
        clear_request_user_id(token)
        db.close()


# ---------------------------------------------------------------------------
# Celery task
# ---------------------------------------------------------------------------

@celery_app.task(bind=True, max_retries=3, default_retry_delay=60)
def post_import_pipeline(
    self,
    user_id: str,
    account_ids: List[str],
    transaction_ids: List[str],
    is_initial_sync: bool = False,
):
    """
    Shared post-import pipeline task.

    Runs FX rate sync, functional amount calculation, balance calculation,
    balance timeseries, and subscription detection in order.

    Args:
        user_id: Owner of the imported transactions.
        account_ids: Accounts whose balances should be recalculated.
        transaction_ids: Newly imported transaction IDs.
        is_initial_sync: When True, subscription detection scans ALL user
            transactions (not just the newly imported ones) to discover
            cross-account patterns.
    """
    try:
        _run_post_import_pipeline(
            user_id=user_id,
            account_ids=account_ids,
            transaction_ids=transaction_ids,
            is_initial_sync=is_initial_sync,
        )
        return {"success": True, "user_id": user_id}
    except Exception as e:
        logger.error(f"[POST_IMPORT_PIPELINE] Task failed for user {user_id}: {e}")
        raise self.retry(exc=e)
