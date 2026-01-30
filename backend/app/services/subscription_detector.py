"""
Subscription pattern detection service for discovering recurring payment patterns.

This service analyzes imported transactions to detect subscription patterns that
haven't been linked to existing subscriptions. Suggestions are stored in the
database for user review.

Usage:
    detector = SubscriptionDetector(db, user_id)
    suggestions = detector.detect_patterns(new_transaction_ids)
    # suggestions are auto-saved to database
"""
import os
import json
import logging
from typing import Optional, List, Dict, Any
from decimal import Decimal
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from collections import defaultdict

from sqlalchemy.orm import Session
from sqlalchemy import and_, func

from app.models import Transaction, RecurringTransaction, SubscriptionSuggestion
from app.db_helpers import get_user_id
from app.services.text_similarity import TextSimilarity
from app.services.merchant_extractor import MerchantExtractor

logger = logging.getLogger(__name__)


# Configuration
ENABLE_SUBSCRIPTION_SUGGESTIONS = os.getenv(
    "ENABLE_SUBSCRIPTION_SUGGESTIONS", "true"
).lower() == "true"

MIN_CONFIDENCE = int(os.getenv("SUBSCRIPTION_SUGGESTION_MIN_CONFIDENCE", "50"))
MAX_SUGGESTIONS = int(os.getenv("SUBSCRIPTION_SUGGESTION_MAX_COUNT", "5"))
MIN_TRANSACTIONS = int(os.getenv("SUBSCRIPTION_SUGGESTION_MIN_TRANSACTIONS", "2"))

# Amount tolerance for grouping (10%)
AMOUNT_TOLERANCE_PERCENT = 0.10


@dataclass
class DetectedPattern:
    """A detected recurring payment pattern."""
    suggested_name: str
    suggested_merchant: Optional[str]
    suggested_amount: Decimal
    currency: str
    detected_frequency: str  # weekly, biweekly, monthly, quarterly, yearly
    confidence: int  # 0-100
    matched_transaction_ids: List[str] = field(default_factory=list)
    match_count: int = 0


class SubscriptionDetector:
    """
    Detects recurring payment patterns from transactions.

    Algorithm:
    1. Get unlinked expense transactions (no recurring_transaction_id)
    2. Group by normalized merchant/description
    3. For each group with 2+ transactions:
       - Check amount consistency (within 10%)
       - Analyze date gaps
       - Detect frequency
       - Calculate confidence
    4. Filter out patterns matching existing subscriptions
    5. Return top MAX_SUGGESTIONS by confidence (min MIN_CONFIDENCE%)
    """

    FREQUENCY_RANGES = {
        'weekly': {'min': 5, 'max': 9, 'target': 7},
        'biweekly': {'min': 12, 'max': 16, 'target': 14},
        'monthly': {'min': 26, 'max': 34, 'target': 30},
        'quarterly': {'min': 80, 'max': 100, 'target': 90},
        'yearly': {'min': 350, 'max': 380, 'target': 365},
    }

    def __init__(self, db: Session, user_id: Optional[str] = None):
        """
        Initialize the SubscriptionDetector.

        Args:
            db: SQLAlchemy database session
            user_id: User ID. If None, uses system user.
        """
        self.db = db
        self.user_id = get_user_id(user_id)
        self.text_similarity = TextSimilarity()
        self.merchant_extractor = MerchantExtractor()
        self._existing_subscriptions: Optional[List[RecurringTransaction]] = None

    def _load_existing_subscriptions(self) -> List[RecurringTransaction]:
        """Load and cache active subscriptions for the user."""
        if self._existing_subscriptions is None:
            self._existing_subscriptions = self.db.query(RecurringTransaction).filter(
                RecurringTransaction.user_id == self.user_id,
                RecurringTransaction.is_active == True
            ).all()
        return self._existing_subscriptions

    @staticmethod
    def _normalize_merchant(text: Optional[str]) -> str:
        """Normalize merchant/description for grouping."""
        if not text:
            return ""
        # Basic normalization: lowercase, strip, remove extra whitespace
        import re
        normalized = text.lower().strip()
        normalized = re.sub(r'\s+', ' ', normalized)
        return normalized

    @staticmethod
    def _get_grouping_key(merchant: Optional[str], description: Optional[str]) -> str:
        """
        Get a grouping key for a transaction.

        Prefers merchant if available, falls back to first significant word
        from description.
        """
        if merchant:
            return SubscriptionDetector._normalize_merchant(merchant)

        if description:
            # Extract first significant word (skip common prefixes)
            normalized = SubscriptionDetector._normalize_merchant(description)
            skip_words = {'payment', 'transfer', 'sepa', 'incasso', 'machtiging', 'btw'}
            words = normalized.split()
            for word in words:
                if len(word) >= 3 and word not in skip_words:
                    return word
            # If no good word found, use first 20 chars
            return normalized[:20] if len(normalized) > 20 else normalized

        return ""

    def _amounts_match(self, amount1: Decimal, amount2: Decimal) -> bool:
        """Check if two amounts match within tolerance."""
        a1 = abs(float(amount1))
        a2 = abs(float(amount2))

        if a1 == 0 or a2 == 0:
            return False

        diff = abs(a1 - a2)
        avg = (a1 + a2) / 2
        return (diff / avg) <= AMOUNT_TOLERANCE_PERCENT

    @staticmethod
    def _calculate_std_dev(values: List[float]) -> float:
        """Calculate standard deviation of a list of values."""
        if len(values) == 0:
            return 0.0
        mean = sum(values) / len(values)
        squared_diffs = [(v - mean) ** 2 for v in values]
        variance = sum(squared_diffs) / len(values)
        return variance ** 0.5

    @staticmethod
    def _filter_outliers(values: List[float], std_dev_multiplier: float = 2.0) -> List[float]:
        """Filter outliers from a list using standard deviation."""
        if len(values) < 3:
            return values

        mean = sum(values) / len(values)
        std_dev = SubscriptionDetector._calculate_std_dev(values)

        if std_dev == 0:
            return values

        return [v for v in values if abs(v - mean) <= std_dev_multiplier * std_dev]

    def _detect_frequency_from_gaps(self, gaps: List[int]) -> tuple[Optional[str], int]:
        """
        Detect frequency from date gaps between transactions.

        Args:
            gaps: List of day gaps between consecutive transactions

        Returns:
            Tuple of (frequency, confidence)
        """
        if not gaps:
            return None, 0

        # Filter outliers
        filtered_gaps = self._filter_outliers([float(g) for g in gaps])
        if not filtered_gaps:
            return None, 0

        # Calculate average gap
        avg_gap = sum(filtered_gaps) / len(filtered_gaps)

        # Find matching frequency
        best_match = {'frequency': None, 'score': 0.0}

        for freq, ranges in self.FREQUENCY_RANGES.items():
            if ranges['min'] <= avg_gap <= ranges['max']:
                # Calculate how close to target
                deviation = abs(avg_gap - ranges['target'])
                max_deviation = (ranges['max'] - ranges['min']) / 2
                score = 1 - (deviation / max_deviation)

                if score > best_match['score']:
                    best_match = {'frequency': freq, 'score': score}

        if not best_match['frequency']:
            return None, 0

        # Calculate confidence based on gap consistency and match score
        std_dev = self._calculate_std_dev(filtered_gaps)
        consistency_score = max(0, 1 - (std_dev / avg_gap)) if avg_gap > 0 else 0

        # Combine scores (50% each)
        confidence = int((best_match['score'] * 0.5 + consistency_score * 0.5) * 100)

        return best_match['frequency'], confidence

    def _matches_existing_subscription(self, pattern: DetectedPattern) -> bool:
        """Check if a pattern matches an existing active subscription."""
        existing = self._load_existing_subscriptions()

        for sub in existing:
            # Check amount match
            if not self._amounts_match(sub.amount, pattern.suggested_amount):
                continue

            # Check text similarity
            score, _ = self.text_similarity.calculate_match_score(
                subscription_name=sub.name,
                subscription_merchant=sub.merchant,
                transaction_description=pattern.suggested_name,
                transaction_merchant=pattern.suggested_merchant
            )

            if score >= 60:  # 60% similarity threshold
                return True

        return False

    def _check_similar_pending_suggestion(
        self,
        pattern: DetectedPattern
    ) -> Optional[SubscriptionSuggestion]:
        """Check if a similar suggestion already exists (pending)."""
        pending = self.db.query(SubscriptionSuggestion).filter(
            SubscriptionSuggestion.user_id == self.user_id,
            SubscriptionSuggestion.status == "pending"
        ).all()

        for suggestion in pending:
            # Check amount match
            if not self._amounts_match(
                Decimal(str(suggestion.suggested_amount)),
                pattern.suggested_amount
            ):
                continue

            # Check text similarity
            score = self.text_similarity.calculate(
                suggestion.suggested_name,
                pattern.suggested_name
            ).score

            if score >= 70:  # 70% similarity threshold
                return suggestion

        return None

    def detect_patterns(
        self,
        transaction_ids: Optional[List[str]] = None,
        lookback_days: int = 365
    ) -> List[DetectedPattern]:
        """
        Analyze transactions to find recurring patterns.

        Args:
            transaction_ids: Optional IDs of specific transactions to analyze.
                            If None, analyzes all unlinked expense transactions.
            lookback_days: Number of days to look back for historical transactions

        Returns:
            List of subscription suggestions, max MAX_SUGGESTIONS, sorted by confidence
        """
        if not ENABLE_SUBSCRIPTION_SUGGESTIONS:
            return []

        logger.info(
            f"[SUBSCRIPTION_DETECTOR] Starting pattern detection for user {self.user_id}"
        )

        # Build query for unlinked expense transactions
        lookback_date = datetime.utcnow() - timedelta(days=lookback_days)

        query = self.db.query(Transaction).filter(
            Transaction.user_id == self.user_id,
            Transaction.recurring_transaction_id.is_(None),
            Transaction.amount < 0,  # Only expenses
            Transaction.booked_at >= lookback_date
        )

        # If specific transaction IDs provided, get their merchants/descriptions
        # to find similar transactions
        if transaction_ids:
            # Get the source transactions
            source_txns = self.db.query(Transaction).filter(
                Transaction.id.in_(transaction_ids),
                Transaction.user_id == self.user_id
            ).all()

            if not source_txns:
                return []

            # Get grouping keys from source transactions
            source_keys = set()
            for txn in source_txns:
                key = self._get_grouping_key(txn.merchant, txn.description)
                if key:
                    source_keys.add(key)

            if not source_keys:
                return []

            # Get all transactions, we'll filter by key later
            all_transactions = query.order_by(Transaction.booked_at.asc()).all()

            # Filter to those matching source keys
            transactions = []
            for txn in all_transactions:
                key = self._get_grouping_key(txn.merchant, txn.description)
                if key in source_keys:
                    transactions.append(txn)
        else:
            transactions = query.order_by(Transaction.booked_at.asc()).all()

        if not transactions:
            logger.info("[SUBSCRIPTION_DETECTOR] No unlinked expense transactions found")
            return []

        logger.info(
            f"[SUBSCRIPTION_DETECTOR] Analyzing {len(transactions)} transactions"
        )

        # Group transactions by merchant/description
        groups: Dict[str, List[Transaction]] = defaultdict(list)
        for txn in transactions:
            key = self._get_grouping_key(txn.merchant, txn.description)
            if key:
                groups[key].append(txn)

        # Analyze each group
        patterns: List[DetectedPattern] = []

        for key, group_txns in groups.items():
            if len(group_txns) < MIN_TRANSACTIONS:
                continue

            # Check amount consistency within the group
            amounts = [abs(float(txn.amount)) for txn in group_txns]
            avg_amount = sum(amounts) / len(amounts)

            # Filter to transactions within amount tolerance
            consistent_txns = [
                txn for txn in group_txns
                if abs(abs(float(txn.amount)) - avg_amount) <= avg_amount * AMOUNT_TOLERANCE_PERCENT
            ]

            if len(consistent_txns) < MIN_TRANSACTIONS:
                continue

            # Sort by date
            consistent_txns.sort(key=lambda t: t.booked_at)

            # Calculate date gaps
            gaps = []
            for i in range(1, len(consistent_txns)):
                prev_date = consistent_txns[i - 1].booked_at
                curr_date = consistent_txns[i].booked_at
                if prev_date and curr_date:
                    days_diff = (curr_date - prev_date).days
                    if days_diff > 0:
                        gaps.append(days_diff)

            if not gaps:
                continue

            # Detect frequency
            frequency, gap_confidence = self._detect_frequency_from_gaps(gaps)

            if not frequency:
                continue

            # Calculate overall confidence
            confidence = gap_confidence

            # Boost for match count (max +30 for 5+ matches)
            match_bonus = min(30, (len(consistent_txns) - 1) * 10)
            confidence = min(100, confidence + match_bonus)

            if confidence < MIN_CONFIDENCE:
                continue

            # Determine suggested name and merchant
            first_txn = consistent_txns[0]
            suggested_name = first_txn.merchant or first_txn.description or key
            suggested_merchant = first_txn.merchant

            # Calculate average amount
            final_amount = Decimal(str(round(avg_amount, 2)))

            pattern = DetectedPattern(
                suggested_name=suggested_name[:255],  # Truncate to field limit
                suggested_merchant=suggested_merchant[:255] if suggested_merchant else None,
                suggested_amount=final_amount,
                currency=first_txn.currency or "EUR",
                detected_frequency=frequency,
                confidence=confidence,
                matched_transaction_ids=[str(txn.id) for txn in consistent_txns],
                match_count=len(consistent_txns)
            )

            # Skip if matches existing subscription
            if self._matches_existing_subscription(pattern):
                logger.debug(
                    f"[SUBSCRIPTION_DETECTOR] Skipping '{key}' - matches existing subscription"
                )
                continue

            patterns.append(pattern)

        # Sort by confidence descending
        patterns.sort(key=lambda p: p.confidence, reverse=True)

        # Limit to MAX_SUGGESTIONS
        patterns = patterns[:MAX_SUGGESTIONS]

        logger.info(
            f"[SUBSCRIPTION_DETECTOR] Detected {len(patterns)} subscription patterns"
        )

        return patterns

    def save_suggestions(
        self,
        patterns: List[DetectedPattern]
    ) -> List[SubscriptionSuggestion]:
        """
        Save detected patterns as suggestions in the database.

        Skips patterns that already have similar pending suggestions.

        Args:
            patterns: List of detected patterns to save

        Returns:
            List of created SubscriptionSuggestion objects
        """
        if not patterns:
            return []

        created = []

        for pattern in patterns:
            # Check for existing similar suggestion
            existing = self._check_similar_pending_suggestion(pattern)
            if existing:
                logger.debug(
                    f"[SUBSCRIPTION_DETECTOR] Skipping '{pattern.suggested_name}' "
                    f"- similar pending suggestion exists"
                )
                continue

            # Create new suggestion
            suggestion = SubscriptionSuggestion(
                user_id=self.user_id,
                suggested_name=pattern.suggested_name,
                suggested_merchant=pattern.suggested_merchant,
                suggested_amount=pattern.suggested_amount,
                currency=pattern.currency,
                detected_frequency=pattern.detected_frequency,
                confidence=pattern.confidence,
                matched_transaction_ids=json.dumps(pattern.matched_transaction_ids),
                status="pending"
            )

            self.db.add(suggestion)
            created.append(suggestion)

            logger.info(
                f"[SUBSCRIPTION_DETECTOR] Created suggestion: '{pattern.suggested_name}' "
                f"({pattern.detected_frequency}, {pattern.confidence}% confidence)"
            )

        if created:
            self.db.commit()
            for suggestion in created:
                self.db.refresh(suggestion)

        return created

    def detect_and_save(
        self,
        transaction_ids: Optional[List[str]] = None
    ) -> int:
        """
        Detect patterns and save suggestions in one call.

        Args:
            transaction_ids: Optional IDs of specific transactions to analyze

        Returns:
            Number of suggestions created
        """
        patterns = self.detect_patterns(transaction_ids)
        suggestions = self.save_suggestions(patterns)
        return len(suggestions)
