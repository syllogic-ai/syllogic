"""
API wrapper for importing and processing transactions.
Handles the complete workflow:
1. Normalize transaction amounts based on transactionType
2. Categorize transactions using batch API
3. Insert transactions with categories
4. Sync exchange rates
5. Update functional amounts
6. Calculate account balances
7. Calculate and store account timeseries (daily balance snapshots)
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional
from uuid import UUID
from decimal import Decimal
from datetime import datetime, date
import logging

from app.database import get_db
from app.db_helpers import get_user_id
from app.models import Transaction, Account, User, ExchangeRate, AccountTimeseries
from pydantic import BaseModel
from app.schemas import (
    TransactionCreate,
    TransactionInput,
    BatchCategorizeRequest,
    BatchCategorizeResponse,
    UserOverride
)
from app.models import Category
from app.services.category_matcher import CategoryMatcher
from app.services.exchange_rate_service import ExchangeRateService
from app.services.account_balance_service import AccountBalanceService
from sqlalchemy import func

logger = logging.getLogger(__name__)

router = APIRouter()


class TransactionImportItem(BaseModel):
    """Single transaction to import."""
    account_id: UUID
    amount: Decimal
    description: Optional[str] = None
    merchant: Optional[str] = None
    booked_at: datetime
    transaction_type: str  # "credit" or "debit"
    currency: str = "EUR"
    external_id: Optional[str] = None


class TransactionImportRequest(BaseModel):
    """Request to import transactions."""
    transactions: List[TransactionImportItem]
    user_id: Optional[str] = None
    sync_exchange_rates: bool = True
    update_functional_amounts: bool = True
    calculate_balances: bool = True


class TransactionImportResponse(BaseModel):
    """Response from transaction import."""
    success: bool
    message: str
    transactions_inserted: int
    transaction_ids: Optional[List[str]] = None  # IDs of inserted transactions for verification
    categorization_summary: Optional[dict] = None
    exchange_rates_synced: Optional[dict] = None
    functional_amounts_updated: Optional[dict] = None
    balances_calculated: Optional[dict] = None
    timeseries_calculated: Optional[dict] = None


def _get_user_overrides_from_db(db: Session, user_id: str) -> List[dict]:
    """
    Get user overrides from database based on overridden transactions.
    
    Returns list of override dicts in format:
    [{"description": "...", "merchant": "...", "category_name": "..."}, ...]
    """
    matcher = CategoryMatcher(db, user_id=user_id)
    overridden_transactions = matcher.get_overridden_transactions()
    
    overrides = []
    for txn in overridden_transactions:
        # Get the user-selected category (category_id, not category_system_id)
        if txn.category_id:
            category = db.query(Category).filter(Category.id == txn.category_id).first()
            if category:
                overrides.append({
                    "description": txn.description,
                    "merchant": txn.merchant,
                    "category_name": category.name
                })
    
    return overrides


def _get_categorization_instructions_from_db(db: Session, user_id: str) -> List[str]:
    """
    Get categorization instructions from overridden transactions.
    
    Returns list of instruction strings from transactions with categorization_instructions.
    """
    instructions = db.query(Transaction.categorization_instructions).filter(
        Transaction.user_id == user_id,
        Transaction.categorization_instructions.isnot(None)
    ).distinct().all()
    
    return [inst[0] for inst in instructions if inst[0]]


@router.post("/import", response_model=TransactionImportResponse)
def import_transactions(
    request: TransactionImportRequest,
    db: Session = Depends(get_db)
):
    """
    Import transactions with full processing pipeline.
    
    This endpoint:
    1. Normalizes amounts based on transactionType (credit = positive, debit = negative)
    2. Categorizes transactions using batch API with user overrides and instructions
    3. Inserts transactions into database with categories
    4. Syncs exchange rates for transaction currencies from earliest date
    5. Updates functional_amount for all transactions
    6. Calculates and updates functional_balance for all accounts
    
    Example request:
    ```json
    {
        "transactions": [
            {
                "account_id": "123e4567-e89b-12d3-a456-426614174000",
                "amount": 25.50,
                "description": "TESCO SUPERMARKET",
                "merchant": "Tesco",
                "booked_at": "2025-01-17T10:00:00Z",
                "transaction_type": "debit",
                "currency": "EUR"
            }
        ],
        "sync_exchange_rates": true,
        "update_functional_amounts": true,
        "calculate_balances": true
    }
    ```
    """
    try:
        user_id = get_user_id(request.user_id)
        
        if not request.transactions:
            raise HTTPException(status_code=400, detail="No transactions provided")
        
        logger.info(f"[IMPORT] Starting import of {len(request.transactions)} transactions for user {user_id}")
        
        # Step 1: Normalize amounts based on transaction_type
        normalized_transactions = []
        for txn in request.transactions:
            # Validate account belongs to user
            account = db.query(Account).filter(
                Account.id == txn.account_id,
                Account.user_id == user_id
            ).first()
            if not account:
                raise HTTPException(
                    status_code=404,
                    detail=f"Account {txn.account_id} not found or doesn't belong to user"
                )
            
            # Normalize amount: credit = positive, debit = negative
            normalized_amount = txn.amount
            if txn.transaction_type.lower() == "credit":
                normalized_amount = abs(txn.amount)  # Ensure positive
            elif txn.transaction_type.lower() == "debit":
                normalized_amount = -abs(txn.amount)  # Ensure negative
            else:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid transaction_type: {txn.transaction_type}. Must be 'credit' or 'debit'"
                )
            
            normalized_transactions.append({
                "account_id": txn.account_id,
                "amount": normalized_amount,
                "description": txn.description,
                "merchant": txn.merchant,
                "booked_at": txn.booked_at,
                "transaction_type": txn.transaction_type.lower(),
                "currency": txn.currency or account.currency or "EUR",
                "external_id": txn.external_id
            })
        
        # Step 2: Get user overrides and instructions from database
        logger.info("[IMPORT] Fetching user overrides and categorization instructions...")
        user_overrides = _get_user_overrides_from_db(db, user_id)
        categorization_instructions = _get_categorization_instructions_from_db(db, user_id)
        
        logger.info(f"[IMPORT] Found {len(user_overrides)} user overrides and {len(categorization_instructions)} instructions")
        
        # Step 3: Categorize transactions using batch API
        logger.info("[IMPORT] Categorizing transactions...")
        categorize_request = BatchCategorizeRequest(
            transactions=[
                TransactionInput(
                    description=txn["description"],
                    merchant=txn["merchant"],
                    amount=txn["amount"]
                )
                for txn in normalized_transactions
            ],
            use_llm=True,
            user_overrides=[UserOverride(**override) for override in user_overrides] if user_overrides else None,
            additional_instructions=categorization_instructions if categorization_instructions else None
        )
        
        # Call the categorize/batch endpoint logic directly
        # Import here to avoid circular dependency
        from app.routes.categories import categorize_transactions_batch
        categorization_result: BatchCategorizeResponse = categorize_transactions_batch(categorize_request, db)
        
        logger.info(
            f"[IMPORT] Categorization complete: "
            f"{categorization_result.categorized_count} categorized, "
            f"{categorization_result.uncategorized_count} uncategorized"
        )
        
        # Step 4: Check for and remove duplicate transactions before inserting
        logger.info("[IMPORT] Checking for existing duplicate transactions...")
        deleted_count = 0
        checked_count = 0
        
        for txn_data in normalized_transactions:
            checked_count += 1
            # Check 1: Check for existing transactions with same account_id and external_id
            if txn_data.get("external_id"):
                existing_by_external_id = db.query(Transaction).filter(
                    Transaction.account_id == txn_data["account_id"],
                    Transaction.external_id == txn_data["external_id"],
                    Transaction.user_id == user_id
                ).all()
                
                if existing_by_external_id:
                    logger.info(
                        f"[IMPORT] Found {len(existing_by_external_id)} existing transaction(s) with "
                        f"account_id={txn_data['account_id']}, external_id={txn_data['external_id']}. "
                        f"Removing duplicates..."
                    )
                    for existing_txn in existing_by_external_id:
                        db.delete(existing_txn)
                        deleted_count += 1
                    continue  # Skip to next transaction if found by external_id
            
            # Check 2: Check for existing transactions with same amount, description, and booked_at
            # This helps catch duplicates even when external_id is not available
            # Use date comparison (not exact datetime) to handle microsecond differences
            if txn_data.get("description") and txn_data.get("booked_at"):
                # Normalize description for comparison (strip whitespace, case-insensitive)
                normalized_description = txn_data["description"].strip() if txn_data["description"] else None
                
                # Extract date from booked_at (handle both datetime and date objects)
                if isinstance(txn_data["booked_at"], datetime):
                    booked_date = txn_data["booked_at"].date()
                elif hasattr(txn_data["booked_at"], 'date'):
                    booked_date = txn_data["booked_at"].date()
                else:
                    booked_date = txn_data["booked_at"]
                
                # Query using date comparison and normalized description
                # Use cast to ensure proper date comparison
                from sqlalchemy import func, cast, Date
                from sqlalchemy import and_
                
                # Build the query with proper date casting
                query = db.query(Transaction).filter(
                    Transaction.account_id == txn_data["account_id"],
                    Transaction.user_id == user_id,
                    Transaction.amount == txn_data["amount"]
                )
                
                # Add description filter (case-insensitive, trimmed)
                if normalized_description:
                    query = query.filter(
                        func.lower(func.trim(Transaction.description)) == normalized_description.lower().strip()
                    )
                
                # Add date filter (compare dates, not exact datetime)
                query = query.filter(
                    cast(Transaction.booked_at, Date) == booked_date
                )
                
                existing_by_details = query.all()
                
                if existing_by_details:
                    logger.info(
                        f"[IMPORT] Found {len(existing_by_details)} existing transaction(s) with "
                        f"matching amount={txn_data['amount']}, description='{normalized_description}', "
                        f"booked_at={booked_date}. Removing duplicates..."
                    )
                    for existing_txn in existing_by_details:
                        logger.debug(
                            f"[IMPORT] Removing duplicate: ID={existing_txn.id}, "
                            f"amount={existing_txn.amount}, description='{existing_txn.description}', "
                            f"booked_at={existing_txn.booked_at}"
                        )
                        db.delete(existing_txn)
                        deleted_count += 1
                else:
                    logger.debug(
                        f"[IMPORT] No duplicates found for: amount={txn_data['amount']}, "
                        f"description='{normalized_description}', booked_at={booked_date}"
                    )
                    # Also log what we're searching for to help debug
                    logger.debug(
                        f"[IMPORT] Search criteria: account_id={txn_data['account_id']}, "
                        f"user_id={user_id}, amount={txn_data['amount']}, "
                        f"description='{normalized_description}', date={booked_date}"
                    )
        
        logger.info(
            f"[IMPORT] Checked {checked_count} transactions for duplicates, "
            f"found and removed {deleted_count} duplicate(s)"
        )
        
        # Log summary of what was checked
        if checked_count > 0 and deleted_count == 0:
            logger.info(
                "[IMPORT] No duplicates found in pre-check. "
                "Will check again before inserting each transaction."
            )
        
        if deleted_count > 0:
            try:
                db.commit()
                logger.info(f"[IMPORT] Removed {deleted_count} duplicate transaction(s)")
            except Exception as e:
                db.rollback()
                logger.warning(f"[IMPORT] Error removing duplicates: {e}. Continuing with insert...")
        
        # Step 5: Insert transactions with categories
        logger.info("[IMPORT] Inserting transactions into database...")
        inserted_count = 0
        inserted_transactions = []  # Store transaction objects to get IDs after commit
        skipped_count = 0
        
        for idx, txn_data in enumerate(normalized_transactions):
            category_result = categorization_result.results[idx]
            
            try:
                # Check if transaction already exists (double-check before insert)
                # Check 1: By external_id if available
                if txn_data.get("external_id"):
                    existing_by_external_id = db.query(Transaction).filter(
                        Transaction.account_id == txn_data["account_id"],
                        Transaction.external_id == txn_data["external_id"],
                        Transaction.user_id == user_id
                    ).first()
                    
                    if existing_by_external_id:
                        logger.warning(
                            f"[IMPORT] Skipping duplicate transaction {idx} "
                            f"(account_id={txn_data['account_id']}, external_id={txn_data['external_id']})"
                        )
                        skipped_count += 1
                        continue
                
                # Check 2: By amount, description, and booked_at
                # Use date comparison (not exact datetime) to handle microsecond differences
                if txn_data.get("description") and txn_data.get("booked_at"):
                    # Normalize description for comparison (strip whitespace, case-insensitive)
                    normalized_description = txn_data["description"].strip() if txn_data["description"] else None
                    
                    # Extract date from booked_at (handle both datetime and date objects)
                    if isinstance(txn_data["booked_at"], datetime):
                        booked_date = txn_data["booked_at"].date()
                    elif hasattr(txn_data["booked_at"], 'date'):
                        booked_date = txn_data["booked_at"].date()
                    else:
                        booked_date = txn_data["booked_at"]
                    
                    # Query using date comparison and normalized description
                    from sqlalchemy import func, cast, Date
                    
                    query = db.query(Transaction).filter(
                        Transaction.account_id == txn_data["account_id"],
                        Transaction.user_id == user_id,
                        Transaction.amount == txn_data["amount"]
                    )
                    
                    # Add description filter (case-insensitive, trimmed)
                    if normalized_description:
                        query = query.filter(
                            func.lower(func.trim(Transaction.description)) == normalized_description.lower().strip()
                        )
                    
                    # Add date filter (compare dates, not exact datetime)
                    query = query.filter(
                        cast(Transaction.booked_at, Date) == booked_date
                    )
                    
                    # Execute query and log what we found
                    existing_by_details = query.first()
                    
                    # Log the query for debugging
                    logger.debug(
                        f"[IMPORT] Checking for duplicate transaction {idx}: "
                        f"account_id={txn_data['account_id']}, "
                        f"amount={txn_data['amount']}, "
                        f"description='{normalized_description}', "
                        f"booked_date={booked_date}"
                    )
                    
                    if existing_by_details:
                        logger.warning(
                            f"[IMPORT] Skipping duplicate transaction {idx} "
                            f"(matching amount={txn_data['amount']}, description='{normalized_description}', "
                            f"booked_at={booked_date})"
                        )
                        skipped_count += 1
                        continue
                
                # Create transaction
                transaction = Transaction(
                    user_id=user_id,
                    account_id=txn_data["account_id"],  # Already a UUID from the request
                    external_id=txn_data.get("external_id"),
                    transaction_type=txn_data["transaction_type"],
                    amount=txn_data["amount"],
                    currency=txn_data["currency"],
                    description=txn_data["description"],
                    merchant=txn_data["merchant"],
                    booked_at=txn_data["booked_at"],
                    category_id=category_result.category_id,  # Set equal to category_system_id initially
                    category_system_id=category_result.category_id,  # AI-assigned category
                    pending=False
                )
                
                db.add(transaction)
                inserted_transactions.append(transaction)  # Store for later ID retrieval
                inserted_count += 1
            except Exception as e:
                logger.error(f"[IMPORT] Error creating transaction {idx}: {e}")
                import traceback
                logger.error(traceback.format_exc())
                # Don't raise immediately - try to continue with other transactions
                skipped_count += 1
        
        try:
            db.commit()
            logger.info(f"[IMPORT] Committed {inserted_count} transactions (skipped {skipped_count})")
            
            # Refresh transactions to get their IDs
            for transaction in inserted_transactions:
                db.refresh(transaction)
            
            # Get transaction IDs
            inserted_ids = [str(txn.id) for txn in inserted_transactions]
            logger.info(f"[IMPORT] Inserted transaction IDs: {inserted_ids}")
            
            # Verify transactions were actually inserted by querying the database
            verified_count = db.query(Transaction).filter(
                Transaction.id.in_([txn.id for txn in inserted_transactions])
            ).count()
            
            if verified_count != inserted_count:
                logger.warning(
                    f"[IMPORT] Warning: Expected {inserted_count} transactions, "
                    f"but only {verified_count} found in database after commit"
                )
            else:
                logger.info(f"[IMPORT] Verified {verified_count} transactions in database")
        except Exception as e:
            db.rollback()
            error_msg = str(e)
            
            # Check if it's a duplicate key violation
            if "duplicate key" in error_msg.lower() or "unique constraint" in error_msg.lower():
                logger.error(
                    f"[IMPORT] Duplicate key violation detected: {error_msg}. "
                    f"This should not happen after duplicate removal. "
                    f"Please check the transactions and try again."
                )
                raise HTTPException(
                    status_code=409,  # Conflict
                    detail=f"Duplicate transaction detected. Some transactions may already exist. "
                           f"Original error: {error_msg}"
                )
            else:
                logger.error(f"[IMPORT] Error committing transactions: {e}")
                import traceback
                logger.error(traceback.format_exc())
                raise HTTPException(
                    status_code=500,
                    detail=f"Failed to commit transactions: {str(e)}"
                )
        
        if skipped_count > 0:
            logger.warning(f"[IMPORT] Skipped {skipped_count} duplicate transaction(s) during insert")
        
        logger.info(f"[IMPORT] Successfully inserted {inserted_count} transactions")
        
        # Step 5: Sync exchange rates
        exchange_rates_result = None
        if request.sync_exchange_rates:
            logger.info("[IMPORT] Syncing exchange rates...")
            try:
                # Get unique account IDs from imported transactions
                account_ids = list(set([txn["account_id"] for txn in normalized_transactions]))
                
                # Get account currencies (base currencies for exchange rate fetching)
                account_currencies = []
                for account_id in account_ids:
                    account = db.query(Account).filter(Account.id == account_id).first()
                    if account and account.currency:
                        if account.currency not in account_currencies:
                            account_currencies.append(account.currency)
                
                # If no account currencies found, default to EUR
                if not account_currencies:
                    account_currencies = ["EUR"]
                    logger.warning("[IMPORT] No account currencies found, defaulting to EUR")
                
                # Find earliest transaction date from imported transactions only
                if normalized_transactions:
                    earliest_date = min([
                        txn["booked_at"].date() if isinstance(txn["booked_at"], datetime) 
                        else (txn["booked_at"] if isinstance(txn["booked_at"], date) else datetime.now().date())
                        for txn in normalized_transactions
                    ])
                else:
                    earliest_date = datetime.now().date()
                
                end_date = datetime.now().date()
                
                logger.info(
                    f"[IMPORT] Fetching exchange rates for account currencies {account_currencies} "
                    f"from {earliest_date} to {end_date}"
                )
                
                # Fetch exchange rates for each account currency
                service = ExchangeRateService(db)
                total_rates_stored = 0
                
                for account_currency in account_currencies:
                    # Fetch rates for this account currency to EUR and USD
                    rates_by_date = service.fetch_exchange_rates_batch(
                        base_currency=account_currency,
                        target_currencies=["EUR", "USD"],
                        start_date=earliest_date,
                        end_date=end_date
                    )
                    
                    # Store the fetched rates for each date
                    stored_count = 0
                    for rate_date, rate_dict in rates_by_date.items():
                        # Store EUR rate if available
                        if "EUR" in rate_dict:
                            eur_stored = service.store_exchange_rates(
                                target_currency="EUR",
                                rates={account_currency: rate_dict["EUR"]},
                                for_date=rate_date
                            )
                            stored_count += eur_stored
                        
                        # Store USD rate if available
                        if "USD" in rate_dict:
                            usd_stored = service.store_exchange_rates(
                                target_currency="USD",
                                rates={account_currency: rate_dict["USD"]},
                                for_date=rate_date
                            )
                            stored_count += usd_stored
                    
                    total_rates_stored += stored_count
                    logger.info(
                        f"[IMPORT] Fetched and stored {stored_count} rates for {account_currency} -> EUR/USD"
                    )
                
                exchange_rates_result = {
                    "total_rates_stored": total_rates_stored,
                    "account_currencies": account_currencies,
                    "date_range": {
                        "start": earliest_date.isoformat(),
                        "end": end_date.isoformat()
                    }
                }
                logger.info(
                    f"[IMPORT] Exchange rates synced: "
                    f"{total_rates_stored} rates stored for currencies {account_currencies}"
                )
            except Exception as e:
                logger.error(f"[IMPORT] Error syncing exchange rates: {e}")
                import traceback
                logger.error(traceback.format_exc())
                exchange_rates_result = {"error": str(e)}
        
        # Step 7: Update functional amounts
        functional_amounts_result = None
        if request.update_functional_amounts:
            logger.info("[IMPORT] Updating functional amounts...")
            try:
                # Get user's functional currency
                user = db.query(User).filter(User.id == user_id).first()
                functional_currency = user.functional_currency if user else "EUR"
                
                # Update functional amounts for all user transactions
                transactions_to_update = db.query(Transaction).filter(
                    Transaction.user_id == user_id
                ).all()
                
                service = ExchangeRateService(db)
                updated_count = 0
                failed_count = 0
                skipped_count = 0
                
                for txn in transactions_to_update:
                    try:
                        txn_date = txn.booked_at.date()
                        
                        if txn.currency == functional_currency:
                            txn.functional_amount = txn.amount
                            skipped_count += 1
                        else:
                            exchange_rate = service.get_exchange_rate(
                                base_currency=txn.currency,
                                target_currency=functional_currency,
                                for_date=txn_date
                            )
                            
                            if exchange_rate:
                                txn.functional_amount = txn.amount * exchange_rate
                                updated_count += 1
                            else:
                                txn.functional_amount = None
                                failed_count += 1
                    except Exception as e:
                        logger.error(f"[IMPORT] Error updating functional amount for transaction {txn.id}: {e}")
                        failed_count += 1
                
                db.commit()
                functional_amounts_result = {
                    "updated": updated_count,
                    "skipped": skipped_count,
                    "failed": failed_count
                }
                logger.info(
                    f"[IMPORT] Functional amounts updated: "
                    f"{updated_count} updated, {skipped_count} skipped, {failed_count} failed"
                )
            except Exception as e:
                logger.error(f"[IMPORT] Error updating functional amounts: {e}")
                functional_amounts_result = {"error": str(e)}
        
        # Step 8: Calculate account balances
        balances_result = None
        balance_service = None
        if request.calculate_balances:
            logger.info("[IMPORT] Calculating account balances...")
            balance_service = AccountBalanceService(db)
            balances_result = balance_service.calculate_account_balances(user_id)
        
        # Step 9: Calculate and store account timeseries
        timeseries_result = None
        logger.info("[IMPORT] Calculating account timeseries...")
        if balance_service is None:
            balance_service = AccountBalanceService(db)
        timeseries_result = balance_service.calculate_account_timeseries(user_id)
        
        return TransactionImportResponse(
            success=True,
            message=f"Successfully imported {inserted_count} transactions",
            transactions_inserted=inserted_count,
            transaction_ids=inserted_ids if inserted_ids else None,
            categorization_summary={
                "total": categorization_result.total_transactions,
                "categorized": categorization_result.categorized_count,
                "deterministic": categorization_result.deterministic_count,
                "llm": categorization_result.llm_count,
                "uncategorized": categorization_result.uncategorized_count,
                "tokens_used": categorization_result.total_tokens_used,
                "cost_usd": categorization_result.total_cost_usd
            },
            exchange_rates_synced=exchange_rates_result,
            functional_amounts_updated=functional_amounts_result,
            balances_calculated=balances_result,
            timeseries_calculated=timeseries_result
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[IMPORT] Error importing transactions: {type(e).__name__}: {e}")
        import traceback
        logger.error(f"[IMPORT] Traceback:\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Import failed: {str(e)}")
