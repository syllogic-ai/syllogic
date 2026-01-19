"""
Service for calculating and managing account balances.
Handles:
1. Current account balance calculation (in account currency and functional currency)
2. Account timeseries calculation (daily balance snapshots)
"""
from datetime import datetime, date, timedelta
from decimal import Decimal
from typing import Dict, Optional
from sqlalchemy.orm import Session
from sqlalchemy import func, desc
import logging
import traceback

from app.models import Account, Transaction, User, ExchangeRate, AccountBalance

logger = logging.getLogger(__name__)


class AccountBalanceService:
    """Service for calculating account balances and timeseries."""

    def __init__(self, db: Session):
        self.db = db

    def calculate_account_balances(self, user_id: str, account_ids: Optional[list] = None) -> Dict:
        """
        Calculate current balances for accounts of a user.

        For each account:
        - Sums all transactions in account currency
        - Adds starting_balance
        - Converts to functional currency using latest exchange rate

        Args:
            user_id: User ID to calculate balances for
            account_ids: Optional list of specific account IDs to process. If None, processes all accounts.

        Returns:
            Dict with keys:
                - accounts_updated: Number of accounts successfully updated
                - accounts_failed: Number of accounts that failed
                - error: Error message if entire operation failed
        """
        try:
            # Get user's functional currency
            user = self.db.query(User).filter(User.id == user_id).first()
            functional_currency = user.functional_currency if user else "EUR"

            # Get accounts for user (filtered by account_ids if provided)
            query = self.db.query(Account).filter(Account.user_id == user_id)
            if account_ids:
                from uuid import UUID
                query = query.filter(Account.id.in_(account_ids))
                logger.info(f"[BALANCE] Processing {len(account_ids)} specific account(s)")
            accounts = query.all()
            
            updated_accounts = 0
            failed_accounts = 0
            
            for account in accounts:
                try:
                    # Sum all transactions for this account in account's currency
                    transaction_sum_result = self.db.query(func.sum(Transaction.amount)).filter(
                        Transaction.user_id == user_id,
                        Transaction.account_id == account.id
                    ).scalar()
                    
                    # Handle NULL result from sum() when no transactions exist
                    if transaction_sum_result is None:
                        transaction_sum = Decimal("0")
                    else:
                        transaction_sum = Decimal(str(transaction_sum_result))
                    
                    # Calculate balance in account's currency = sum(transactions) + starting_balance
                    starting_balance = account.starting_balance or Decimal("0")
                    balance_in_account_currency = transaction_sum + starting_balance
                    
                    # Convert to functional currency using latest available exchange rate
                    account_currency = account.currency or "EUR"
                    
                    if account_currency == functional_currency:
                        # Same currency, no conversion needed
                        functional_balance = balance_in_account_currency
                        logger.debug(
                            f"[BALANCE] Account {account.name}: "
                            f"transaction_sum={transaction_sum}, "
                            f"starting_balance={starting_balance}, "
                            f"balance_in_account_currency={balance_in_account_currency}, "
                            f"functional_balance={functional_balance} (no conversion)"
                        )
                    else:
                        # Get latest exchange rate from database
                        latest_rate_record = self.db.query(ExchangeRate).filter(
                            ExchangeRate.base_currency == account_currency,
                            ExchangeRate.target_currency == functional_currency
                        ).order_by(desc(ExchangeRate.date)).first()
                        
                        if latest_rate_record:
                            exchange_rate = latest_rate_record.rate
                            functional_balance = balance_in_account_currency * exchange_rate
                            
                            logger.debug(
                                f"[BALANCE] Account {account.name}: "
                                f"transaction_sum={transaction_sum}, "
                                f"starting_balance={starting_balance}, "
                                f"balance_in_account_currency={balance_in_account_currency} {account_currency}, "
                                f"exchange_rate={exchange_rate} (from {latest_rate_record.date.date()}), "
                                f"functional_balance={functional_balance} {functional_currency}"
                            )
                        else:
                            # No exchange rate found - log warning and use account currency balance
                            logger.warning(
                                f"[BALANCE] No exchange rate found for {account_currency} -> {functional_currency}. "
                                f"Using balance in account currency for account {account.name}"
                            )
                            functional_balance = balance_in_account_currency
                    
                    # Update the account
                    account.functional_balance = functional_balance
                    updated_accounts += 1
                    
                except Exception as e:
                    logger.error(f"[BALANCE] Error calculating balance for account {account.name}: {e}")
                    logger.error(traceback.format_exc())
                    failed_accounts += 1
                    # Continue with other accounts
                    continue
            
            self.db.commit()
            result = {
                "accounts_updated": updated_accounts,
                "accounts_failed": failed_accounts
            }
            logger.info(
                f"[BALANCE] Calculated balances for {updated_accounts} accounts "
                f"({failed_accounts} failed)"
            )
            return result
            
        except Exception as e:
            logger.error(f"[BALANCE] Error calculating balances: {e}")
            logger.error(traceback.format_exc())
            return {"error": str(e)}

    def calculate_account_timeseries(self, user_id: str, account_ids: Optional[list] = None) -> Dict:
        """
        Calculate and store daily balance snapshots (timeseries) for accounts of a user.

        For each account:
        - Gets minimum transaction date
        - Calculates balance for each day from min date to today
        - Stores balance in both account currency and functional currency
        - Uses exchange rate for each specific date

        Args:
            user_id: User ID to calculate timeseries for
            account_ids: Optional list of specific account IDs to process. If None, processes all accounts.

        Returns:
            Dict with keys:
                - accounts_processed: Number of accounts successfully processed
                - accounts_failed: Number of accounts that failed
                - total_days_processed: Total number of days processed across all accounts
                - total_records_stored: Total number of timeseries records stored
                - error: Error message if entire operation failed
        """
        try:
            # Get user's functional currency
            user = self.db.query(User).filter(User.id == user_id).first()
            functional_currency = user.functional_currency if user else "EUR"

            # Get accounts for user (filtered by account_ids if provided)
            query = self.db.query(Account).filter(Account.user_id == user_id)
            if account_ids:
                from uuid import UUID
                query = query.filter(Account.id.in_(account_ids))
                logger.info(f"[TIMESERIES] Processing {len(account_ids)} specific account(s)")
            accounts = query.all()
            
            total_days_processed = 0
            total_records_stored = 0
            failed_accounts = 0
            
            for account in accounts:
                try:
                    # Get minimum transaction date for this account
                    min_date_result = self.db.query(func.min(Transaction.booked_at)).filter(
                        Transaction.user_id == user_id,
                        Transaction.account_id == account.id
                    ).scalar()
                    
                    if not min_date_result:
                        logger.debug(f"[TIMESERIES] No transactions found for account {account.name}, skipping timeseries")
                        continue
                    
                    min_date = min_date_result.date() if isinstance(min_date_result, datetime) else min_date_result
                    end_date = datetime.now().date()
                    account_currency = account.currency or "EUR"
                    starting_balance = account.starting_balance or Decimal("0")
                    
                    logger.info(
                        f"[TIMESERIES] Calculating timeseries for account {account.name} "
                        f"from {min_date} to {end_date}"
                    )
                    
                    # Calculate balance for each day
                    current_date = min_date
                    days_processed = 0
                    records_stored = 0
                    
                    while current_date <= end_date:
                        # Calculate cumulative balance up to this date (in account currency)
                        # Sum all transactions up to and including this date
                        transaction_sum_result = self.db.query(func.sum(Transaction.amount)).filter(
                            Transaction.user_id == user_id,
                            Transaction.account_id == account.id,
                            func.date(Transaction.booked_at) <= current_date
                        ).scalar()
                        
                        if transaction_sum_result is None:
                            transaction_sum = Decimal("0")
                        else:
                            transaction_sum = Decimal(str(transaction_sum_result))
                        
                        # Balance in account currency = starting_balance + sum of transactions up to this date
                        balance_in_account_currency = starting_balance + transaction_sum
                        
                        # Convert to functional currency using exchange rate for this specific date
                        if account_currency == functional_currency:
                            balance_in_functional_currency = balance_in_account_currency
                        else:
                            # Get exchange rate for this specific date
                            rate_datetime = datetime.combine(current_date, datetime.min.time())
                            exchange_rate_record = self.db.query(ExchangeRate).filter(
                                ExchangeRate.date == rate_datetime,
                                ExchangeRate.base_currency == account_currency,
                                ExchangeRate.target_currency == functional_currency
                            ).first()
                            
                            if exchange_rate_record:
                                exchange_rate = exchange_rate_record.rate
                                balance_in_functional_currency = balance_in_account_currency * exchange_rate
                            else:
                                # Try to find closest available rate (within 7 days)
                                found_rate = None
                                for days_back in range(8):
                                    check_date = rate_datetime - timedelta(days=days_back)
                                    closest_rate = self.db.query(ExchangeRate).filter(
                                        ExchangeRate.date == check_date,
                                        ExchangeRate.base_currency == account_currency,
                                        ExchangeRate.target_currency == functional_currency
                                    ).first()
                                    if closest_rate:
                                        found_rate = closest_rate.rate
                                        break
                                
                                if found_rate:
                                    balance_in_functional_currency = balance_in_account_currency * found_rate
                                else:
                                    # No rate found - use account currency balance
                                    logger.warning(
                                        f"[TIMESERIES] No exchange rate found for {account_currency} -> {functional_currency} "
                                        f"on {current_date} for account {account.name}. Using account currency balance."
                                    )
                                    balance_in_functional_currency = balance_in_account_currency
                        
                        # Check if timeseries record already exists for this account and date
                        rate_datetime = datetime.combine(current_date, datetime.min.time())
                        existing_timeseries = self.db.query(AccountBalance).filter(
                            AccountBalance.account_id == account.id,
                            AccountBalance.date == rate_datetime
                        ).first()
                        
                        if existing_timeseries:
                            # Update existing record
                            existing_timeseries.balance_in_account_currency = balance_in_account_currency
                            existing_timeseries.balance_in_functional_currency = balance_in_functional_currency
                            existing_timeseries.updated_at = datetime.utcnow()
                        else:
                            # Create new record
                            timeseries_record = AccountBalance(
                                account_id=account.id,
                                date=rate_datetime,
                                balance_in_account_currency=balance_in_account_currency,
                                balance_in_functional_currency=balance_in_functional_currency
                            )
                            self.db.add(timeseries_record)
                        
                        records_stored += 1
                        days_processed += 1
                        current_date += timedelta(days=1)
                    
                    total_days_processed += days_processed
                    total_records_stored += records_stored
                    
                    logger.info(
                        f"[TIMESERIES] Stored {records_stored} timeseries records for account {account.name} "
                        f"({days_processed} days)"
                    )
                    
                except Exception as e:
                    logger.error(f"[TIMESERIES] Error calculating timeseries for account {account.name}: {e}")
                    logger.error(traceback.format_exc())
                    failed_accounts += 1
                    continue
            
            self.db.commit()
            result = {
                "accounts_processed": len(accounts) - failed_accounts,
                "accounts_failed": failed_accounts,
                "total_days_processed": total_days_processed,
                "total_records_stored": total_records_stored
            }
            logger.info(
                f"[TIMESERIES] Timeseries calculation complete: "
                f"{total_records_stored} records stored across {total_days_processed} days "
                f"for {len(accounts) - failed_accounts} accounts"
            )
            return result
            
        except Exception as e:
            logger.error(f"[TIMESERIES] Error calculating timeseries: {e}")
            logger.error(traceback.format_exc())
            return {"error": str(e)}
