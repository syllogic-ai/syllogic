"""
Service for syncing bank data (accounts and transactions).
"""
from typing import List, Optional, Dict, Any
from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy import or_
from decimal import Decimal

from app.models import Account, Transaction
from app.integrations.base import BankAdapter, AccountData, TransactionData
from app.services.category_matcher import CategoryMatcher
from app.services.subscription_matcher import SubscriptionMatcher
from app.services.subscription_detector import SubscriptionDetector
from app.services.merchant_extractor import extract_merchant
from app.db_helpers import get_user_id
from app.security.data_encryption import (
    blind_index,
    blind_index_candidates,
    decrypt_with_fallback,
    encrypt_value,
)


class SyncService:
    """Service for syncing bank data."""

    def __init__(self, db: Session, user_id: Optional[str] = None, use_llm_categorization: bool = True):
        self.db = db
        self.user_id = get_user_id(user_id)
        self.category_matcher = CategoryMatcher(db, user_id=self.user_id)
        self.subscription_matcher = SubscriptionMatcher(db, user_id=self.user_id)
        self.use_llm_categorization = use_llm_categorization

    @staticmethod
    def _resolve_account_external_id(account: Account) -> Optional[str]:
        return decrypt_with_fallback(account.external_id_ciphertext, account.external_id)

    @staticmethod
    def _set_account_external_id_fields(account: Account, external_id: Optional[str]) -> None:
        encrypted = encrypt_value(external_id)
        hashed = blind_index(external_id)
        account.external_id_hash = hashed
        if encrypted:
            account.external_id_ciphertext = encrypted
            account.external_id = external_id
        else:
            account.external_id_ciphertext = None
            account.external_id = external_id

    def _find_existing_account(self, provider: str, external_id: Optional[str]) -> Optional[Account]:
        query = self.db.query(Account).filter(
            Account.user_id == self.user_id,
            Account.provider == provider,
        )
        hashed_candidates = blind_index_candidates(external_id)
        if hashed_candidates:
            return query.filter(
                or_(
                    Account.external_id_hash.in_(hashed_candidates),
                    Account.external_id == external_id,
                )
            ).first()
        return query.filter(Account.external_id == external_id).first()
    
    def sync_accounts(self, adapter: BankAdapter, provider: str) -> List[Account]:
        """
        Sync accounts from bank adapter to database.
        
        Args:
            adapter: Bank adapter instance
            provider: Provider name (e.g., 'revolut')
            
        Returns:
            List of synced Account objects
        """
        account_data_list = adapter.fetch_accounts()
        synced_accounts = []
        
        for account_data in account_data_list:
            # Check if account already exists
            existing_account = self._find_existing_account(provider, account_data.external_id)
            
            if existing_account:
                # Update existing account
                existing_account.name = account_data.name
                existing_account.account_type = account_data.account_type
                existing_account.institution = account_data.institution
                existing_account.currency = account_data.currency
                # Only update balance if provided from CSV (not None), otherwise keep existing or calculate later
                # balance_current removed - use functional_balance instead
                existing_account.balance_available = account_data.balance_available
                self._set_account_external_id_fields(existing_account, account_data.external_id)
                existing_account.is_active = True
                synced_accounts.append(existing_account)
            else:
                # Create new account
                # Don't set balance here - it will be calculated from transactions after sync
                new_account = Account(
                    user_id=self.user_id,
                    name=account_data.name,
                    account_type=account_data.account_type,
                    institution=account_data.institution,
                    currency=account_data.currency,
                    provider=provider,
                    balance_available=account_data.balance_available,
                )
                self._set_account_external_id_fields(new_account, account_data.external_id)
                self.db.add(new_account)
                synced_accounts.append(new_account)
        
        self.db.commit()
        
        # Refresh all accounts
        for account in synced_accounts:
            self.db.refresh(account)
        
        return synced_accounts
    
    def sync_transactions(
        self,
        adapter: BankAdapter,
        account: Account,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> tuple[int, int, List[str]]:
        """
        Sync transactions for an account.

        Args:
            adapter: Bank adapter instance
            account: Account to sync transactions for
            start_date: Optional start date for transaction range
            end_date: Optional end date for transaction range

        Returns:
            Tuple of (created_count, updated_count, created_transaction_ids)
        """
        resolved_account_external_id = self._resolve_account_external_id(account)
        if not resolved_account_external_id:
            raise ValueError(f"Account {account.id} is missing provider external_id.")

        transaction_data_list = adapter.fetch_transactions(
            resolved_account_external_id,
            start_date=start_date,
            end_date=end_date,
        )

        created_count = 0
        updated_count = 0
        created_transaction_ids: List[str] = []

        for transaction_data in transaction_data_list:
            # Try to auto-categorize the transaction
            category = self.category_matcher.match_category(
                description=transaction_data.description,
                merchant=transaction_data.merchant,
                amount=transaction_data.amount,
                transaction_type=transaction_data.transaction_type,
                use_llm=self.use_llm_categorization
            )

            # Check if transaction already exists
            existing_transaction = self.db.query(Transaction).filter(
                Transaction.user_id == self.user_id,
                Transaction.account_id == account.id,
                Transaction.external_id == transaction_data.external_id
            ).first()

            # Try to extract/improve merchant from description if empty
            merchant = transaction_data.merchant
            if not merchant and transaction_data.description:
                merchant = extract_merchant(transaction_data.description)

            # Try to auto-match to subscription (only for expenses without existing link)
            matched_subscription = None
            if float(transaction_data.amount) < 0:  # Only expenses
                matched_subscription = self.subscription_matcher.match_transaction(
                    description=transaction_data.description,
                    merchant=merchant,
                    amount=Decimal(str(transaction_data.amount)),
                    account_id=str(account.id),
                )

            if existing_transaction:
                # Update existing transaction
                existing_transaction.amount = transaction_data.amount
                existing_transaction.currency = transaction_data.currency
                existing_transaction.description = transaction_data.description
                existing_transaction.merchant = merchant or transaction_data.merchant
                existing_transaction.booked_at = transaction_data.booked_at
                existing_transaction.transaction_type = transaction_data.transaction_type
                existing_transaction.pending = transaction_data.pending
                # Only update category_system_id if user hasn't overridden (preserve user's manual categorization)
                if not existing_transaction.category_id and category:
                    existing_transaction.category_system_id = category.id
                # Only set subscription link if not already set (preserve manual links)
                if not existing_transaction.recurring_transaction_id and matched_subscription:
                    existing_transaction.recurring_transaction_id = matched_subscription.id
                updated_count += 1
            else:
                # Create new transaction
                new_transaction = Transaction(
                    user_id=self.user_id,
                    account_id=account.id,
                    external_id=transaction_data.external_id,
                    transaction_type=transaction_data.transaction_type,
                    amount=transaction_data.amount,
                    currency=transaction_data.currency,
                    description=transaction_data.description,
                    merchant=merchant or transaction_data.merchant,
                    booked_at=transaction_data.booked_at,
                    pending=transaction_data.pending,
                    category_system_id=category.id if category else None,  # Use category_system_id for AI-assigned
                    recurring_transaction_id=matched_subscription.id if matched_subscription else None,
                )
                self.db.add(new_transaction)
                self.db.flush()  # Flush to get the ID
                created_transaction_ids.append(str(new_transaction.id))
                created_count += 1

        self.db.commit()

        return (created_count, updated_count, created_transaction_ids)
    
    def sync_all(
        self,
        adapter: BankAdapter,
        provider: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        detect_subscriptions: bool = True,
    ) -> dict:
        """
        Sync both accounts and transactions.

        Args:
            adapter: Bank adapter instance
            provider: Provider name
            start_date: Optional start date for transaction range
            end_date: Optional end date for transaction range
            detect_subscriptions: Whether to detect subscription patterns

        Returns:
            Dict with sync results including subscriptions_detected
        """
        # Sync accounts first
        accounts = self.sync_accounts(adapter, provider)

        # For Revolut, permanently delete old "Revolut default" accounts if they exist
        if provider == 'revolut':
            from app.models import Transaction
            old_default_accounts = self.db.query(Account).filter(
                Account.user_id == self.user_id,
                Account.provider == 'revolut',
                or_(
                    Account.external_id == 'revolut_default',
                    Account.external_id_hash.in_(blind_index_candidates("revolut_default")),
                )
            ).all()
            for old_account in old_default_accounts:
                # Delete associated transactions first
                self.db.query(Transaction).filter(
                    Transaction.user_id == self.user_id,
                    Transaction.account_id == old_account.id
                ).delete()
                # Then delete the account
                self.db.delete(old_account)
            if old_default_accounts:
                self.db.commit()

        # Sync transactions for each account
        total_created = 0
        total_updated = 0
        all_created_ids: List[str] = []

        for account in accounts:
            created, updated, created_ids = self.sync_transactions(
                adapter,
                account,
                start_date=start_date,
                end_date=end_date,
            )
            total_created += created
            total_updated += updated
            all_created_ids.extend(created_ids)

        # After syncing transactions, update functional_balance from sum of all transactions
        # This ensures the balance is always accurate based on the transactions in the database
        from sqlalchemy import func
        from decimal import Decimal
        for account in accounts:
            # Calculate balance from sum of all transactions for this account
            transaction_sum_result = self.db.query(func.sum(Transaction.amount)).filter(
                Transaction.user_id == self.user_id,
                Transaction.account_id == account.id
            ).scalar()

            if transaction_sum_result is None:
                transaction_sum = Decimal("0")
            else:
                transaction_sum = Decimal(str(transaction_sum_result))

            # Calculate functional_balance = sum(transactions) + starting_balance
            starting_balance = account.starting_balance or Decimal("0")
            account.functional_balance = transaction_sum + starting_balance
            self.db.commit()

        # Detect subscription patterns from newly created transactions
        subscriptions_detected = 0
        if detect_subscriptions:
            detector = SubscriptionDetector(self.db, self.user_id)
            detection_result = detector.detect_and_apply(all_created_ids or None)
            subscriptions_detected = detection_result.get("detected_count", 0)

        return {
            'accounts_synced': len(accounts),
            'transactions_created': total_created,
            'transactions_updated': total_updated,
            'subscriptions_detected': subscriptions_detected,
        }

    def upsert_transaction(
        self,
        account_id: str,
        transaction_data: TransactionData
    ) -> Dict[str, Any]:
        """
        Upsert a single transaction (create or update).

        Used by Ponto sync which handles transactions individually.

        Args:
            account_id: Account ID (UUID string)
            transaction_data: Transaction data from bank adapter

        Returns:
            Dict with keys: created (bool), updated (bool), transaction_id (str)
        """
        # Get the account
        account = self.db.query(Account).filter(
            Account.id == account_id,
            Account.user_id == self.user_id
        ).first()

        if not account:
            raise ValueError(f"Account {account_id} not found for user {self.user_id}")

        # Try to auto-categorize the transaction
        category = self.category_matcher.match_category(
            description=transaction_data.description,
            merchant=transaction_data.merchant,
            amount=transaction_data.amount,
            transaction_type=transaction_data.transaction_type,
            use_llm=self.use_llm_categorization
        )

        # Try to extract/improve merchant from description if empty
        merchant = transaction_data.merchant
        if not merchant and transaction_data.description:
            merchant = extract_merchant(transaction_data.description)

        # Try to auto-match to subscription (only for expenses)
        matched_subscription = None
        if float(transaction_data.amount) < 0:  # Only expenses
            matched_subscription = self.subscription_matcher.match_transaction(
                description=transaction_data.description,
                merchant=merchant,
                amount=Decimal(str(transaction_data.amount)),
                account_id=str(account.id),
            )

        # Check if transaction already exists
        existing_transaction = self.db.query(Transaction).filter(
            Transaction.user_id == self.user_id,
            Transaction.account_id == account.id,
            Transaction.external_id == transaction_data.external_id
        ).first()

        if existing_transaction:
            # Update existing transaction
            existing_transaction.amount = transaction_data.amount
            existing_transaction.currency = transaction_data.currency
            existing_transaction.description = transaction_data.description
            existing_transaction.merchant = merchant or transaction_data.merchant
            existing_transaction.booked_at = transaction_data.booked_at
            existing_transaction.transaction_type = transaction_data.transaction_type
            existing_transaction.pending = transaction_data.pending

            # Only update category_system_id if user hasn't overridden
            if not existing_transaction.category_id and category:
                existing_transaction.category_system_id = category.id

            # Only set subscription link if not already set (preserve manual links)
            if not existing_transaction.recurring_transaction_id and matched_subscription:
                existing_transaction.recurring_transaction_id = matched_subscription.id

            self.db.commit()
            self.db.refresh(existing_transaction)

            return {
                'created': False,
                'updated': True,
                'transaction_id': str(existing_transaction.id)
            }
        else:
            # Create new transaction
            new_transaction = Transaction(
                user_id=self.user_id,
                account_id=account.id,
                external_id=transaction_data.external_id,
                transaction_type=transaction_data.transaction_type,
                amount=transaction_data.amount,
                currency=transaction_data.currency,
                description=transaction_data.description,
                merchant=merchant or transaction_data.merchant,
                booked_at=transaction_data.booked_at,
                pending=transaction_data.pending,
                category_system_id=category.id if category else None,
                recurring_transaction_id=matched_subscription.id if matched_subscription else None,
            )
            self.db.add(new_transaction)
            self.db.commit()
            self.db.refresh(new_transaction)

            return {
                'created': True,
                'updated': False,
                'transaction_id': str(new_transaction.id)
            }
