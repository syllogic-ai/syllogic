"""Demo environment seeding service.

Creates deterministic, realistic financial demo data for an existing user account.
The service is designed for shared demo environments where data is reset on a schedule.
"""

from __future__ import annotations

import logging
import random
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP
from typing import Dict, Iterable, List, Optional

from sqlalchemy.orm import Session
from sqlalchemy import cast, func, Date

from app.models import (
    Account,
    CategorizationRule,
    Category,
    CsvImport,
    Property,
    RecurringTransaction,
    SubscriptionSuggestion,
    Transaction,
    TransactionLink,
    User,
    Vehicle,
)
from app.services.account_balance_service import AccountBalanceService
from app.services.exchange_rate_service import ExchangeRateService

logger = logging.getLogger(__name__)


DEMO_DEFAULT_START_DATE = date(2025, 1, 1)


@dataclass(frozen=True)
class AccountSpec:
    name: str
    account_type: str
    institution: str
    currency: str
    target_ending_balance: Decimal


@dataclass(frozen=True)
class CategorySpec:
    name: str
    category_type: str
    color: str
    icon: str
    description: str
    categorization_instructions: str
    is_system: bool = False
    hide_from_selection: bool = False


@dataclass(frozen=True)
class TxTemplate:
    description: str
    merchant: str
    category_name: str
    min_amount: float
    max_amount: float
    currency: str


ACCOUNT_SPECS: tuple[AccountSpec, ...] = (
    AccountSpec(
        name="Main Checking",
        account_type="checking",
        institution="Revolut",
        currency="EUR",
        target_ending_balance=Decimal("7425.00"),
    ),
    AccountSpec(
        name="Savings Vault",
        account_type="savings",
        institution="Revolut",
        currency="EUR",
        target_ending_balance=Decimal("18620.00"),
    ),
    AccountSpec(
        name="Travel Card",
        account_type="credit",
        institution="Wise",
        currency="USD",
        target_ending_balance=Decimal("1280.00"),
    ),
)


CATEGORY_SPECS: tuple[CategorySpec, ...] = (
    CategorySpec(
        name="Food & Dining",
        category_type="expense",
        color="#F59E0B",
        icon="RiRestaurantLine",
        description="Restaurants, cafes, takeout, and food delivery",
        categorization_instructions=(
            "Use for restaurant meals, coffee shops, bars, and food delivery platforms such as "
            "Uber Eats or Deliveroo. Exclude grocery-store purchases (use Groceries) and travel "
            "bookings (use Travel)."
        ),
    ),
    CategorySpec(
        name="Groceries",
        category_type="expense",
        color="#10B981",
        icon="RiShoppingCartLine",
        description="Supermarket and household essentials",
        categorization_instructions=(
            "Use for supermarket, grocery, and food-market purchases including Lidl, Albert Heijn, "
            "Tesco, and similar merchants. If the merchant is a restaurant chain or cafe, use Food & Dining instead."
        ),
    ),
    CategorySpec(
        name="Transportation",
        category_type="expense",
        color="#3B82F6",
        icon="RiCarLine",
        description="Transit, rides, fuel, and parking",
        categorization_instructions=(
            "Use for fuel, train, metro, bus, taxi, parking, and ride-sharing. If transaction "
            "is for flights or hotels, use Travel instead."
        ),
    ),
    CategorySpec(
        name="Shopping",
        category_type="expense",
        color="#EC4899",
        icon="RiShoppingBagLine",
        description="General retail and online purchases",
        categorization_instructions=(
            "Use for retail stores and online marketplaces such as Amazon, Zalando, H&M, and Apple Store "
            "hardware purchases. Exclude recurring software memberships (use Entertainment or Bills & Utilities depending on context)."
        ),
    ),
    CategorySpec(
        name="Entertainment",
        category_type="expense",
        color="#8B5CF6",
        icon="RiGamepadLine",
        description="Streaming, events, and leisure",
        categorization_instructions=(
            "Use for movies, concerts, gaming, and streaming subscriptions such as Netflix and Spotify. "
            "Exclude restaurant spending (Food & Dining) and travel lodging (Travel)."
        ),
    ),
    CategorySpec(
        name="Bills & Utilities",
        category_type="expense",
        color="#64748B",
        icon="RiFileTextLine",
        description="Home and telecom bills",
        categorization_instructions=(
            "Use for electricity, water, internet, mobile phone, and utility providers like "
            "Vattenfall, Ziggo, KPN, and Vodafone. If it is rent or mortgage, use Housing."
        ),
    ),
    CategorySpec(
        name="Health & Fitness",
        category_type="expense",
        color="#22C55E",
        icon="RiHeartPulseLine",
        description="Medical and fitness expenses",
        categorization_instructions=(
            "Use for pharmacy, doctor, dentist, hospital, and gym memberships. "
            "Exclude personal grooming (Personal Care)."
        ),
    ),
    CategorySpec(
        name="Housing",
        category_type="expense",
        color="#78716C",
        icon="RiHome4Line",
        description="Rent and home-related spending",
        categorization_instructions=(
            "Use for rent, mortgage, property fees, and home maintenance. "
            "Use Travel for temporary hotels or Airbnb stays."
        ),
    ),
    CategorySpec(
        name="Education",
        category_type="expense",
        color="#6366F1",
        icon="RiBookOpenLine",
        description="Courses, books, and training",
        categorization_instructions=(
            "Use for course subscriptions, books, certifications, and tuition. "
            "If a payment is for entertainment content instead of learning, use Entertainment."
        ),
    ),
    CategorySpec(
        name="Travel",
        category_type="expense",
        color="#14B8A6",
        icon="RiPlaneLine",
        description="Flights, hotels, and trip expenses",
        categorization_instructions=(
            "Use for flights, hotels, vacation bookings, travel insurance, and airport purchases. "
            "Exclude daily commute and rideshare commuting (Transportation)."
        ),
    ),
    CategorySpec(
        name="Personal Care",
        category_type="expense",
        color="#0EA5E9",
        icon="RiUser3Line",
        description="Beauty and personal maintenance",
        categorization_instructions=(
            "Use for barbers, salons, cosmetics, and personal hygiene purchases. "
            "Exclude medical treatment and pharmacy costs (Health & Fitness)."
        ),
    ),
    CategorySpec(
        name="Gifts & Donations",
        category_type="expense",
        color="#EF4444",
        icon="RiGiftLine",
        description="Gifts and charitable giving",
        categorization_instructions=(
            "Use for birthday gifts, holiday presents, and donations to non-profits. "
            "Exclude regular bill payments and transfers between own accounts."
        ),
    ),
    CategorySpec(
        name="Other Expenses",
        category_type="expense",
        color="#52525B",
        icon="RiMore2Line",
        description="Catch-all for unmatched expenses",
        categorization_instructions=(
            "Use only when no specific expense category clearly fits. Prefer a specific category whenever possible."
        ),
    ),
    CategorySpec(
        name="Salary",
        category_type="income",
        color="#22C55E",
        icon="RiBriefcaseLine",
        description="Regular payroll income",
        categorization_instructions=(
            "Use for recurring payroll, wages, and employer salary deposits. "
            "Exclude freelance invoices and refunds."
        ),
    ),
    CategorySpec(
        name="Other Income",
        category_type="income",
        color="#64748B",
        icon="RiAddCircleLine",
        description="General non-salary income",
        categorization_instructions=(
            "Use for interest payouts, bonuses, and one-off non-salary credits that are not refunds."
        ),
    ),
    CategorySpec(
        name="Refunds",
        category_type="income",
        color="#3B82F6",
        icon="RiArrowGoBackLine",
        description="Reimbursements and reversals",
        categorization_instructions=(
            "Use for returned purchases, chargebacks, and reimbursements linked to previous spending."
        ),
    ),
    CategorySpec(
        name="Freelance",
        category_type="income",
        color="#14B8A6",
        icon="RiComputerLine",
        description="Freelance and contract payments",
        categorization_instructions=(
            "Use for consulting, contract, and freelance client payments. "
            "Exclude employer payroll (Salary)."
        ),
    ),
    CategorySpec(
        name="Internal Transfer",
        category_type="transfer",
        color="#64748B",
        icon="RiExchangeLine",
        description="Transfers between own accounts",
        categorization_instructions=(
            "Use for money moved between the user\'s own accounts. "
            "Do not use for salary or external cash deposits."
        ),
        is_system=True,
    ),
    CategorySpec(
        name="External Transfer",
        category_type="transfer",
        color="#78716C",
        icon="RiArrowLeftRightLine",
        description="Transfers to or from external accounts",
        categorization_instructions=(
            "Use for top-ups and transfers involving accounts not tracked in the app."
        ),
        is_system=True,
    ),
    CategorySpec(
        name="Balancing Transfer",
        category_type="transfer",
        color="#52525B",
        icon="RiScalesLine",
        description="System balancing entries",
        categorization_instructions=(
            "Reserved for reconciliation and balancing adjustments. Prefer Internal/External Transfer for user-visible movement."
        ),
        is_system=True,
        hide_from_selection=True,
    ),
)


EUR_DAILY_TEMPLATES: tuple[TxTemplate, ...] = (
    TxTemplate("LIDL SUPERMARKET", "Lidl", "Groceries", 9, 52, "EUR"),
    TxTemplate("ALBERT HEIJN", "Albert Heijn", "Groceries", 10, 58, "EUR"),
    TxTemplate("JUMBO", "Jumbo", "Groceries", 8, 48, "EUR"),
    TxTemplate("STARBUCKS", "Starbucks", "Food & Dining", 3, 11, "EUR"),
    TxTemplate("UBER EATS", "Uber Eats", "Food & Dining", 9, 28, "EUR"),
    TxTemplate("LOCAL RESTAURANT", "Local Bistro", "Food & Dining", 11, 39, "EUR"),
    TxTemplate("NS TRANSPORT", "NS", "Transportation", 3, 16, "EUR"),
    TxTemplate("UBER RIDE", "Uber", "Transportation", 5, 22, "EUR"),
    TxTemplate("SHELL STATION", "Shell", "Transportation", 20, 65, "EUR"),
    TxTemplate("ZARA", "Zara", "Shopping", 12, 72, "EUR"),
    TxTemplate("H&M", "H&M", "Shopping", 10, 60, "EUR"),
    TxTemplate("MEDIA MARKT", "MediaMarkt", "Shopping", 25, 180, "EUR"),
    TxTemplate("NETFLIX", "Netflix", "Entertainment", 10, 16, "EUR"),
    TxTemplate("SPOTIFY", "Spotify", "Entertainment", 7, 13, "EUR"),
    TxTemplate("CINEMA", "Pathé", "Entertainment", 8, 24, "EUR"),
    TxTemplate("PHARMACY", "Boots", "Health & Fitness", 4, 28, "EUR"),
    TxTemplate("GYM MEMBERSHIP", "Basic Fit", "Health & Fitness", 18, 39, "EUR"),
    TxTemplate("BOOKSTORE", "Bookshop", "Education", 7, 34, "EUR"),
    TxTemplate("ONLINE COURSE", "Udemy", "Education", 9, 45, "EUR"),
    TxTemplate("BARBER", "Local Barber", "Personal Care", 9, 28, "EUR"),
    TxTemplate("GIFT SHOP", "Gift Store", "Gifts & Donations", 8, 45, "EUR"),
    TxTemplate("MISC PURCHASE", "Misc Merchant", "Other Expenses", 4, 25, "EUR"),
)


USD_DAILY_TEMPLATES: tuple[TxTemplate, ...] = (
    TxTemplate("AMAZON.COM", "Amazon", "Shopping", 10, 120, "USD"),
    TxTemplate("APPLE STORE", "Apple", "Shopping", 15, 160, "USD"),
    TxTemplate("HOTEL BOOKING", "Booking.com", "Travel", 45, 200, "USD"),
    TxTemplate("AIRLINE TICKET", "KLM", "Travel", 80, 260, "USD"),
    TxTemplate("UBER TRIP", "Uber", "Transportation", 6, 28, "USD"),
    TxTemplate("AIRPORT DINING", "Airport Cafe", "Food & Dining", 8, 32, "USD"),
)


SPIKE_TEMPLATES: tuple[TxTemplate, ...] = (
    TxTemplate("DENTAL CLINIC", "Dental Clinic", "Health & Fitness", 95, 260, "EUR"),
    TxTemplate("WEEKEND TRIP", "Booking.com", "Travel", 130, 380, "EUR"),
    TxTemplate("ELECTRONICS", "Apple", "Shopping", 120, 480, "EUR"),
    TxTemplate("PROFESSIONAL COURSE", "Coursera", "Education", 60, 240, "EUR"),
)


class DemoSeedService:
    """Creates and refreshes a deterministic demo dataset for a specific user."""

    def __init__(self, db: Session, random_seed: int = 42):
        self.db = db
        self.random_seed = random_seed
        self.rng = random.Random(random_seed)
        self._external_counter = 0

    def resolve_user(self, user_id: Optional[str] = None, email: Optional[str] = None) -> User:
        """Resolve demo user by user_id or email. Raises ValueError if missing."""
        query = self.db.query(User)

        user: Optional[User] = None
        if user_id:
            user = query.filter(User.id == user_id).first()
        elif email:
            normalized = email.strip().lower()
            user = query.filter(func.lower(User.email) == normalized).first()
        else:
            raise ValueError("Either user_id or email must be provided.")

        if not user:
            identifier = f"user_id='{user_id}'" if user_id else f"email='{email}'"
            raise ValueError(
                f"Demo user not found for {identifier}. "
                "Create the account via normal signup first, then run the demo seed."
            )

        return user

    def seed_for_user(
        self,
        user: User,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        reset: bool = True,
    ) -> Dict[str, object]:
        """Seed or reseed demo data for a user and return a detailed summary."""
        seed_start = start_date or DEMO_DEFAULT_START_DATE
        seed_end = end_date or date.today()

        if seed_end < seed_start:
            raise ValueError(f"Invalid date range: {seed_start} to {seed_end}")

        if reset:
            deleted = self._clear_user_financial_data(user.id)
        else:
            deleted = {}

        self._prepare_user_for_demo(user)
        accounts = self._create_accounts(user.id)
        categories = self._create_categories(user.id)

        transactions = self._build_transactions(
            user_id=user.id,
            accounts=accounts,
            categories=categories,
            start_date=seed_start,
            end_date=seed_end,
        )

        self.db.add_all(transactions)

        account_sums: Dict[str, Decimal] = {str(account.id): Decimal("0") for account in accounts}
        for tx in transactions:
            account_sums[str(tx.account_id)] += tx.amount or Decimal("0")

        target_balances = {spec.name: spec.target_ending_balance for spec in ACCOUNT_SPECS}
        for account in accounts:
            sum_value = account_sums[str(account.id)]
            target = target_balances[account.name]
            starting_balance = _quantize_currency(target - sum_value)
            account.starting_balance = starting_balance
            account.balance_available = target
            account.functional_balance = target if account.currency == "EUR" else None

        self.db.commit()

        sync_result = self._sync_exchange_rates(seed_start, seed_end)
        functional_result = self._update_functional_amounts(user.id)

        balance_service = AccountBalanceService(self.db)
        account_ids = [account.id for account in accounts]
        balances_result = balance_service.calculate_account_balances(user.id, account_ids=account_ids)
        timeseries_result = balance_service.calculate_account_timeseries(user.id, account_ids=account_ids)

        currency_set = sorted({account.currency for account in accounts if account.currency})
        summary = {
            "user_id": user.id,
            "user_email": user.email,
            "reset": reset,
            "deleted_records": deleted,
            "seed_random_seed": self.random_seed,
            "accounts_created": len(accounts),
            "categories_created": len(categories),
            "transactions_created": len(transactions),
            "currencies": currency_set,
            "date_range": {
                "start": seed_start.isoformat(),
                "end": seed_end.isoformat(),
            },
            "exchange_rates_synced": sync_result,
            "functional_amounts": functional_result,
            "balances_calculated": balances_result,
            "timeseries_calculated": timeseries_result,
        }

        logger.info(
            "[DEMO_SEED] Completed demo seed for user=%s with %s transactions (%s -> %s)",
            user.id,
            len(transactions),
            seed_start,
            seed_end,
        )
        return summary

    def append_previous_day_transactions(
        self,
        user: User,
        target_date: Optional[date] = None,
    ) -> Dict[str, object]:
        """Append demo transactions for previous day (or an explicit target date).

        This method is idempotent per day:
        - It skips when the target date already has any transactions for the user.
        - For created rows it uses deterministic external IDs with prefix
          `demo-day-YYYYMMDD-...`.
        """
        day = target_date or (date.today() - timedelta(days=1))
        if day < DEMO_DEFAULT_START_DATE:
            return {
                "skipped": True,
                "reason": "DATE_BEFORE_DEMO_RANGE",
                "target_date": day.isoformat(),
            }

        self._prepare_user_for_demo(user)

        existing_for_day = self.db.query(func.count(Transaction.id)).filter(
            Transaction.user_id == user.id,
            cast(Transaction.booked_at, Date) == day,
        ).scalar() or 0

        if existing_for_day > 0:
            return {
                "skipped": True,
                "reason": "DAY_ALREADY_POPULATED",
                "target_date": day.isoformat(),
                "existing_records": int(existing_for_day),
            }

        accounts = self.db.query(Account).filter(
            Account.user_id == user.id,
            Account.is_active == True,
        ).all()
        account_by_name = {account.name: account for account in accounts}
        required_accounts = ["Main Checking", "Savings Vault", "Travel Card"]
        missing_accounts = [name for name in required_accounts if name not in account_by_name]
        if missing_accounts:
            raise ValueError(
                f"Demo accounts missing for user {user.id}: {', '.join(missing_accounts)}. "
                "Run full demo seed/reset first."
            )

        categories = self.db.query(Category).filter(Category.user_id == user.id).all()
        category_by_name = {category.name: category for category in categories}
        required_categories = [spec.name for spec in CATEGORY_SPECS]
        missing_categories = [name for name in required_categories if name not in category_by_name]
        if missing_categories:
            raise ValueError(
                f"Demo categories missing for user {user.id}: {', '.join(missing_categories[:5])}..."
            )

        daily_transactions = self._build_transactions_for_day(
            user_id=user.id,
            account_by_name=account_by_name,
            category_by_name=category_by_name,
            day=day,
        )

        # Enforce month-to-date financial constraints after appending this day.
        month_start = date(day.year, day.month, 1)
        existing_month_transactions = self.db.query(Transaction).filter(
            Transaction.user_id == user.id,
            cast(Transaction.booked_at, Date) >= month_start,
            cast(Transaction.booked_at, Date) <= day,
        ).all()

        combined_month_transactions = list(existing_month_transactions) + list(daily_transactions)
        self._enforce_monthly_financial_constraints(
            transactions=combined_month_transactions,
            user_id=user.id,
            main_account=account_by_name["Main Checking"],
            categories=categories,
            category_by_name=category_by_name,
            start_date=month_start,
            end_date=day,
            adjustment_posted_at=day,
        )

        additional_adjustments = combined_month_transactions[len(existing_month_transactions) + len(daily_transactions):]
        if additional_adjustments:
            daily_transactions.extend(additional_adjustments)

        self._assign_daily_external_ids(user.id, day, daily_transactions)

        self.db.add_all(daily_transactions)
        self.db.commit()

        sync_result = self._sync_exchange_rates(day, day)
        functional_result = self._update_functional_amounts(user.id)

        balance_service = AccountBalanceService(self.db)
        touched_account_ids = sorted({transaction.account_id for transaction in daily_transactions})
        balances_result = balance_service.calculate_account_balances(user.id, account_ids=touched_account_ids)
        timeseries_result = balance_service.calculate_account_timeseries(user.id, account_ids=touched_account_ids)

        summary = {
            "skipped": False,
            "target_date": day.isoformat(),
            "transactions_created": len(daily_transactions),
            "exchange_rates_synced": sync_result,
            "functional_amounts": functional_result,
            "balances_calculated": balances_result,
            "timeseries_calculated": timeseries_result,
        }
        logger.info(
            "[DEMO_DAILY] Added %s transactions for user=%s date=%s",
            len(daily_transactions),
            user.id,
            day,
        )
        return summary

    def ensure_demo_coverage(
        self,
        user: User,
        start_date: date = DEMO_DEFAULT_START_DATE,
        end_date: Optional[date] = None,
        max_missing_days_before_reseed: int = 45,
    ) -> Dict[str, object]:
        """Ensure continuous demo coverage for [start_date, end_date].

        Behavior:
        - If canonical demo foundation is missing, perform a full reset seed.
        - If no transactions exist, perform a full reset seed.
        - If gaps exist and are small, fill missing days incrementally.
        - If gaps are large, perform a full reset seed for consistency.
        """
        coverage_end = end_date or date.today()
        if coverage_end < start_date:
            return {
                "action": "skipped_invalid_range",
                "start_date": start_date.isoformat(),
                "end_date": coverage_end.isoformat(),
            }

        self._prepare_user_for_demo(user)

        accounts = self.db.query(Account).filter(
            Account.user_id == user.id,
            Account.is_active == True,
        ).all()
        categories = self.db.query(Category).filter(Category.user_id == user.id).all()

        account_names = {account.name for account in accounts}
        required_accounts = {"Main Checking", "Savings Vault", "Travel Card"}
        missing_accounts = sorted(required_accounts - account_names)

        category_names = {category.name for category in categories}
        required_categories = {spec.name for spec in CATEGORY_SPECS}
        missing_categories = sorted(required_categories - category_names)

        if missing_accounts or missing_categories:
            seed_summary = self.seed_for_user(
                user=user,
                start_date=start_date,
                end_date=coverage_end,
                reset=True,
            )
            return {
                "action": "bootstrap_reset",
                "reason": "MISSING_FOUNDATION",
                "missing_accounts": missing_accounts,
                "missing_categories_count": len(missing_categories),
                "start_date": start_date.isoformat(),
                "end_date": coverage_end.isoformat(),
                "seed_summary": seed_summary,
            }

        existing_dates = {
            row[0]
            for row in self.db.query(cast(Transaction.booked_at, Date))
            .filter(
                Transaction.user_id == user.id,
                cast(Transaction.booked_at, Date) >= start_date,
                cast(Transaction.booked_at, Date) <= coverage_end,
            )
            .distinct()
            .all()
            if row[0] is not None
        }

        if not existing_dates:
            seed_summary = self.seed_for_user(
                user=user,
                start_date=start_date,
                end_date=coverage_end,
                reset=True,
            )
            return {
                "action": "bootstrap_reset",
                "reason": "NO_TRANSACTIONS",
                "start_date": start_date.isoformat(),
                "end_date": coverage_end.isoformat(),
                "seed_summary": seed_summary,
            }

        missing_days = [
            day for day in _iter_dates(start_date, coverage_end)
            if day not in existing_dates
        ]

        if not missing_days:
            return {
                "action": "none",
                "missing_days": 0,
                "start_date": start_date.isoformat(),
                "end_date": coverage_end.isoformat(),
            }

        if len(missing_days) > max_missing_days_before_reseed:
            seed_summary = self.seed_for_user(
                user=user,
                start_date=start_date,
                end_date=coverage_end,
                reset=True,
            )
            return {
                "action": "bootstrap_reset",
                "reason": "TOO_MANY_GAPS",
                "missing_days": len(missing_days),
                "start_date": start_date.isoformat(),
                "end_date": coverage_end.isoformat(),
                "seed_summary": seed_summary,
            }

        filled_days = 0
        transactions_created = 0
        for day in missing_days:
            day_summary = self.append_previous_day_transactions(user=user, target_date=day)
            if day_summary.get("skipped"):
                continue
            filled_days += 1
            transactions_created += int(day_summary.get("transactions_created", 0))

        return {
            "action": "filled_missing_days",
            "filled_days": filled_days,
            "transactions_created": transactions_created,
            "missing_days": len(missing_days),
            "first_missing_day": missing_days[0].isoformat(),
            "last_missing_day": missing_days[-1].isoformat(),
            "start_date": start_date.isoformat(),
            "end_date": coverage_end.isoformat(),
        }

    def _prepare_user_for_demo(self, user: User) -> None:
        user.functional_currency = "EUR"
        user.onboarding_status = "completed"
        if not user.onboarding_completed_at:
            user.onboarding_completed_at = datetime.utcnow()
        user.updated_at = datetime.utcnow()
        self.db.commit()

    def _clear_user_financial_data(self, user_id: str) -> Dict[str, int]:
        """Delete user financial data only, preserving auth/session records."""
        deleted: Dict[str, int] = {}

        deleted["transaction_links"] = self.db.query(TransactionLink).filter(
            TransactionLink.user_id == user_id
        ).delete(synchronize_session=False)

        deleted["subscription_suggestions"] = self.db.query(SubscriptionSuggestion).filter(
            SubscriptionSuggestion.user_id == user_id
        ).delete(synchronize_session=False)

        deleted["csv_imports"] = self.db.query(CsvImport).filter(
            CsvImport.user_id == user_id
        ).delete(synchronize_session=False)

        deleted["transactions"] = self.db.query(Transaction).filter(
            Transaction.user_id == user_id
        ).delete(synchronize_session=False)

        deleted["recurring_transactions"] = self.db.query(RecurringTransaction).filter(
            RecurringTransaction.user_id == user_id
        ).delete(synchronize_session=False)

        deleted["categorization_rules"] = self.db.query(CategorizationRule).filter(
            CategorizationRule.user_id == user_id
        ).delete(synchronize_session=False)

        deleted["accounts"] = self.db.query(Account).filter(
            Account.user_id == user_id
        ).delete(synchronize_session=False)

        deleted["categories"] = self.db.query(Category).filter(
            Category.user_id == user_id
        ).delete(synchronize_session=False)

        deleted["properties"] = self.db.query(Property).filter(
            Property.user_id == user_id
        ).delete(synchronize_session=False)

        deleted["vehicles"] = self.db.query(Vehicle).filter(
            Vehicle.user_id == user_id
        ).delete(synchronize_session=False)

        self.db.commit()
        return deleted

    def _create_accounts(self, user_id: str) -> List[Account]:
        accounts: List[Account] = []
        now = datetime.utcnow()

        for spec in ACCOUNT_SPECS:
            account = Account(
                user_id=user_id,
                name=spec.name,
                account_type=spec.account_type,
                institution=spec.institution,
                currency=spec.currency,
                provider="manual",
                is_active=True,
                starting_balance=Decimal("0"),
                functional_balance=Decimal("0") if spec.currency == "EUR" else None,
                created_at=now,
                updated_at=now,
            )
            self.db.add(account)
            accounts.append(account)

        self.db.commit()
        for account in accounts:
            self.db.refresh(account)

        return accounts

    def _create_categories(self, user_id: str) -> List[Category]:
        categories: List[Category] = []
        now = datetime.utcnow()

        for spec in CATEGORY_SPECS:
            category = Category(
                user_id=user_id,
                name=spec.name,
                category_type=spec.category_type,
                color=spec.color,
                icon=spec.icon,
                description=spec.description,
                categorization_instructions=spec.categorization_instructions,
                is_system=spec.is_system,
                hide_from_selection=spec.hide_from_selection,
                created_at=now,
            )
            self.db.add(category)
            categories.append(category)

        self.db.commit()
        for category in categories:
            self.db.refresh(category)

        return categories

    def _build_transactions(
        self,
        user_id: str,
        accounts: List[Account],
        categories: List[Category],
        start_date: date,
        end_date: date,
    ) -> List[Transaction]:
        account_by_name = {account.name: account for account in accounts}
        category_by_name = {category.name: category for category in categories}

        main_account = account_by_name["Main Checking"]
        savings_account = account_by_name["Savings Vault"]
        travel_account = account_by_name["Travel Card"]

        transactions: List[Transaction] = []

        for current_date in _iter_dates(start_date, end_date):
            is_weekend = current_date.weekday() >= 5
            tx_per_day = self.rng.randint(4, 6) if is_weekend else self.rng.randint(3, 5)

            for _ in range(tx_per_day):
                template = self._choose_daily_template(current_date)
                account = travel_account if template.currency == "USD" else main_account
                amount = _decimal_from_range(self.rng, template.min_amount, template.max_amount) * Decimal("-1")
                transactions.append(
                    self._build_transaction(
                        user_id=user_id,
                        account=account,
                        amount=amount,
                        booked_date=current_date,
                        description=template.description,
                        merchant=template.merchant,
                        category=category_by_name[template.category_name],
                    )
                )

            # periodic spikes for realism
            days_since_start = (current_date - start_date).days
            if days_since_start % 10 == 0 and self.rng.random() < 0.68:
                spike = self.rng.choice(SPIKE_TEMPLATES)
                spike_account = travel_account if spike.currency == "USD" else main_account
                spike_amount = _decimal_from_range(self.rng, spike.min_amount, spike.max_amount) * Decimal("-1")
                transactions.append(
                    self._build_transaction(
                        user_id=user_id,
                        account=spike_account,
                        amount=spike_amount,
                        booked_date=current_date,
                        description=spike.description,
                        merchant=spike.merchant,
                        category=category_by_name[spike.category_name],
                    )
                )

        # recurring monthly transactions
        for month_anchor in _iter_month_anchors(start_date, end_date):
            month = month_anchor.month
            year = month_anchor.year

            self._append_monthly_if_in_range(
                transactions=transactions,
                user_id=user_id,
                account=main_account,
                category=category_by_name["Salary"],
                amount=_decimal_from_range(self.rng, 5600, 6400),
                year=year,
                month=month,
                day=25,
                description="SALARY PAYMENT",
                merchant="Employer BV",
                start_date=start_date,
                end_date=end_date,
            )

            self._append_monthly_if_in_range(
                transactions=transactions,
                user_id=user_id,
                account=main_account,
                category=category_by_name["Housing"],
                amount=_decimal_from_range(self.rng, 1850, 2250) * Decimal("-1"),
                year=year,
                month=month,
                day=1,
                description="RENT PAYMENT",
                merchant="City Apartments",
                start_date=start_date,
                end_date=end_date,
            )

            self._append_monthly_if_in_range(
                transactions=transactions,
                user_id=user_id,
                account=main_account,
                category=category_by_name["Bills & Utilities"],
                amount=_decimal_from_range(self.rng, 90, 220) * Decimal("-1"),
                year=year,
                month=month,
                day=6,
                description="ENERGY BILL",
                merchant="Vattenfall",
                start_date=start_date,
                end_date=end_date,
            )

            self._append_monthly_if_in_range(
                transactions=transactions,
                user_id=user_id,
                account=main_account,
                category=category_by_name["Bills & Utilities"],
                amount=_decimal_from_range(self.rng, 55, 95) * Decimal("-1"),
                year=year,
                month=month,
                day=12,
                description="INTERNET BILL",
                merchant="Ziggo",
                start_date=start_date,
                end_date=end_date,
            )

            self._append_monthly_if_in_range(
                transactions=transactions,
                user_id=user_id,
                account=main_account,
                category=category_by_name["Entertainment"],
                amount=_decimal_from_range(self.rng, 10, 17) * Decimal("-1"),
                year=year,
                month=month,
                day=8,
                description="NETFLIX SUBSCRIPTION",
                merchant="Netflix",
                start_date=start_date,
                end_date=end_date,
            )

            self._append_monthly_if_in_range(
                transactions=transactions,
                user_id=user_id,
                account=main_account,
                category=category_by_name["Entertainment"],
                amount=_decimal_from_range(self.rng, 8, 14) * Decimal("-1"),
                year=year,
                month=month,
                day=18,
                description="SPOTIFY SUBSCRIPTION",
                merchant="Spotify",
                start_date=start_date,
                end_date=end_date,
            )

            # internal transfer pair between own EUR accounts
            transfer_amount = _decimal_from_range(self.rng, 1200, 2200)
            self._append_monthly_if_in_range(
                transactions=transactions,
                user_id=user_id,
                account=main_account,
                category=category_by_name["Internal Transfer"],
                amount=transfer_amount * Decimal("-1"),
                year=year,
                month=month,
                day=3,
                description="TRANSFER TO SAVINGS",
                merchant="Internal Transfer",
                start_date=start_date,
                end_date=end_date,
            )
            self._append_monthly_if_in_range(
                transactions=transactions,
                user_id=user_id,
                account=savings_account,
                category=category_by_name["Internal Transfer"],
                amount=transfer_amount,
                year=year,
                month=month,
                day=3,
                description="TRANSFER FROM CHECKING",
                merchant="Internal Transfer",
                start_date=start_date,
                end_date=end_date,
            )

            # travel card top-up from external source (USD)
            self._append_monthly_if_in_range(
                transactions=transactions,
                user_id=user_id,
                account=travel_account,
                category=category_by_name["External Transfer"],
                amount=_decimal_from_range(self.rng, 180, 540),
                year=year,
                month=month,
                day=15,
                description="TRAVEL CARD TOPUP",
                merchant="Wise Transfer",
                start_date=start_date,
                end_date=end_date,
            )

            # savings interest and occasional freelance payment
            self._append_monthly_if_in_range(
                transactions=transactions,
                user_id=user_id,
                account=savings_account,
                category=category_by_name["Other Income"],
                amount=_decimal_from_range(self.rng, 6, 24),
                year=year,
                month=month,
                day=28,
                description="SAVINGS INTEREST",
                merchant="Revolut",
                start_date=start_date,
                end_date=end_date,
            )

            if self.rng.random() < 0.35:
                self._append_monthly_if_in_range(
                    transactions=transactions,
                    user_id=user_id,
                    account=main_account,
                    category=category_by_name["Freelance"],
                    amount=_decimal_from_range(self.rng, 700, 2200),
                    year=year,
                    month=month,
                    day=self.rng.randint(9, 24),
                    description="FREELANCE PROJECT PAYMENT",
                    merchant="Client Studio",
                    start_date=start_date,
                    end_date=end_date,
                )

            if self.rng.random() < 0.28:
                self._append_monthly_if_in_range(
                    transactions=transactions,
                    user_id=user_id,
                    account=main_account,
                    category=category_by_name["Refunds"],
                    amount=_decimal_from_range(self.rng, 20, 140),
                    year=year,
                    month=month,
                    day=self.rng.randint(5, 27),
                    description="CARD REFUND",
                    merchant="Refund Processor",
                    start_date=start_date,
                    end_date=end_date,
                )

        self._inject_categorization_edge_cases(transactions, categories)
        self._enforce_monthly_financial_constraints(
            transactions=transactions,
            user_id=user_id,
            main_account=main_account,
            categories=categories,
            category_by_name=category_by_name,
            start_date=start_date,
            end_date=end_date,
        )

        # Sort by date to keep deterministic ordering in UI and analytics.
        transactions.sort(key=lambda t: t.booked_at)

        return transactions

    def _build_transactions_for_day(
        self,
        user_id: str,
        account_by_name: Dict[str, Account],
        category_by_name: Dict[str, Category],
        day: date,
    ) -> List[Transaction]:
        """Generate one day of demo transactions following the canonical pattern."""
        main_account = account_by_name["Main Checking"]
        savings_account = account_by_name["Savings Vault"]
        travel_account = account_by_name["Travel Card"]

        transactions: List[Transaction] = []

        is_weekend = day.weekday() >= 5
        tx_per_day = self.rng.randint(4, 6) if is_weekend else self.rng.randint(3, 5)

        for _ in range(tx_per_day):
            template = self._choose_daily_template(day)
            account = travel_account if template.currency == "USD" else main_account
            amount = _decimal_from_range(self.rng, template.min_amount, template.max_amount) * Decimal("-1")
            transactions.append(
                self._build_transaction(
                    user_id=user_id,
                    account=account,
                    amount=amount,
                    booked_date=day,
                    description=template.description,
                    merchant=template.merchant,
                    category=category_by_name[template.category_name],
                )
            )

        days_since_start = (day - DEMO_DEFAULT_START_DATE).days
        if days_since_start >= 0 and days_since_start % 10 == 0 and self.rng.random() < 0.68:
            spike = self.rng.choice(SPIKE_TEMPLATES)
            spike_account = travel_account if spike.currency == "USD" else main_account
            spike_amount = _decimal_from_range(self.rng, spike.min_amount, spike.max_amount) * Decimal("-1")
            transactions.append(
                self._build_transaction(
                    user_id=user_id,
                    account=spike_account,
                    amount=spike_amount,
                    booked_date=day,
                    description=spike.description,
                    merchant=spike.merchant,
                    category=category_by_name[spike.category_name],
                )
            )

        if day.day == 25:
            transactions.append(
                self._build_transaction(
                    user_id=user_id,
                    account=main_account,
                    amount=_decimal_from_range(self.rng, 5600, 6400),
                    booked_date=day,
                    description="SALARY PAYMENT",
                    merchant="Employer BV",
                    category=category_by_name["Salary"],
                )
            )

        if day.day == 1:
            transactions.append(
                self._build_transaction(
                    user_id=user_id,
                    account=main_account,
                    amount=_decimal_from_range(self.rng, 1850, 2250) * Decimal("-1"),
                    booked_date=day,
                    description="RENT PAYMENT",
                    merchant="City Apartments",
                    category=category_by_name["Housing"],
                )
            )

        if day.day == 6:
            transactions.append(
                self._build_transaction(
                    user_id=user_id,
                    account=main_account,
                    amount=_decimal_from_range(self.rng, 90, 220) * Decimal("-1"),
                    booked_date=day,
                    description="ENERGY BILL",
                    merchant="Vattenfall",
                    category=category_by_name["Bills & Utilities"],
                )
            )

        if day.day == 12:
            transactions.append(
                self._build_transaction(
                    user_id=user_id,
                    account=main_account,
                    amount=_decimal_from_range(self.rng, 55, 95) * Decimal("-1"),
                    booked_date=day,
                    description="INTERNET BILL",
                    merchant="Ziggo",
                    category=category_by_name["Bills & Utilities"],
                )
            )

        if day.day == 8:
            transactions.append(
                self._build_transaction(
                    user_id=user_id,
                    account=main_account,
                    amount=_decimal_from_range(self.rng, 10, 17) * Decimal("-1"),
                    booked_date=day,
                    description="NETFLIX SUBSCRIPTION",
                    merchant="Netflix",
                    category=category_by_name["Entertainment"],
                )
            )

        if day.day == 18:
            transactions.append(
                self._build_transaction(
                    user_id=user_id,
                    account=main_account,
                    amount=_decimal_from_range(self.rng, 8, 14) * Decimal("-1"),
                    booked_date=day,
                    description="SPOTIFY SUBSCRIPTION",
                    merchant="Spotify",
                    category=category_by_name["Entertainment"],
                )
            )

        if day.day == 3:
            transfer_amount = _decimal_from_range(self.rng, 1200, 2200)
            transactions.append(
                self._build_transaction(
                    user_id=user_id,
                    account=main_account,
                    amount=transfer_amount * Decimal("-1"),
                    booked_date=day,
                    description="TRANSFER TO SAVINGS",
                    merchant="Internal Transfer",
                    category=category_by_name["Internal Transfer"],
                )
            )
            transactions.append(
                self._build_transaction(
                    user_id=user_id,
                    account=savings_account,
                    amount=transfer_amount,
                    booked_date=day,
                    description="TRANSFER FROM CHECKING",
                    merchant="Internal Transfer",
                    category=category_by_name["Internal Transfer"],
                )
            )

        if day.day == 15:
            transactions.append(
                self._build_transaction(
                    user_id=user_id,
                    account=travel_account,
                    amount=_decimal_from_range(self.rng, 180, 540),
                    booked_date=day,
                    description="TRAVEL CARD TOPUP",
                    merchant="Wise Transfer",
                    category=category_by_name["External Transfer"],
                )
            )

        if day.day == 28:
            transactions.append(
                self._build_transaction(
                    user_id=user_id,
                    account=savings_account,
                    amount=_decimal_from_range(self.rng, 6, 24),
                    booked_date=day,
                    description="SAVINGS INTEREST",
                    merchant="Revolut",
                    category=category_by_name["Other Income"],
                )
            )

        if 9 <= day.day <= 24 and self.rng.random() < 0.35:
            transactions.append(
                self._build_transaction(
                    user_id=user_id,
                    account=main_account,
                    amount=_decimal_from_range(self.rng, 700, 2200),
                    booked_date=day,
                    description="FREELANCE PROJECT PAYMENT",
                    merchant="Client Studio",
                    category=category_by_name["Freelance"],
                )
            )

        if 5 <= day.day <= 27 and self.rng.random() < 0.28:
            transactions.append(
                self._build_transaction(
                    user_id=user_id,
                    account=main_account,
                    amount=_decimal_from_range(self.rng, 20, 140),
                    booked_date=day,
                    description="CARD REFUND",
                    merchant="Refund Processor",
                    category=category_by_name["Refunds"],
                )
            )

        self._inject_categorization_edge_cases(transactions, list(category_by_name.values()))
        transactions.sort(key=lambda tx: tx.booked_at)
        return transactions

    def _choose_daily_template(self, current_date: date) -> TxTemplate:
        """Weighted transaction template selection with periodic USD usage."""
        usd_bias = 0.12 if current_date.weekday() >= 4 else 0.07
        if self.rng.random() < usd_bias:
            return self.rng.choice(USD_DAILY_TEMPLATES)
        return self.rng.choice(EUR_DAILY_TEMPLATES)

    def _append_monthly_if_in_range(
        self,
        transactions: List[Transaction],
        user_id: str,
        account: Account,
        category: Category,
        amount: Decimal,
        year: int,
        month: int,
        day: int,
        description: str,
        merchant: str,
        start_date: date,
        end_date: date,
    ) -> None:
        max_day = _days_in_month(year, month)
        safe_day = min(day, max_day)
        booked_date = date(year, month, safe_day)
        if booked_date < start_date or booked_date > end_date:
            return

        transactions.append(
            self._build_transaction(
                user_id=user_id,
                account=account,
                amount=amount,
                booked_date=booked_date,
                description=description,
                merchant=merchant,
                category=category,
            )
        )

    def _build_transaction(
        self,
        user_id: str,
        account: Account,
        amount: Decimal,
        booked_date: date,
        description: str,
        merchant: str,
        category: Optional[Category],
        external_id: Optional[str] = None,
    ) -> Transaction:
        self._external_counter += 1
        booked_at = datetime.combine(
            booked_date,
            datetime.min.time(),
        ).replace(
            hour=self.rng.randint(7, 22),
            minute=self.rng.randint(0, 59),
            second=self.rng.randint(0, 59),
        )

        normalized_amount = _quantize_currency(amount)
        transaction_type = "credit" if normalized_amount >= 0 else "debit"
        category_id = category.id if category else None

        return Transaction(
            user_id=user_id,
            account_id=account.id,
            external_id=external_id or f"demo-{account.currency.lower()}-{self._external_counter:06d}",
            transaction_type=transaction_type,
            amount=normalized_amount,
            currency=account.currency,
            description=description,
            merchant=merchant,
            category_id=category_id,
            category_system_id=category_id,
            booked_at=booked_at,
            pending=False,
            include_in_analytics=True,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )

    def _inject_categorization_edge_cases(self, transactions: List[Transaction], categories: List[Category]) -> None:
        """Introduce a small amount of uncategorized and override-like data."""
        if not transactions:
            return

        categories_by_id = {str(cat.id): cat for cat in categories}
        by_type: Dict[str, List[Category]] = {"expense": [], "income": [], "transfer": []}
        for category in categories:
            by_type.setdefault(category.category_type, []).append(category)

        eligible_indices = [
            idx
            for idx, tx in enumerate(transactions)
            if tx.category_system_id is not None
            and tx.transaction_type in {"credit", "debit"}
            and categories_by_id.get(str(tx.category_system_id), None)
            and categories_by_id[str(tx.category_system_id)].category_type != "transfer"
        ]

        if len(eligible_indices) < 10:
            return

        uncategorized_count = max(1, int(len(eligible_indices) * 0.04))
        uncategorized_indices = set(self.rng.sample(eligible_indices, k=min(uncategorized_count, len(eligible_indices))))

        for idx in uncategorized_indices:
            transactions[idx].category_id = None
            transactions[idx].category_system_id = None

        override_pool = [idx for idx in eligible_indices if idx not in uncategorized_indices]
        override_count = max(1, int(len(eligible_indices) * 0.03))
        override_indices = self.rng.sample(override_pool, k=min(override_count, len(override_pool)))

        for idx in override_indices:
            tx = transactions[idx]
            system_category = categories_by_id.get(str(tx.category_system_id)) if tx.category_system_id else None
            if not system_category:
                continue

            same_type = [
                cat
                for cat in by_type.get(system_category.category_type, [])
                if cat.id != system_category.id and not cat.hide_from_selection
            ]
            if not same_type:
                continue

            override_category = self.rng.choice(same_type)
            tx.category_id = override_category.id
            tx.categorization_instructions = (
                f"For similar transactions, prefer '{override_category.name}' over '{system_category.name}'."
            )

    def _assign_daily_external_ids(
        self,
        user_id: str,
        target_date: date,
        transactions: List[Transaction],
    ) -> None:
        """Assign deterministic day-based external IDs and avoid collisions."""
        prefix = f"demo-day-{target_date:%Y%m%d}"
        existing_ids = {
            row[0]
            for row in self.db.query(Transaction.external_id).filter(
                Transaction.user_id == user_id,
                Transaction.external_id.ilike(f"{prefix}-%"),
            ).all()
            if row[0]
        }
        assigned = set(existing_ids)

        sequence = 1
        for tx in transactions:
            account_suffix = str(tx.account_id).split("-")[0]
            candidate = f"{prefix}-{account_suffix}-{sequence:03d}"
            while candidate in assigned:
                sequence += 1
                candidate = f"{prefix}-{account_suffix}-{sequence:03d}"
            tx.external_id = candidate
            assigned.add(candidate)
            sequence += 1

    def _enforce_monthly_financial_constraints(
        self,
        transactions: List[Transaction],
        user_id: str,
        main_account: Account,
        categories: List[Category],
        category_by_name: Dict[str, Category],
        start_date: date,
        end_date: date,
        adjustment_posted_at: Optional[date] = None,
    ) -> None:
        """Ensure monthly savings rate >= 35% and housing is top expense category."""
        categories_by_id = {str(category.id): category for category in categories}
        min_savings_rate = Decimal("0.35")
        max_expense_ratio = Decimal("1.00") - min_savings_rate

        housing_category = category_by_name["Housing"]
        bonus_category = category_by_name["Other Income"]

        for month_anchor in _iter_month_anchors(start_date, end_date):
            year = month_anchor.year
            month = month_anchor.month
            month_start = date(year, month, 1)
            month_end = date(year, month, _days_in_month(year, month))
            allowed_start = max(start_date, month_start)
            allowed_end = min(end_date, month_end)
            if allowed_start > allowed_end:
                continue

            def _clamp_allowed_day(day_of_month: int) -> int:
                return max(allowed_start.day, min(day_of_month, allowed_end.day))

            monthly = self._calculate_monthly_financials(
                transactions=transactions,
                categories_by_id=categories_by_id,
                year=year,
                month=month,
            )

            if monthly["largest_non_housing_expense"] >= monthly["housing_expense"]:
                housing_top_up = (
                    monthly["largest_non_housing_expense"] - monthly["housing_expense"]
                ) + _decimal_from_range(self.rng, 40, 120)
                if adjustment_posted_at and adjustment_posted_at.year == year and adjustment_posted_at.month == month:
                    housing_day = _clamp_allowed_day(adjustment_posted_at.day)
                else:
                    housing_day = _clamp_allowed_day(min(2, _days_in_month(year, month)))
                transactions.append(
                    self._build_transaction(
                        user_id=user_id,
                        account=main_account,
                        amount=housing_top_up * Decimal("-1"),
                        booked_date=date(year, month, housing_day),
                        description="HOUSING SERVICE CHARGE",
                        merchant="Property Management",
                        category=housing_category,
                    )
                )
                monthly = self._calculate_monthly_financials(
                    transactions=transactions,
                    categories_by_id=categories_by_id,
                    year=year,
                    month=month,
                )

            required_income = Decimal("0")
            if monthly["expense_total"] > 0:
                required_income = _quantize_currency(monthly["expense_total"] / max_expense_ratio)

            if monthly["income_total"] < required_income:
                bonus_amount = (required_income - monthly["income_total"]) + _decimal_from_range(self.rng, 60, 180)
                if adjustment_posted_at and adjustment_posted_at.year == year and adjustment_posted_at.month == month:
                    bonus_day = _clamp_allowed_day(adjustment_posted_at.day)
                else:
                    bonus_day = _clamp_allowed_day(min(26, _days_in_month(year, month)))
                transactions.append(
                    self._build_transaction(
                        user_id=user_id,
                        account=main_account,
                        amount=bonus_amount,
                        booked_date=date(year, month, bonus_day),
                        description="PERFORMANCE BONUS PAYOUT",
                        merchant="Employer BV",
                        category=bonus_category,
                    )
                )

    def _calculate_monthly_financials(
        self,
        transactions: List[Transaction],
        categories_by_id: Dict[str, Category],
        year: int,
        month: int,
    ) -> Dict[str, Decimal]:
        """Return income/expense snapshot for a given month."""
        income_total = Decimal("0")
        expense_total = Decimal("0")
        expense_by_category: Dict[str, Decimal] = {}

        for tx in transactions:
            if tx.booked_at.year != year or tx.booked_at.month != month:
                continue

            effective_category_id = tx.category_id or tx.category_system_id
            category = categories_by_id.get(str(effective_category_id)) if effective_category_id else None
            category_type = category.category_type if category else None
            category_name = category.name if category else None

            if tx.amount is None:
                continue

            if tx.amount > 0:
                if category_type == "transfer":
                    continue
                income_total += tx.amount
                continue

            if tx.amount < 0:
                if category_type == "transfer":
                    continue
                spend_amount = abs(tx.amount)
                expense_total += spend_amount

                if category and category_type == "expense" and category_name:
                    expense_by_category[category_name] = expense_by_category.get(category_name, Decimal("0")) + spend_amount

        housing_expense = expense_by_category.get("Housing", Decimal("0"))
        largest_non_housing_expense = max(
            (amount for name, amount in expense_by_category.items() if name != "Housing"),
            default=Decimal("0"),
        )

        return {
            "income_total": income_total,
            "expense_total": expense_total,
            "housing_expense": housing_expense,
            "largest_non_housing_expense": largest_non_housing_expense,
        }

    def _sync_exchange_rates(self, start_date: date, end_date: date) -> Dict[str, object]:
        try:
            service = ExchangeRateService(self.db)
            result = service.sync_exchange_rates(start_date=start_date, end_date=end_date)
            return result
        except Exception as exc:  # noqa: BLE001 - preserve full error in summary
            logger.warning("[DEMO_SEED] Exchange rate sync failed: %s", exc)
            return {"error": str(exc)}

    def _update_functional_amounts(self, user_id: str) -> Dict[str, int]:
        user = self.db.query(User).filter(User.id == user_id).first()
        functional_currency = user.functional_currency if user and user.functional_currency else "EUR"

        transactions = self.db.query(Transaction).filter(Transaction.user_id == user_id).all()
        if not transactions:
            return {"updated": 0, "skipped": 0, "failed": 0}

        try:
            exchange_service = ExchangeRateService(self.db)
        except Exception as exc:  # noqa: BLE001 - preserve full error in summary
            logger.warning("[DEMO_SEED] Could not initialize ExchangeRateService for functional amounts: %s", exc)
            return {"updated": 0, "skipped": 0, "failed": len(transactions)}

        updated = 0
        skipped = 0
        failed = 0

        for tx in transactions:
            try:
                if tx.currency == functional_currency:
                    tx.functional_amount = tx.amount
                    skipped += 1
                    continue

                rate = exchange_service.get_exchange_rate(
                    base_currency=tx.currency,
                    target_currency=functional_currency,
                    for_date=tx.booked_at.date(),
                )
                if rate is None:
                    tx.functional_amount = None
                    failed += 1
                    continue

                tx.functional_amount = _quantize_currency(tx.amount * rate)
                updated += 1
            except Exception:  # noqa: BLE001
                tx.functional_amount = None
                failed += 1

        self.db.commit()
        return {"updated": updated, "skipped": skipped, "failed": failed}


def _quantize_currency(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _decimal_from_range(rng: random.Random, min_value: float, max_value: float) -> Decimal:
    sampled = rng.uniform(min_value, max_value)
    return _quantize_currency(Decimal(str(sampled)))


def _iter_dates(start_date: date, end_date: date) -> Iterable[date]:
    current = start_date
    while current <= end_date:
        yield current
        current += timedelta(days=1)


def _iter_month_anchors(start_date: date, end_date: date) -> Iterable[date]:
    current = date(start_date.year, start_date.month, 1)
    while current <= end_date:
        yield current
        if current.month == 12:
            current = date(current.year + 1, 1, 1)
        else:
            current = date(current.year, current.month + 1, 1)


def _days_in_month(year: int, month: int) -> int:
    if month == 12:
        next_month = date(year + 1, 1, 1)
    else:
        next_month = date(year, month + 1, 1)
    return (next_month - timedelta(days=1)).day
