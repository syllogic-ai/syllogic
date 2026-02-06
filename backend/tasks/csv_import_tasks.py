"""
Celery tasks for background CSV import processing.
Processes transactions in batches with real-time progress updates via Redis Pub/Sub.
"""
import logging
from typing import List, Optional, Dict, Any
from datetime import datetime
from decimal import Decimal

from celery_app import celery_app
from app.database import SessionLocal
from app.models import CsvImport, Account, Transaction, User, Category
from app.services.event_publisher import EventPublisher
from app.services.category_matcher import CategoryMatcher
from app.services.exchange_rate_service import ExchangeRateService
from app.services.account_balance_service import AccountBalanceService
from app.services.subscription_matcher import SubscriptionMatcher
from app.services.subscription_detector import SubscriptionDetector
from app.schemas import (
    TransactionInput,
    BatchCategorizeRequest,
    BatchCategorizeResponse,
    UserOverride,
    DailyBalanceImport,
)
from sqlalchemy import func, cast, Date

logger = logging.getLogger(__name__)


def _get_user_overrides_from_db(db, user_id: str) -> List[dict]:
    """
    Get user overrides from database based on overridden transactions.
    """
    matcher = CategoryMatcher(db, user_id=user_id)
    overridden_transactions = matcher.get_overridden_transactions()

    overrides = []
    for txn in overridden_transactions:
        if txn.category_id:
            category = db.query(Category).filter(Category.id == txn.category_id).first()
            if category:
                overrides.append({
                    "description": txn.description,
                    "merchant": txn.merchant,
                    "category_name": category.name
                })

    return overrides


def _get_categorization_instructions_from_db(db, user_id: str) -> List[str]:
    """
    Get categorization instructions from overridden transactions.
    """
    instructions = db.query(Transaction.categorization_instructions).filter(
        Transaction.user_id == user_id,
        Transaction.categorization_instructions.isnot(None)
    ).distinct().all()

    return [inst[0] for inst in instructions if inst[0]]


def _process_transaction_batch(
    db,
    user_id: str,
    transactions_data: List[Dict[str, Any]],
    user_overrides: List[dict],
    categorization_instructions: List[str],
) -> Dict[str, Any]:
    """
    Process a batch of transactions: normalize, categorize and insert.

    Returns:
        Dict with counts of inserted, skipped transactions and categorization summary
    """
    from app.routes.categories import categorize_transactions_batch
    from decimal import Decimal

    inserted_count = 0
    skipped_count = 0
    inserted_transactions = []
    seen_external_ids = set()
    
    # Normalize amounts and transaction_type (same logic as transaction_import route)
    normalized_transactions_data = []
    for txn in transactions_data:
        normalized_txn = txn.copy()
        amount = Decimal(str(txn["amount"]))
        transaction_type = str(txn.get("transaction_type", "")).lower()
        
        # Handle aliases: "expense" = "debit", "income" = "credit"
        if transaction_type in ["expense", "expenses"]:
            transaction_type = "debit"
        elif transaction_type in ["income", "revenue"]:
            transaction_type = "credit"
        
        # Normalize amounts: credit = positive, debit = negative
        if transaction_type == "credit":
            normalized_amount = abs(amount)  # Ensure positive
            # Validate: credit should be positive
            if float(amount) < 0:
                logger.warning(
                    f"[CSV_IMPORT] Warning: Transaction marked as 'credit' but amount is negative. "
                    f"Description: {txn.get('description', 'N/A')[:50]}, Amount: {amount}. "
                    f"Correcting to 'debit'."
                )
                transaction_type = "debit"
                normalized_amount = -abs(amount)  # Make negative for debit
        elif transaction_type == "debit":
            normalized_amount = -abs(amount)  # Ensure negative
            # Validate: debit should be negative
            if float(amount) > 0:
                logger.warning(
                    f"[CSV_IMPORT] Warning: Transaction marked as 'debit' but amount is positive. "
                    f"Description: {txn.get('description', 'N/A')[:50]}, Amount: {amount}. "
                    f"Correcting to 'credit'."
                )
                transaction_type = "credit"
                normalized_amount = abs(amount)  # Make positive for credit
        else:
            # If transaction_type is invalid, infer from amount sign
            logger.warning(
                f"[CSV_IMPORT] Invalid transaction_type '{txn.get('transaction_type')}' for transaction. "
                f"Description: {txn.get('description', 'N/A')[:50]}, Amount: {amount}. "
                f"Inferring from amount sign."
            )
            if float(amount) >= 0:
                transaction_type = "credit"
                normalized_amount = abs(amount)
            else:
                transaction_type = "debit"
                normalized_amount = -abs(amount)
        
        normalized_txn["amount"] = float(normalized_amount)
        normalized_txn["transaction_type"] = transaction_type
        normalized_transactions_data.append(normalized_txn)
    
    # Use normalized transactions for the rest of the processing
    transactions_data = normalized_transactions_data

    # Build set of existing external_ids for duplicate detection
    incoming_external_ids = [
        txn.get("external_id")
        for txn in transactions_data
        if txn.get("external_id")
    ]

    duplicate_external_ids = set()
    if incoming_external_ids:
        db.flush()
        existing = db.query(Transaction.external_id).filter(
            Transaction.user_id == user_id,
            Transaction.external_id.in_(incoming_external_ids)
        ).all()
        duplicate_external_ids = set(ext_id[0] for ext_id in existing if ext_id and ext_id[0])

    # Categorize transactions that don't have pre-assigned categories
    transactions_needing_categorization = []
    categorization_index_map = []

    for idx, txn in enumerate(transactions_data):
        if not txn.get("category_id"):
            transactions_needing_categorization.append(txn)
            categorization_index_map.append(idx)

    categorization_results = {}
    categorization_summary = None

    if transactions_needing_categorization:
        categorize_request = BatchCategorizeRequest(
            transactions=[
                TransactionInput(
                    description=txn["description"],
                    merchant=txn["merchant"],
                    amount=Decimal(str(txn["amount"])),
                    transaction_type=txn.get("transaction_type")  # Pass transaction_type for correct categorization
                )
                for txn in transactions_needing_categorization
            ],
            use_llm=True,
            user_overrides=[UserOverride(**override) for override in user_overrides] if user_overrides else None,
            additional_instructions=categorization_instructions if categorization_instructions else None
        )

        categorization_result: BatchCategorizeResponse = categorize_transactions_batch(
            categorize_request, db, user_id=user_id
        )

        categorization_summary = {
            "total": categorization_result.total_transactions,
            "categorized": categorization_result.categorized_count,
            "deterministic": categorization_result.deterministic_count,
            "llm": categorization_result.llm_count,
            "uncategorized": categorization_result.uncategorized_count,
            "tokens_used": categorization_result.total_tokens_used,
            "cost_usd": categorization_result.total_cost_usd,
        }

        for result_idx, result in enumerate(categorization_result.results):
            original_idx = categorization_index_map[result_idx]
            categorization_results[original_idx] = result.category_id

    # Handle pre-selected categories
    for idx, txn in enumerate(transactions_data):
        if txn.get("category_id"):
            categorization_results[idx] = txn["category_id"]

    # Insert transactions
    for idx, txn_data in enumerate(transactions_data):
        category_id = categorization_results.get(idx)

        try:
            external_id = txn_data.get("external_id")
            if external_id:
                if external_id in duplicate_external_ids or external_id in seen_external_ids:
                    skipped_count += 1
                    continue
                seen_external_ids.add(external_id)

            # Check for duplicates by amount/description/date
            if txn_data.get("description") and txn_data.get("booked_at"):
                normalized_description = txn_data["description"].strip() if txn_data["description"] else None
                booked_at = txn_data["booked_at"]
                if isinstance(booked_at, str):
                    booked_at = datetime.fromisoformat(booked_at.replace("Z", "+00:00"))
                booked_date = booked_at.date() if isinstance(booked_at, datetime) else booked_at

                query = db.query(Transaction).filter(
                    Transaction.account_id == txn_data["account_id"],
                    Transaction.user_id == user_id,
                    Transaction.amount == Decimal(str(txn_data["amount"]))
                )

                if normalized_description:
                    query = query.filter(
                        func.lower(func.trim(Transaction.description)) == normalized_description.lower().strip()
                    )

                query = query.filter(
                    cast(Transaction.booked_at, Date) == booked_date
                )

                if query.first():
                    skipped_count += 1
                    continue

            # Parse booked_at if string
            booked_at = txn_data["booked_at"]
            if isinstance(booked_at, str):
                booked_at = datetime.fromisoformat(booked_at.replace("Z", "+00:00"))

            transaction = Transaction(
                user_id=user_id,
                account_id=txn_data["account_id"],
                external_id=txn_data.get("external_id"),
                transaction_type=txn_data["transaction_type"],
                amount=Decimal(str(txn_data["amount"])),
                currency=txn_data["currency"],
                description=txn_data["description"],
                merchant=txn_data["merchant"],
                booked_at=booked_at,
                category_id=category_id,
                category_system_id=category_id if not txn_data.get("category_id") else None,
                pending=False
            )

            db.add(transaction)
            inserted_transactions.append(transaction)
            inserted_count += 1

        except Exception as e:
            logger.error(f"Error inserting transaction: {e}")
            skipped_count += 1

    db.commit()

    # Refresh to get IDs
    for txn in inserted_transactions:
        db.refresh(txn)

    return {
        "inserted_count": inserted_count,
        "skipped_count": skipped_count,
        "inserted_transactions": inserted_transactions,
        "categorization_summary": categorization_summary,
    }


@celery_app.task(bind=True, max_retries=3)
def process_csv_import(
    self,
    csv_import_id: str,
    user_id: str,
    transactions_data: List[Dict[str, Any]],
    daily_balances: Optional[List[Dict[str, Any]]] = None,
    starting_balance: Optional[float] = None,
):
    """
    Process CSV import in the background.

    This task:
    1. Processes transactions in batches
    2. Publishes progress updates via Redis Pub/Sub
    3. Performs post-import operations (categorization, balance calculation)

    Args:
        csv_import_id: UUID of the CsvImport record
        user_id: User ID
        transactions_data: List of transaction dicts to import
        daily_balances: Optional list of daily balance dicts
        starting_balance: Optional starting balance to set on account
    """
    logger.info(f"[CSV_IMPORT_TASK] Starting import {csv_import_id} for user {user_id}")

    db = SessionLocal()
    publisher = EventPublisher()

    try:
        # Get the CSV import record
        csv_import = db.query(CsvImport).filter(CsvImport.id == csv_import_id).first()
        if not csv_import:
            raise ValueError(f"CsvImport {csv_import_id} not found")

        csv_import.status = "importing"
        db.commit()

        total_rows = len(transactions_data)
        publisher.publish_import_started(user_id, csv_import_id, total_rows)

        # Get user overrides and instructions
        user_overrides = _get_user_overrides_from_db(db, user_id)
        categorization_instructions = _get_categorization_instructions_from_db(db, user_id)

        # Process in batches
        batch_size = 500
        total_inserted = 0
        total_skipped = 0
        all_inserted_transactions = []
        aggregated_categorization_summary = None

        for i in range(0, total_rows, batch_size):
            batch = transactions_data[i:i + batch_size]

            result = _process_transaction_batch(
                db=db,
                user_id=user_id,
                transactions_data=batch,
                user_overrides=user_overrides,
                categorization_instructions=categorization_instructions,
            )

            total_inserted += result["inserted_count"]
            total_skipped += result["skipped_count"]
            all_inserted_transactions.extend(result["inserted_transactions"])

            # Aggregate categorization summary
            if result["categorization_summary"]:
                if not aggregated_categorization_summary:
                    aggregated_categorization_summary = result["categorization_summary"].copy()
                else:
                    for key in ["total", "categorized", "deterministic", "llm", "uncategorized", "tokens_used"]:
                        aggregated_categorization_summary[key] += result["categorization_summary"].get(key, 0)
                    aggregated_categorization_summary["cost_usd"] += result["categorization_summary"].get("cost_usd", 0.0)

            # Update progress
            processed = min(i + batch_size, total_rows)
            csv_import.progress_count = processed
            db.commit()

            publisher.publish_import_progress(user_id, csv_import_id, processed, total_rows)
            logger.info(f"[CSV_IMPORT_TASK] Batch processed: {processed}/{total_rows}")

        # Post-import operations
        if all_inserted_transactions:
            affected_account_ids = list(set([str(txn.account_id) for txn in all_inserted_transactions]))
            inserted_ids = [str(txn.id) for txn in all_inserted_transactions]

            # Match subscriptions
            _match_subscriptions(db, user_id, all_inserted_transactions)

            # Detect subscription patterns
            _detect_subscriptions(db, user_id, inserted_ids)

            # Sync exchange rates
            _sync_exchange_rates(db, user_id, transactions_data)

            # Update functional amounts
            _update_functional_amounts(db, user_id, all_inserted_transactions)

            # Update starting balance if provided
            if starting_balance is not None:
                for account_id in affected_account_ids:
                    account = db.query(Account).filter(Account.id == account_id).first()
                    if account:
                        account.starting_balance = Decimal(str(starting_balance))
                db.commit()

            # Calculate balances
            balance_service = AccountBalanceService(db)
            balance_service.calculate_account_balances(user_id, account_ids=affected_account_ids)

            # Import daily balances if provided
            skip_dates_by_account = {}
            if daily_balances:
                user = db.query(User).filter(User.id == user_id).first()
                functional_currency = user.functional_currency if user else "EUR"

                for account_id in affected_account_ids:
                    result = balance_service.import_daily_balances(
                        account_id=account_id,
                        daily_balances=daily_balances,
                        functional_currency=functional_currency
                    )
                    if result.get("imported_dates"):
                        skip_dates_by_account[account_id] = result["imported_dates"]

            # Calculate timeseries
            balance_service.calculate_account_timeseries(
                user_id,
                account_ids=affected_account_ids,
                skip_dates=skip_dates_by_account if skip_dates_by_account else None
            )

        # Update CSV import record
        csv_import.status = "completed"
        csv_import.imported_rows = total_inserted
        csv_import.completed_at = datetime.utcnow()
        db.commit()

        publisher.publish_import_completed(
            user_id=user_id,
            import_id=csv_import_id,
            imported_count=total_inserted,
            skipped_count=total_skipped,
            categorization_summary=aggregated_categorization_summary,
        )

        logger.info(
            f"[CSV_IMPORT_TASK] Completed import {csv_import_id}: "
            f"{total_inserted} inserted, {total_skipped} skipped"
        )

        return {
            "success": True,
            "import_id": csv_import_id,
            "imported_count": total_inserted,
            "skipped_count": total_skipped,
        }

    except Exception as e:
        logger.error(f"[CSV_IMPORT_TASK] Import {csv_import_id} failed: {e}")
        import traceback
        logger.error(traceback.format_exc())

        # Update CSV import record with error
        try:
            csv_import = db.query(CsvImport).filter(CsvImport.id == csv_import_id).first()
            if csv_import:
                csv_import.status = "failed"
                csv_import.error_message = str(e)
                db.commit()
        except Exception:
            pass

        publisher.publish_import_failed(user_id, csv_import_id, str(e))
        raise self.retry(exc=e, countdown=60)

    finally:
        db.close()
        publisher.close()


def _match_subscriptions(db, user_id: str, transactions: List[Transaction]) -> None:
    """Match transactions to existing subscriptions."""
    try:
        subscription_matcher = SubscriptionMatcher(db, user_id=user_id)
        matched_count = 0

        for txn in transactions:
            if float(txn.amount) >= 0 or txn.recurring_transaction_id:
                continue

            match = subscription_matcher.match_transaction(
                description=txn.description,
                merchant=txn.merchant,
                amount=txn.amount
            )

            if match:
                txn.recurring_transaction_id = match.id
                matched_count += 1

        if matched_count > 0:
            db.commit()
            logger.info(f"Matched {matched_count} transactions to subscriptions")
    except Exception as e:
        logger.error(f"Error matching subscriptions: {e}")


def _detect_subscriptions(db, user_id: str, transaction_ids: List[str]) -> None:
    """Detect new subscription patterns."""
    try:
        detector = SubscriptionDetector(db, user_id=user_id)
        suggestions_count = detector.detect_and_save(transaction_ids)
        if suggestions_count > 0:
            logger.info(f"Created {suggestions_count} subscription suggestions")
    except Exception as e:
        logger.error(f"Error detecting subscriptions: {e}")


def _sync_exchange_rates(db, user_id: str, transactions_data: List[Dict]) -> None:
    """Sync exchange rates for transaction currencies."""
    try:
        account_currencies = set()
        for txn in transactions_data:
            currency = txn.get("currency", "EUR")
            if currency:
                account_currencies.add(currency)

        if not account_currencies:
            return

        # Find date range
        dates = []
        for txn in transactions_data:
            booked_at = txn.get("booked_at")
            if booked_at:
                if isinstance(booked_at, str):
                    booked_at = datetime.fromisoformat(booked_at.replace("Z", "+00:00"))
                if isinstance(booked_at, datetime):
                    dates.append(booked_at.date())

        if not dates:
            return

        start_date = min(dates)
        end_date = max(dates)

        service = ExchangeRateService(db)
        for currency in account_currencies:
            rates_by_date = service.fetch_exchange_rates_batch(
                base_currency=currency,
                target_currencies=["EUR", "USD"],
                start_date=start_date,
                end_date=end_date
            )

            for rate_date, rate_dict in rates_by_date.items():
                if "EUR" in rate_dict:
                    service.store_exchange_rates("EUR", {currency: rate_dict["EUR"]}, rate_date)
                if "USD" in rate_dict:
                    service.store_exchange_rates("USD", {currency: rate_dict["USD"]}, rate_date)

    except Exception as e:
        logger.error(f"Error syncing exchange rates: {e}")


def _update_functional_amounts(db, user_id: str, transactions: List[Transaction]) -> None:
    """Update functional amounts for transactions."""
    try:
        user = db.query(User).filter(User.id == user_id).first()
        functional_currency = user.functional_currency if user else "EUR"

        service = ExchangeRateService(db)

        for txn in transactions:
            try:
                txn_date = txn.booked_at.date()

                if txn.currency == functional_currency:
                    txn.functional_amount = txn.amount
                else:
                    exchange_rate = service.get_exchange_rate(
                        base_currency=txn.currency,
                        target_currency=functional_currency,
                        for_date=txn_date
                    )

                    if exchange_rate:
                        txn.functional_amount = txn.amount * exchange_rate
                    else:
                        txn.functional_amount = None
            except Exception as e:
                logger.error(f"Error updating functional amount for transaction {txn.id}: {e}")

        db.commit()
    except Exception as e:
        logger.error(f"Error updating functional amounts: {e}")
