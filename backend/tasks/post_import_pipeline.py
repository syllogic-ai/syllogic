"""
Shared post-import pipeline Celery task.

Runs 7 post-processing steps in order after any transaction import (CSV or Enable Banking):
  1. FX rate sync
  2. Functional amount calculation
  3. Internal transfer detection (create mirrors, flag both sides as non-analytics)
  4. Batch AI categorization (for transactions without a user-assigned category)
  5. Balance calculation
  6. Balance timeseries
  7. Subscription detection
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
from app.services.category_embedding import CategoryEmbeddingService
from app.services.internal_transfer_service import InternalTransferService

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


def _detect_internal_transfers(db, user_id: str, transaction_ids: List[str]) -> dict:
    """Detect counterparty-IBAN matches against the user's manual pocket accounts
    and create mirror transactions on the pocket side.

    Returns ``{"detected": int, "pocket_account_ids": list[UUID]}``. Callers
    should extend their balance/timeseries account scope with
    ``pocket_account_ids`` so mirrored pockets get recalculated.
    """
    if not transaction_ids:
        return {"detected": 0, "pocket_account_ids": []}
    service = InternalTransferService(db, user_id=user_id)
    return service.detect_for_transactions(transaction_ids)


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
            # Skip transactions excluded from analytics — covers internal
            # transfers (set by step 3) AND user-hidden rows (set via UI).
            Transaction.include_in_analytics.is_(True),
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

    # Tier 1: user overrides. Checked upfront so downstream tiers only run on
    # genuinely unassigned rows, and so the persisted method is accurate.
    override_matches: dict = {}
    for entry in batch_input:
        cat = matcher._check_user_override(
            entry.get("description"),
            entry.get("merchant"),
            Decimal(str(entry["amount"])),
        )
        if cat is not None:
            override_matches[entry["index"]] = cat

    # Tier 2: semantic (embedding) match on whatever overrides didn't claim.
    # Caches the per-transaction embedding so the LLM tier doesn't re-embed.
    embedder = CategoryEmbeddingService(db)
    embedder.refresh_category_embeddings(user_id=user_id)  # no-op once populated
    post_override = [b for b in batch_input if b["index"] not in override_matches]
    embed_matches, embed_vectors = embedder.match_categories_batch(
        user_id=user_id, transactions=post_override
    )
    # Map per-index vectors so we can cache them on the row.
    txn_vector_by_index: dict = {
        entry["index"]: embed_vectors[i]
        for i, entry in enumerate(post_override)
        if embed_vectors and i < len(embed_vectors)
    }

    # Tier 3: LLM on whatever embedding couldn't confidently place.
    llm_batch = [b for b in post_override if b["index"] not in embed_matches]
    llm_results: dict = {}
    total_tokens = 0
    total_cost = 0.0
    if llm_batch:
        llm_results, total_tokens, total_cost = matcher.match_categories_batch_llm(llm_batch)

    # If no tier produced anything AND no tokens were spent, assume OpenAI is
    # unavailable — preserve existing system categories rather than wiping them.
    if (
        not override_matches
        and not embed_matches
        and not llm_results
        and total_tokens == 0
    ):
        logger.info(
            "[POST_IMPORT_PIPELINE] Categorization unavailable (no API key?); "
            "skipping, existing system categories preserved"
        )
        return

    assigned = 0
    for i, txn in enumerate(transactions):
        # Cache embedding on the row (even if another tier made the call).
        if i in txn_vector_by_index:
            txn.embedding = txn_vector_by_index[i]

        if i in override_matches:
            txn.category_system_id = override_matches[i].id
            txn.categorization_confidence = Decimal("100.00")
            txn.categorization_method = "override"
            assigned += 1
            continue

        if i in embed_matches:
            match = embed_matches[i]
            txn.category_system_id = match.category.id
            txn.categorization_confidence = Decimal(f"{match.confidence:.2f}")
            txn.categorization_method = "embedding"
            assigned += 1
            continue

        if i in llm_results:
            category, confidence = llm_results[i]
            txn.category_system_id = category.id
            txn.categorization_confidence = Decimal(f"{float(confidence):.2f}")
            txn.categorization_method = "llm"
            assigned += 1
        # When no tier matched, leave the existing system category intact.

    if assigned > 0:
        db.commit()

    logger.info(
        "[POST_IMPORT_PIPELINE] Batch categorized %d/%d (override: %d, embedding: %d, "
        "llm: %d, tokens: %d, cost: $%.6f)",
        assigned,
        len(transactions),
        len(override_matches),
        len(embed_matches),
        len(llm_results),
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

        # Step 3: Internal transfer detection (must run before LLM categorization)
        detection = _detect_internal_transfers(db, user_id, transaction_ids)
        logger.info(
            "[POST_IMPORT_PIPELINE] Internal transfers detected: %d (touched %d pocket(s))",
            detection["detected"],
            len(detection["pocket_account_ids"]),
        )

        # Mirror transactions created in step 3 live on the pocket account; if
        # that pocket isn't in the sync's original account_ids scope, its
        # balance and timeseries won't be refreshed. Extend the recalc set to
        # include every pocket we just mirrored into.
        touched_pocket_ids = [str(pid) for pid in detection["pocket_account_ids"]]
        recalc_account_ids = list({*account_ids, *touched_pocket_ids})

        # Step 4: Batch AI categorization (overwrites wrong system categories; preserves user overrides)
        _batch_categorize_transactions(db, user_id, transaction_ids)

        # Step 5: Balance calculation
        _calculate_balances(db, user_id, recalc_account_ids)

        # Step 6: Balance timeseries
        _calculate_timeseries(db, user_id, recalc_account_ids)

        # Step 7: Subscription detection
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
