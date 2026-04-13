"""
Service for automatically matching transactions to subscriptions during bank sync.

Follows the CategoryMatcher pattern:
- Caches active subscriptions per user
- Matches transactions based on text similarity and amount tolerance
- Never overwrites existing recurring_transaction_id

Usage:
    matcher = SubscriptionMatcher(db, user_id)
    subscription = matcher.match_transaction(
        description="Netflix Monthly",
        merchant="Netflix",
        amount=Decimal("-15.99")
    )
    if subscription:
        transaction.recurring_transaction_id = subscription.id
"""
import os
import logging
from typing import Optional, List, Dict
from decimal import Decimal
from uuid import UUID
from sqlalchemy.orm import Session
from sqlalchemy import or_

from app.models import RecurringTransaction
from app.db_helpers import get_user_id
from app.services.text_similarity import TextSimilarity
from app.services.merchant_extractor import MerchantExtractor

logger = logging.getLogger(__name__)


# Configuration
ENABLE_AUTO_SUBSCRIPTION_MATCHING = os.getenv(
    "ENABLE_AUTO_SUBSCRIPTION_MATCHING", "true"
).lower() == "true"

# Minimum match score required to auto-link (0-100)
MIN_MATCH_SCORE = float(os.getenv("SUBSCRIPTION_MIN_MATCH_SCORE", "60.0"))

# Amount tolerance (percentage difference allowed)
AMOUNT_TOLERANCE_PERCENT = float(os.getenv("SUBSCRIPTION_AMOUNT_TOLERANCE", "0.05"))


class SubscriptionMatcher:
    """
    Service for matching transactions to existing subscriptions.

    Caches active subscriptions per user for efficient matching during sync.
    """

    def __init__(self, db: Session, user_id: Optional[str] = None):
        """
        Initialize the SubscriptionMatcher.

        Args:
            db: SQLAlchemy database session
            user_id: User ID. If None, uses system user.
        """
        self.db = db
        self.user_id = user_id if user_id else get_user_id(user_id)
        self._subscription_cache: Dict[Optional[str], List[RecurringTransaction]] = {}
        self._text_similarity = TextSimilarity()
        self._merchant_extractor = MerchantExtractor()

    def _load_subscriptions(
        self,
        account_id: Optional[str] = None
    ) -> List[RecurringTransaction]:
        """
        Load and cache active subscriptions for the user.

        Returns:
            List of active RecurringTransaction objects
        """
        cache_key = str(account_id) if account_id else None
        if cache_key not in self._subscription_cache:
            account_uuid = None
            if cache_key:
                try:
                    account_uuid = UUID(cache_key)
                except (ValueError, TypeError):
                    account_uuid = None

            query = self.db.query(RecurringTransaction).filter(
                RecurringTransaction.user_id == self.user_id,
                RecurringTransaction.is_active == True
            )
            if account_uuid:
                query = query.filter(
                    or_(
                        RecurringTransaction.account_id == account_uuid,
                        RecurringTransaction.account_id.is_(None),
                    )
                )

            subscriptions = query.all()
            self._subscription_cache[cache_key] = subscriptions

            logger.debug(
                f"[SUBSCRIPTION_MATCHER] Loaded {len(subscriptions)} "
                f"active subscriptions for user {self.user_id} (account={cache_key or 'any'})"
            )

        return self._subscription_cache[cache_key]

    def clear_cache(self):
        """Clear the subscription cache. Call after subscription updates."""
        self._subscription_cache = {}

    @staticmethod
    def _amount_matches(
        subscription_amount: Decimal,
        transaction_amount: Decimal,
        tolerance_percent: float = AMOUNT_TOLERANCE_PERCENT
    ) -> bool:
        """
        Check if transaction amount matches subscription amount within tolerance.

        Args:
            subscription_amount: Expected subscription amount (positive)
            transaction_amount: Transaction amount (can be negative for expenses)
            tolerance_percent: Maximum percentage difference allowed

        Returns:
            True if amounts match within tolerance
        """
        # Use absolute values for comparison
        sub_amount = abs(float(subscription_amount))
        txn_amount = abs(float(transaction_amount))

        if sub_amount == 0 or txn_amount == 0:
            return False

        # Calculate percentage difference
        diff = abs(sub_amount - txn_amount)
        avg = (sub_amount + txn_amount) / 2

        if avg == 0:
            return False

        percentage_diff = diff / avg
        return percentage_diff <= tolerance_percent

    def _calculate_match_score(
        self,
        subscription: RecurringTransaction,
        description: Optional[str],
        merchant: Optional[str],
        amount: Decimal
    ) -> tuple[float, str]:
        """
        Calculate match score between a subscription and transaction.

        Args:
            subscription: Subscription to match against
            description: Transaction description
            merchant: Transaction merchant
            amount: Transaction amount

        Returns:
            Tuple of (score 0-100, match_reason)
        """
        # Amount check is a prerequisite
        if not self._amount_matches(subscription.amount, amount):
            return 0.0, "amount_mismatch"

        # Calculate text similarity
        text_score, method = self._text_similarity.calculate_match_score(
            subscription_name=subscription.name,
            subscription_merchant=subscription.merchant,
            transaction_description=description,
            transaction_merchant=merchant
        )

        if text_score == 0:
            return 0.0, "no_text_match"

        # Boost score if amount is exact match
        sub_amount = abs(float(subscription.amount))
        txn_amount = abs(float(amount))
        if abs(sub_amount - txn_amount) < 0.01:  # Exact match within 1 cent
            text_score = min(text_score + 10, 100)

        return text_score, method

    def match_transaction(
        self,
        description: Optional[str],
        merchant: Optional[str],
        amount: Decimal,
        account_id: Optional[str] = None,
        min_score: float = MIN_MATCH_SCORE
    ) -> Optional[RecurringTransaction]:
        """
        Find the best matching subscription for a transaction.

        Args:
            description: Transaction description
            merchant: Transaction merchant (may be None)
            amount: Transaction amount
            min_score: Minimum match score required (0-100)

        Returns:
            Best matching RecurringTransaction or None if no match found
        """
        if not ENABLE_AUTO_SUBSCRIPTION_MATCHING:
            return None

        # Skip income transactions (subscriptions are expenses)
        if float(amount) > 0:
            return None

        # Try to extract merchant if not provided
        if not merchant and description:
            extraction = self._merchant_extractor.extract(description)
            if extraction.merchant and extraction.confidence >= 60:
                merchant = extraction.merchant

        # Load subscriptions
        subscriptions = self._load_subscriptions(account_id=account_id)

        if not subscriptions:
            return None

        best_match = None
        best_score = 0.0
        best_reason = ""

        for subscription in subscriptions:
            score, reason = self._calculate_match_score(
                subscription=subscription,
                description=description,
                merchant=merchant,
                amount=amount
            )

            # Prefer account-scoped matches over legacy account-agnostic matches.
            if account_id and subscription.account_id:
                if str(subscription.account_id) == str(account_id):
                    score = min(100.0, score + 5)
            elif account_id and not subscription.account_id:
                score = max(0.0, score - 5)

            if score > best_score:
                best_score = score
                best_match = subscription
                best_reason = reason

        # Only return if score meets threshold
        if best_match and best_score >= min_score:
            logger.info(
                f"[SUBSCRIPTION_MATCHER] Matched transaction to '{best_match.name}' "
                f"(score: {best_score:.1f}%, reason: {best_reason})"
            )
            return best_match

        if best_match:
            logger.debug(
                f"[SUBSCRIPTION_MATCHER] Best match '{best_match.name}' "
                f"score {best_score:.1f}% below threshold {min_score}%"
            )

        return None

    def match_transactions_batch(
        self,
        transactions: List[Dict],
        min_score: float = MIN_MATCH_SCORE
    ) -> Dict[str, RecurringTransaction]:
        """
        Match multiple transactions to subscriptions in batch.

        Args:
            transactions: List of dicts with keys: id, description, merchant, amount
            min_score: Minimum match score required

        Returns:
            Dict mapping transaction_id to matched RecurringTransaction
        """
        if not ENABLE_AUTO_SUBSCRIPTION_MATCHING:
            return {}

        results = {}
        matched_count = 0

        for txn in transactions:
            txn_id = txn.get('id')
            description = txn.get('description')
            merchant = txn.get('merchant')
            amount = txn.get('amount')
            account_id = txn.get('account_id')

            if amount is None:
                continue

            # Convert to Decimal if needed
            if not isinstance(amount, Decimal):
                amount = Decimal(str(amount))

            match = self.match_transaction(
                description=description,
                merchant=merchant,
                amount=amount,
                account_id=account_id,
                min_score=min_score
            )

            if match:
                results[txn_id] = match
                matched_count += 1

        logger.info(
            f"[SUBSCRIPTION_MATCHER] Batch matched {matched_count}/{len(transactions)} "
            f"transactions to subscriptions"
        )

        return results
