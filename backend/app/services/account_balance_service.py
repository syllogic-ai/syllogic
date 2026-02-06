"""
Service for calculating and managing account balances.
Handles:
1. Current account balance calculation (in account currency and functional currency)
2. Account timeseries calculation (daily balance snapshots)
3. Importing daily balances from CSV files
"""
from datetime import datetime, date, timedelta
from decimal import Decimal
from typing import Dict, Optional, List, Set
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

    def calculate_account_timeseries(
        self,
        user_id: str,
        account_ids: Optional[list] = None,
        skip_dates: Optional[Dict[str, Set[date]]] = None
    ) -> Dict:
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
            skip_dates: Optional dict mapping account_id (string) to set of dates to skip.
                       These dates already have authoritative balance data from CSV import.

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
                        # No transactions - use account created_at date or today as starting point
                        # This ensures accounts with only starting balance still appear in analytics
                        logger.info(f"[TIMESERIES] No transactions found for account {account.name}, using starting balance only")

                        # Use account creation date, or today if not available
                        if account.created_at:
                            min_date = account.created_at.date() if isinstance(account.created_at, datetime) else account.created_at
                        else:
                            min_date = datetime.now().date()
                    else:
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
                    skipped_count = 0

                    # Get skip dates for this account (if any)
                    account_skip_dates = skip_dates.get(str(account.id), set()) if skip_dates else set()

                    # Get the max date with CSV data to know when to carry forward balances
                    max_csv_date = max(account_skip_dates) if account_skip_dates else None

                    # Track last known balance for carry-forward
                    last_known_balance_account = None
                    last_known_balance_functional = None

                    while current_date <= end_date:
                        # Skip dates that already have authoritative balance data from CSV
                        if current_date in account_skip_dates:
                            # Get the balance from account_balances to track for carry-forward
                            rate_datetime = datetime.combine(current_date, datetime.min.time())
                            existing_entry = self.db.query(AccountBalance).filter(
                                AccountBalance.account_id == account.id,
                                AccountBalance.date == rate_datetime
                            ).first()
                            if existing_entry:
                                last_known_balance_account = existing_entry.balance_in_account_currency
                                last_known_balance_functional = existing_entry.balance_in_functional_currency

                            logger.debug(
                                f"[TIMESERIES] Skipping {current_date} for account {account.name} "
                                f"(has authoritative balance from CSV: {last_known_balance_account})"
                            )
                            current_date += timedelta(days=1)
                            skipped_count += 1
                            continue

                        # For dates after the last CSV date, check if there are transactions on THIS specific date
                        # If no transactions and we have a last known balance, carry it forward
                        if max_csv_date and current_date > max_csv_date and last_known_balance_account is not None:
                            # Check if there are any transactions on this specific date
                            transactions_on_date = self.db.query(func.count(Transaction.id)).filter(
                                Transaction.user_id == user_id,
                                Transaction.account_id == account.id,
                                func.date(Transaction.booked_at) == current_date
                            ).scalar()

                            if not transactions_on_date or transactions_on_date == 0:
                                # No transactions on this date - carry forward the last known balance
                                balance_in_account_currency = last_known_balance_account
                                balance_in_functional_currency = last_known_balance_functional

                                # Store this balance
                                rate_datetime = datetime.combine(current_date, datetime.min.time())
                                existing_timeseries = self.db.query(AccountBalance).filter(
                                    AccountBalance.account_id == account.id,
                                    AccountBalance.date == rate_datetime
                                ).first()

                                if not existing_timeseries:
                                    timeseries_record = AccountBalance(
                                        account_id=account.id,
                                        date=rate_datetime,
                                        balance_in_account_currency=balance_in_account_currency,
                                        balance_in_functional_currency=balance_in_functional_currency
                                    )
                                    self.db.add(timeseries_record)
                                    records_stored += 1
                                    logger.debug(
                                        f"[TIMESERIES] Carried forward balance for {current_date}: "
                                        f"{balance_in_account_currency} (no transactions after CSV data)"
                                    )
                                else:
                                    skipped_count += 1

                                days_processed += 1
                                current_date += timedelta(days=1)
                                continue

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
                            # Only skip if this date is in skip_dates (has authoritative CSV data)
                            # Otherwise, update the record with newly calculated balance from transactions
                            if current_date in account_skip_dates:
                                # Preserve CSV data - don't overwrite
                                logger.debug(
                                    f"[TIMESERIES] Preserving CSV balance for {current_date}: "
                                    f"{existing_timeseries.balance_in_account_currency} (not overwriting with calculated {balance_in_account_currency})"
                                )
                                skipped_count += 1
                            else:
                                # Update existing record with newly calculated balance
                                existing_timeseries.balance_in_account_currency = balance_in_account_currency
                                existing_timeseries.balance_in_functional_currency = balance_in_functional_currency
                                records_stored += 1
                                logger.debug(
                                    f"[TIMESERIES] Updated existing balance for {current_date}: "
                                    f"{balance_in_account_currency} (recalculated from transactions)"
                                )
                        else:
                            # Create new record only if no existing entry
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

                    if skipped_count > 0:
                        logger.info(
                            f"[TIMESERIES] Stored {records_stored} timeseries records for account {account.name} "
                            f"({days_processed} days calculated, {skipped_count} days skipped - using CSV balances)"
                        )
                    else:
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

            # Update each account's functional_balance from the latest account_balances entry
            # This ensures functional_balance reflects the actual balance (including fees from CSV)
            for account in accounts:
                try:
                    latest_balance = self.db.query(AccountBalance).filter(
                        AccountBalance.account_id == account.id
                    ).order_by(desc(AccountBalance.date)).first()

                    if latest_balance:
                        account.functional_balance = latest_balance.balance_in_functional_currency
                        logger.debug(
                            f"[TIMESERIES] Updated {account.name} functional_balance to "
                            f"{latest_balance.balance_in_functional_currency} from {latest_balance.date.date()}"
                        )
                except Exception as e:
                    logger.error(f"[TIMESERIES] Error updating functional_balance for {account.name}: {e}")

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

    def import_daily_balances(
        self,
        account_id: str,
        daily_balances: List[Dict],
        functional_currency: str
    ) -> Dict:
        """
        Store provided daily balances directly in account_balances table.
        These balances are authoritative values from the CSV file.

        Args:
            account_id: Account ID to store balances for
            daily_balances: List of dicts with 'date' (YYYY-MM-DD) and 'balance' keys
            functional_currency: User's functional currency for conversion

        Returns:
            Dict with keys:
                - imported_dates: Set of dates that were imported
                - records_stored: Number of balance records stored
                - error: Error message if operation failed
        """
        try:
            # Get account for currency info
            account = self.db.query(Account).filter(Account.id == account_id).first()
            if not account:
                return {"error": f"Account {account_id} not found", "imported_dates": set()}

            account_currency = account.currency or "EUR"

            imported_dates: Set[date] = set()
            records_stored = 0

            logger.info(
                f"[BALANCE_IMPORT] Importing {len(daily_balances)} daily balances for account {account.name}"
            )

            for balance_data in daily_balances:
                try:
                    # Parse date
                    date_str = balance_data.get("date")
                    if not date_str:
                        continue

                    # Parse the date string (YYYY-MM-DD format)
                    balance_date = datetime.strptime(date_str, "%Y-%m-%d").date()
                    balance_value = Decimal(str(balance_data.get("balance", 0)))

                    # Convert to functional currency if needed
                    if account_currency == functional_currency:
                        functional_balance = balance_value
                    else:
                        # Get exchange rate for this specific date
                        rate_datetime = datetime.combine(balance_date, datetime.min.time())
                        exchange_rate_record = self.db.query(ExchangeRate).filter(
                            ExchangeRate.date == rate_datetime,
                            ExchangeRate.base_currency == account_currency,
                            ExchangeRate.target_currency == functional_currency
                        ).first()

                        if exchange_rate_record:
                            functional_balance = balance_value * exchange_rate_record.rate
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
                                functional_balance = balance_value * found_rate
                            else:
                                # No rate found - use account currency balance
                                logger.warning(
                                    f"[BALANCE_IMPORT] No exchange rate found for {account_currency} -> "
                                    f"{functional_currency} on {balance_date}. Using account currency balance."
                                )
                                functional_balance = balance_value

                    # Upsert into account_balances
                    rate_datetime = datetime.combine(balance_date, datetime.min.time())
                    existing = self.db.query(AccountBalance).filter(
                        AccountBalance.account_id == account_id,
                        AccountBalance.date == rate_datetime
                    ).first()

                    if existing:
                        # Update existing record
                        existing.balance_in_account_currency = balance_value
                        existing.balance_in_functional_currency = functional_balance
                        existing.updated_at = datetime.utcnow()
                        logger.debug(
                            f"[BALANCE_IMPORT] Updated balance for {balance_date}: {balance_value} {account_currency}"
                        )
                    else:
                        # Create new record
                        new_balance = AccountBalance(
                            account_id=account_id,
                            date=rate_datetime,
                            balance_in_account_currency=balance_value,
                            balance_in_functional_currency=functional_balance
                        )
                        self.db.add(new_balance)
                        logger.debug(
                            f"[BALANCE_IMPORT] Created balance for {balance_date}: {balance_value} {account_currency}"
                        )

                    imported_dates.add(balance_date)
                    records_stored += 1

                except Exception as e:
                    logger.error(f"[BALANCE_IMPORT] Error importing balance for date {balance_data}: {e}")
                    continue

            self.db.commit()

            logger.info(
                f"[BALANCE_IMPORT] Imported {records_stored} daily balances for account {account.name} "
                f"({len(imported_dates)} unique dates)"
            )

            return {
                "imported_dates": imported_dates,
                "records_stored": records_stored
            }

        except Exception as e:
            logger.error(f"[BALANCE_IMPORT] Error importing daily balances: {e}")
            logger.error(traceback.format_exc())
            self.db.rollback()
            return {"error": str(e), "imported_dates": set()}
