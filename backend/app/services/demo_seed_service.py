"""Demo environment seeding service.

Creates deterministic, realistic financial demo data for an existing user account.
The service is designed for shared demo environments where data is reset on a schedule.
"""

from __future__ import annotations

import hashlib
import logging
import random
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP
from typing import Dict, Iterable, List, Optional, Tuple

from sqlalchemy.orm import Session
from sqlalchemy import cast, func, Date

from app.models import (
    Account,
    AccountBalance,
    BrokerConnection,
    BrokerTrade,
    CategorizationRule,
    Category,
    CsvImport,
    Holding,
    HoldingValuation,
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
    minimum_balance_floor: Decimal


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
        minimum_balance_floor=Decimal("1500.00"),
    ),
    AccountSpec(
        name="Savings Vault",
        account_type="savings",
        institution="Revolut",
        currency="EUR",
        target_ending_balance=Decimal("18620.00"),
        minimum_balance_floor=Decimal("9000.00"),
    ),
    AccountSpec(
        name="Travel Card",
        account_type="credit",
        institution="Wise",
        currency="USD",
        target_ending_balance=Decimal("1280.00"),
        minimum_balance_floor=Decimal("600.00"),
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


# ---------------------------------------------------------------------------
# Investments demo data
#
# The demo portfolio is seeded directly into holdings/valuations/account
# balances with a deterministic price path. We deliberately DO NOT use the
# shared `price_snapshots` cache or the IBKR sync service: prices there are
# global (keyed by symbol/date) and would collide with real users holding
# the same tickers. Keeping demo valuations self-contained makes the data
# deterministic and fully isolated. The demo investment accounts are also
# excluded from the nightly investment sync (see tasks/investment_tasks.py).
# ---------------------------------------------------------------------------

DEMO_INVESTMENT_START_DATE = date(2024, 1, 1)


@dataclass(frozen=True)
class HoldingSpec:
    symbol: str
    name: str
    instrument_type: str  # "equity" | "etf" | "cash"
    currency: str
    quantity: Decimal
    base_price: Decimal  # native-currency price at the position's open date
    drift_annual: float  # fractional annual price drift (e.g. 0.12 = +12%/yr)
    volatility: float  # daily deterministic noise amplitude (fraction of price)
    avg_cost: Optional[Decimal]  # native average cost (None for cash)


@dataclass(frozen=True)
class InvestmentAccountSpec:
    name: str
    account_type: str  # "investment_brokerage" | "investment_manual"
    institution: str
    provider: str  # "ibkr_flex" | "manual"
    currency: str  # account base currency
    source: str  # holdings source tag: "ibkr_flex" | "manual"
    has_broker_connection: bool
    holdings: Tuple[HoldingSpec, ...]


INVESTMENT_ACCOUNT_SPECS: Tuple[InvestmentAccountSpec, ...] = (
    InvestmentAccountSpec(
        name="Interactive Brokers",
        account_type="investment_brokerage",
        institution="Interactive Brokers",
        provider="ibkr_flex",
        currency="USD",
        source="ibkr_flex",
        has_broker_connection=True,
        holdings=(
            HoldingSpec("AAPL", "Apple Inc.", "equity", "USD",
                        Decimal("40"), Decimal("185.00"), 0.14, 0.012, Decimal("164.20")),
            HoldingSpec("MSFT", "Microsoft Corp.", "equity", "USD",
                        Decimal("22"), Decimal("372.00"), 0.16, 0.011, Decimal("328.50")),
            HoldingSpec("NVDA", "NVIDIA Corp.", "equity", "USD",
                        Decimal("18"), Decimal("48.00"), 0.55, 0.022, Decimal("21.40")),
            HoldingSpec("VWRA", "Vanguard FTSE All-World UCITS ETF", "etf", "USD",
                        Decimal("60"), Decimal("108.00"), 0.10, 0.008, Decimal("95.30")),
            HoldingSpec("USD", "Cash (USD)", "cash", "USD",
                        Decimal("3150.00"), Decimal("1"), 0.0, 0.0, None),
        ),
    ),
    InvestmentAccountSpec(
        name="Personal Portfolio",
        account_type="investment_manual",
        institution="Self-managed",
        provider="manual",
        currency="EUR",
        source="manual",
        has_broker_connection=False,
        holdings=(
            HoldingSpec("IWDA", "iShares Core MSCI World UCITS ETF", "etf", "EUR",
                        Decimal("85"), Decimal("82.00"), 0.11, 0.008, Decimal("71.90")),
            HoldingSpec("VWCE", "Vanguard FTSE All-World UCITS ETF (Acc)", "etf", "EUR",
                        Decimal("45"), Decimal("112.00"), 0.10, 0.008, Decimal("99.40")),
            HoldingSpec("EUR", "Cash (EUR)", "cash", "EUR",
                        Decimal("1850.00"), Decimal("1"), 0.0, 0.0, None),
        ),
    ),
)


class DemoSeedService:
    """Creates and refreshes a deterministic demo dataset for a specific user."""

    def __init__(self, db: Session, random_seed: int = 42):
        self.db = db
        self.random_seed = random_seed
        self.rng = random.Random(random_seed)
        self._external_counter = 0
        self._usd_eur_cache: Dict[date, Decimal] = {}

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

        category_by_name = {category.name: category for category in categories}
        self._normalize_seeded_account_balances(
            user_id=user.id,
            accounts=accounts,
            transactions=transactions,
            category_by_name=category_by_name,
            start_date=seed_start,
            end_date=seed_end,
        )
        transactions.sort(key=lambda tx: tx.booked_at)

        self.db.add_all(transactions)

        self.db.commit()

        sync_result = self._sync_exchange_rates(seed_start, seed_end)
        functional_result = self._update_functional_amounts(user.id)

        balance_service = AccountBalanceService(self.db)
        account_ids = [account.id for account in accounts]
        balances_result = balance_service.calculate_account_balances(user.id, account_ids=account_ids)
        timeseries_result = balance_service.calculate_account_timeseries(user.id, account_ids=account_ids)

        investments_result = self._seed_investments(
            user=user,
            start_date=seed_start,
            end_date=seed_end,
        )

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
            "investments": investments_result,
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

        self._normalize_daily_account_balances(
            user_id=user.id,
            target_date=day,
            daily_transactions=daily_transactions,
            accounts=accounts,
            category_by_name=category_by_name,
        )
        daily_transactions.sort(key=lambda tx: tx.booked_at)

        self._assign_daily_external_ids(user.id, day, daily_transactions)

        self.db.add_all(daily_transactions)
        self.db.commit()

        sync_result = self._sync_exchange_rates(day, day)
        functional_result = self._update_functional_amounts(user.id)

        balance_service = AccountBalanceService(self.db)
        touched_account_ids = sorted({transaction.account_id for transaction in daily_transactions})
        balances_result = balance_service.calculate_account_balances(user.id, account_ids=touched_account_ids)
        timeseries_result = balance_service.calculate_account_timeseries(user.id, account_ids=touched_account_ids)

        investments_result = self._append_investment_valuations_for_day(user=user, day=day)

        summary = {
            "skipped": False,
            "target_date": day.isoformat(),
            "transactions_created": len(daily_transactions),
            "exchange_rates_synced": sync_result,
            "functional_amounts": functional_result,
            "balances_calculated": balances_result,
            "timeseries_calculated": timeseries_result,
            "investments": investments_result,
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

    # ------------------------------------------------------------------
    # Investments
    # ------------------------------------------------------------------

    def _seed_investments(
        self,
        user: User,
        start_date: date,
        end_date: date,
    ) -> Dict[str, object]:
        """Create the demo investment portfolio (IBKR + standalone) plus a
        deterministic daily valuation history across [start_date, end_date].

        Valuations and account balances are written directly (no PriceSnapshot
        cache, no IBKR/price sync) so the data is deterministic and isolated
        from real users who may hold the same tickers.
        """
        self._clear_investment_data(user.id)

        now = datetime.utcnow()
        accounts: List[Tuple[Account, InvestmentAccountSpec]] = []

        for acct_spec in INVESTMENT_ACCOUNT_SPECS:
            account = Account(
                user_id=user.id,
                name=acct_spec.name,
                account_type=acct_spec.account_type,
                institution=acct_spec.institution,
                currency=acct_spec.currency,
                provider=acct_spec.provider,
                is_active=True,
                starting_balance=Decimal("0"),
                functional_balance=Decimal("0") if acct_spec.currency == "EUR" else None,
                created_at=now,
                updated_at=now,
            )
            self.db.add(account)
            accounts.append((account, acct_spec))

        self.db.commit()
        for account, _ in accounts:
            self.db.refresh(account)

        holdings: List[Tuple[Holding, HoldingSpec, Account]] = []
        for account, acct_spec in accounts:
            if acct_spec.has_broker_connection:
                self.db.add(BrokerConnection(
                    user_id=user.id,
                    account_id=account.id,
                    provider=acct_spec.provider,
                    # Demo accounts are excluded from the real investment sync,
                    # so these credentials are never decrypted. A sentinel keeps
                    # the NOT NULL column populated without SYLLOGIC_SECRET_KEY.
                    credentials_encrypted="demo-disabled",
                    last_sync_status="ok",
                    last_sync_at=now,
                    created_at=now,
                    updated_at=now,
                ))
            for h_spec in acct_spec.holdings:
                holding = Holding(
                    user_id=user.id,
                    account_id=account.id,
                    symbol=h_spec.symbol,
                    name=h_spec.name,
                    currency=h_spec.currency,
                    instrument_type=h_spec.instrument_type,
                    quantity=h_spec.quantity,
                    avg_cost=h_spec.avg_cost,
                    as_of_date=start_date,
                    source=acct_spec.source,
                    created_at=now,
                    updated_at=now,
                )
                self.db.add(holding)
                holdings.append((holding, h_spec, account))

        self.db.commit()
        for holding, _, _ in holdings:
            self.db.refresh(holding)

        trades_created = self._create_broker_trades(holdings, start_date)
        valuation_summary = self._seed_investment_valuations(
            holdings, accounts, start_date, end_date
        )

        logger.info(
            "[DEMO_SEED] Seeded investments for user=%s accounts=%s holdings=%s "
            "trades=%s valuations=%s",
            user.id,
            len(accounts),
            len(holdings),
            trades_created,
            valuation_summary["valuations"],
        )

        return {
            "accounts_created": len(accounts),
            "holdings_created": len(holdings),
            "broker_trades_created": trades_created,
            "valuations_created": valuation_summary["valuations"],
            "account_balances_created": valuation_summary["account_balances"],
            "date_range": {"start": start_date.isoformat(), "end": end_date.isoformat()},
        }

    def _clear_investment_data(self, user_id: str) -> None:
        """Remove existing demo investment accounts (cascades to holdings,
        valuations, broker connections/trades, and account balances)."""
        self.db.query(Account).filter(
            Account.user_id == user_id,
            Account.account_type.in_(("investment_brokerage", "investment_manual")),
        ).delete(synchronize_session=False)
        self.db.commit()

    def _create_broker_trades(
        self,
        holdings: List[Tuple[Holding, HoldingSpec, Account]],
        start_date: date,
    ) -> int:
        """Create a small buy-only trade history for brokerage positions so the
        holding-detail trades/lots views populate. Lots sum to the held qty."""
        created = 0
        lots = (
            (Decimal("0.6"), 0, Decimal("0.94")),
            (Decimal("0.4"), 45, Decimal("1.07")),
        )
        for holding, h_spec, account in holdings:
            if h_spec.instrument_type == "cash" or holding.source != "ibkr_flex":
                continue
            if h_spec.avg_cost is None:
                continue
            lot_n = 0
            for frac, day_offset, price_mult in lots:
                qty = (Decimal(h_spec.quantity) * frac).quantize(Decimal("0.00000001"))
                if qty <= 0:
                    continue
                lot_n += 1
                self.db.add(BrokerTrade(
                    account_id=account.id,
                    symbol=h_spec.symbol,
                    trade_date=start_date + timedelta(days=day_offset),
                    side="buy",
                    quantity=qty,
                    price=(Decimal(h_spec.avg_cost) * price_mult).quantize(Decimal("0.0001")),
                    currency=h_spec.currency,
                    fees=Decimal("1.00"),
                    external_id=f"demo-trade-{h_spec.symbol}-{lot_n}",
                ))
                created += 1
        self.db.commit()
        return created

    def _seed_investment_valuations(
        self,
        holdings: List[Tuple[Holding, HoldingSpec, Account]],
        accounts: List[Tuple[Account, InvestmentAccountSpec]],
        start_date: date,
        end_date: date,
    ) -> Dict[str, int]:
        holdings_by_account: Dict[str, List[Tuple[Holding, HoldingSpec]]] = {}
        for holding, h_spec, account in holdings:
            holdings_by_account.setdefault(str(account.id), []).append((holding, h_spec))

        valuations = 0
        account_balances = 0
        for day in _iter_dates(start_date, end_date):
            rate_usd_eur = self._usd_to_eur_rate(day)
            for account, acct_spec in accounts:
                total_user = Decimal("0")
                total_acct = Decimal("0")
                for holding, h_spec in holdings_by_account.get(str(account.id), []):
                    price = self._demo_holding_price(h_spec, start_date, day)
                    value_native = (Decimal(h_spec.quantity) * price).quantize(Decimal("0.00000001"))
                    value_user = self._convert_currency(value_native, h_spec.currency, "EUR", rate_usd_eur)
                    value_acct = self._convert_currency(value_native, h_spec.currency, acct_spec.currency, rate_usd_eur)
                    self.db.add(HoldingValuation(
                        holding_id=holding.id,
                        date=day,
                        quantity=h_spec.quantity,
                        price=price,
                        value_user_currency=value_user,
                        is_stale=False,
                    ))
                    valuations += 1
                    total_user += value_user
                    total_acct += value_acct
                self.db.add(AccountBalance(
                    account_id=account.id,
                    date=day,
                    balance_in_account_currency=total_acct,
                    balance_in_functional_currency=total_user,
                ))
                account_balances += 1

        # Reflect the most recent valuation on the account headline balance.
        last_rate = self._usd_to_eur_rate(end_date)
        for account, acct_spec in accounts:
            total_acct = Decimal("0")
            for holding, h_spec in holdings_by_account.get(str(account.id), []):
                price = self._demo_holding_price(h_spec, start_date, end_date)
                value_native = (Decimal(h_spec.quantity) * price).quantize(Decimal("0.00000001"))
                total_acct += self._convert_currency(value_native, h_spec.currency, acct_spec.currency, last_rate)
            account.balance_available = total_acct
            account.last_synced_at = datetime.utcnow()

        self.db.commit()
        return {"valuations": valuations, "account_balances": account_balances}

    def _append_investment_valuations_for_day(
        self,
        user: User,
        day: date,
    ) -> Dict[str, object]:
        """Add one day of investment valuations for the demo portfolio.

        Idempotent: skips when the day is already valued. Safe no-op when the
        demo investment accounts don't exist yet (a full reset creates them)."""
        accounts = self.db.query(Account).filter(
            Account.user_id == user.id,
            Account.is_active == True,
            Account.account_type.in_(("investment_brokerage", "investment_manual")),
        ).all()
        if not accounts:
            return {"skipped": True, "reason": "NO_INVESTMENT_ACCOUNTS"}

        holdings = self.db.query(Holding).filter(Holding.user_id == user.id).all()
        holding_ids = [h.id for h in holdings]
        if holding_ids:
            already = self.db.query(HoldingValuation).filter(
                HoldingValuation.holding_id.in_(holding_ids),
                HoldingValuation.date == day,
            ).first()
            if already is not None:
                return {"skipped": True, "reason": "ALREADY_VALUED", "target_date": day.isoformat()}

        holdings_by_account: Dict[str, List[Holding]] = {}
        for h in holdings:
            holdings_by_account.setdefault(str(h.account_id), []).append(h)

        spec_lookup = _holding_spec_lookup()
        rate_usd_eur = self._usd_to_eur_rate(day)
        valuations = 0
        account_balances = 0
        for account in accounts:
            total_user = Decimal("0")
            total_acct = Decimal("0")
            for h in holdings_by_account.get(str(account.id), []):
                spec = spec_lookup.get((h.source, h.symbol, h.instrument_type))
                if spec is None:
                    continue
                anchor = h.as_of_date or DEMO_DEFAULT_START_DATE
                price = self._demo_holding_price(spec, anchor, day)
                value_native = (Decimal(h.quantity) * price).quantize(Decimal("0.00000001"))
                value_user = self._convert_currency(value_native, h.currency, "EUR", rate_usd_eur)
                value_acct = self._convert_currency(value_native, h.currency, account.currency, rate_usd_eur)
                self.db.add(HoldingValuation(
                    holding_id=h.id,
                    date=day,
                    quantity=h.quantity,
                    price=price,
                    value_user_currency=value_user,
                    is_stale=False,
                ))
                valuations += 1
                total_user += value_user
                total_acct += value_acct
            self.db.add(AccountBalance(
                account_id=account.id,
                date=day,
                balance_in_account_currency=total_acct,
                balance_in_functional_currency=total_user,
            ))
            account_balances += 1
            account.balance_available = total_acct
            account.last_synced_at = datetime.utcnow()

        self.db.commit()
        return {
            "skipped": False,
            "target_date": day.isoformat(),
            "valuations": valuations,
            "account_balances": account_balances,
        }

    def _demo_holding_price(self, h_spec: HoldingSpec, anchor: date, day: date) -> Decimal:
        """Deterministic native-currency price for a holding on a given day.

        Pure function of (seed, symbol, day) so a full reset and an incremental
        daily append always agree on the price for any given date."""
        if h_spec.instrument_type == "cash":
            return Decimal("1")
        day_index = (day - anchor).days
        if day_index < 0:
            day_index = 0
        drift = 1.0 + h_spec.drift_annual * (day_index / 365.0)
        digest = hashlib.sha256(
            f"{self.random_seed}:{h_spec.symbol}:{day.isoformat()}".encode()
        ).hexdigest()
        unit = (int(digest[:8], 16) / 0xFFFFFFFF) * 2.0 - 1.0  # [-1, 1]
        factor = drift * (1.0 + h_spec.volatility * unit)
        if factor < 0.05:
            factor = 0.05
        price = Decimal(h_spec.base_price) * Decimal(str(factor))
        return price.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)

    def _convert_currency(
        self,
        amount: Decimal,
        src: str,
        dst: str,
        rate_usd_eur: Decimal,
    ) -> Decimal:
        src = (src or "").upper()
        dst = (dst or "").upper()
        if src == dst:
            converted = Decimal(amount)
        elif src == "USD" and dst == "EUR":
            converted = Decimal(amount) * rate_usd_eur
        elif src == "EUR" and dst == "USD":
            converted = Decimal(amount) / rate_usd_eur
        else:
            converted = Decimal(amount)
        return converted.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    def _usd_to_eur_rate(self, day: date) -> Decimal:
        cached = self._usd_eur_cache.get(day)
        if cached is not None:
            return cached
        rate: Optional[Decimal] = None
        try:
            rate = ExchangeRateService(self.db).get_exchange_rate(
                base_currency="USD",
                target_currency="EUR",
                for_date=day,
            )
        except Exception:  # noqa: BLE001 - fall back to a static rate
            rate = None
        value = Decimal(str(rate)) if rate else Decimal("0.92")
        self._usd_eur_cache[day] = value
        return value

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

            freelance_day = self._monthly_optional_event_day(
                event_key="freelance",
                year=year,
                month=month,
                probability=0.35,
                day_start=9,
                day_end=24,
            )
            if freelance_day is not None:
                self._append_monthly_if_in_range(
                    transactions=transactions,
                    user_id=user_id,
                    account=main_account,
                    category=category_by_name["Freelance"],
                    amount=_decimal_from_range(self.rng, 700, 2200),
                    year=year,
                    month=month,
                    day=freelance_day,
                    description="FREELANCE PROJECT PAYMENT",
                    merchant="Client Studio",
                    start_date=start_date,
                    end_date=end_date,
                )

            refund_day = self._monthly_optional_event_day(
                event_key="refund",
                year=year,
                month=month,
                probability=0.28,
                day_start=5,
                day_end=27,
            )
            if refund_day is not None:
                self._append_monthly_if_in_range(
                    transactions=transactions,
                    user_id=user_id,
                    account=main_account,
                    category=category_by_name["Refunds"],
                    amount=_decimal_from_range(self.rng, 20, 140),
                    year=year,
                    month=month,
                    day=refund_day,
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

        freelance_day = self._monthly_optional_event_day(
            event_key="freelance",
            year=day.year,
            month=day.month,
            probability=0.35,
            day_start=9,
            day_end=24,
        )
        if freelance_day is not None and day.day == freelance_day:
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

        refund_day = self._monthly_optional_event_day(
            event_key="refund",
            year=day.year,
            month=day.month,
            probability=0.28,
            day_start=5,
            day_end=27,
        )
        if refund_day is not None and day.day == refund_day:
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

        transactions.sort(key=lambda tx: tx.booked_at)
        return transactions

    def _choose_daily_template(self, current_date: date) -> TxTemplate:
        """Weighted transaction template selection with periodic USD usage."""
        usd_bias = 0.12 if current_date.weekday() >= 4 else 0.07
        if self.rng.random() < usd_bias:
            return self.rng.choice(USD_DAILY_TEMPLATES)
        return self.rng.choice(EUR_DAILY_TEMPLATES)

    def _monthly_optional_event_day(
        self,
        event_key: str,
        year: int,
        month: int,
        probability: float,
        day_start: int,
        day_end: int,
    ) -> Optional[int]:
        """Return deterministic optional event day for the month, or None."""
        month_rng = random.Random(f"{self.random_seed}:{event_key}:{year:04d}-{month:02d}")
        if month_rng.random() >= probability:
            return None
        return month_rng.randint(day_start, day_end)

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
        booked_time: Optional[tuple[int, int, int]] = None,
    ) -> Transaction:
        self._external_counter += 1
        if booked_time is None:
            booked_time = (
                self.rng.randint(7, 22),
                self.rng.randint(0, 59),
                self.rng.randint(0, 59),
            )

        booked_at = datetime.combine(
            booked_date,
            datetime.min.time(),
        ).replace(
            hour=booked_time[0],
            minute=booked_time[1],
            second=booked_time[2],
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

    def _build_balance_adjustment_transaction(
        self,
        user_id: str,
        account: Account,
        category: Category,
        amount: Decimal,
        booked_date: date,
        description: str,
        booked_time: tuple[int, int, int],
    ) -> Transaction:
        tx = self._build_transaction(
            user_id=user_id,
            account=account,
            amount=amount,
            booked_date=booked_date,
            description=description,
            merchant="System Balance Normalization",
            category=category,
            booked_time=booked_time,
        )
        tx.include_in_analytics = False
        return tx

    def _normalize_seeded_account_balances(
        self,
        user_id: str,
        accounts: List[Account],
        transactions: List[Transaction],
        category_by_name: Dict[str, Category],
        start_date: date,
        end_date: date,
    ) -> None:
        balancing_category = category_by_name["Balancing Transfer"]
        spec_by_name = {spec.name: spec for spec in ACCOUNT_SPECS}
        transactions_by_account: Dict[str, List[Transaction]] = {str(account.id): [] for account in accounts}

        for tx in transactions:
            transactions_by_account.setdefault(str(tx.account_id), []).append(tx)

        for account in accounts:
            spec = spec_by_name[account.name]
            floor = spec.minimum_balance_floor
            account_transactions = sorted(
                transactions_by_account.get(str(account.id), []),
                key=lambda tx: tx.booked_at,
            )
            total_amount = sum(
                ((tx.amount or Decimal("0")) for tx in account_transactions),
                Decimal("0"),
            )
            minimum_prefix = self._minimum_prefix_sum(account_transactions)
            starting_balance = _quantize_currency(floor - minimum_prefix)

            account.starting_balance = starting_balance
            account.balance_available = spec.target_ending_balance
            account.functional_balance = (
                spec.target_ending_balance if account.currency == "EUR" else None
            )

            adjustment_transactions = self._build_seed_balance_adjustments(
                user_id=user_id,
                account=account,
                category=balancing_category,
                opening_balance=starting_balance,
                transactions=account_transactions,
                target_ending_balance=spec.target_ending_balance,
                minimum_balance_floor=floor,
                start_date=start_date,
                end_date=end_date,
            )
            if adjustment_transactions:
                transactions.extend(adjustment_transactions)
                transactions_by_account[str(account.id)].extend(adjustment_transactions)

            logger.info(
                "[DEMO_SEED] Normalized account=%s floor=%s target=%s tx_sum=%s adjustments=%s",
                account.name,
                floor,
                spec.target_ending_balance,
                total_amount,
                len(adjustment_transactions),
            )

    def _build_seed_balance_adjustments(
        self,
        user_id: str,
        account: Account,
        category: Category,
        opening_balance: Decimal,
        transactions: List[Transaction],
        target_ending_balance: Decimal,
        minimum_balance_floor: Decimal,
        start_date: date,
        end_date: date,
    ) -> List[Transaction]:
        adjustments: List[Transaction] = []
        ending_balance = self._ending_balance(opening_balance, transactions)
        balance_delta = _quantize_currency(ending_balance - target_ending_balance)

        if balance_delta < Decimal("-0.01"):
            adjustments.append(
                self._build_balance_adjustment_transaction(
                    user_id=user_id,
                    account=account,
                    category=category,
                    amount=abs(balance_delta),
                    booked_date=end_date,
                    booked_time=(23, 59, 40),
                    description="DEMO BALANCE TOP-UP",
                )
            )
            return adjustments

        if balance_delta <= Decimal("0.01"):
            return adjustments

        remaining_delta = balance_delta
        candidate_dates = self._balance_adjustment_dates(start_date, end_date)

        for offset, candidate_date in enumerate(candidate_dates):
            if remaining_delta <= Decimal("0.01"):
                break

            candidate_transactions = sorted(
                [*transactions, *adjustments],
                key=lambda tx: tx.booked_at,
            )
            minimum_after_candidate = self._minimum_balance_after_date(
                opening_balance=opening_balance,
                transactions=candidate_transactions,
                candidate_date=candidate_date,
            )
            available_slack = _quantize_currency(
                minimum_after_candidate - minimum_balance_floor
            )
            if available_slack <= Decimal("0.01"):
                continue

            remaining_slots = len(candidate_dates) - offset
            target_slice = remaining_delta if remaining_slots <= 1 else _quantize_currency(
                remaining_delta / Decimal(remaining_slots)
            )
            adjustment_amount = _quantize_currency(
                min(remaining_delta, available_slack, target_slice)
            )
            if adjustment_amount <= Decimal("0.01"):
                continue
            adjustments.append(
                self._build_balance_adjustment_transaction(
                    user_id=user_id,
                    account=account,
                    category=category,
                    amount=adjustment_amount * Decimal("-1"),
                    booked_date=candidate_date,
                    booked_time=(23, 59, max(0, 39 - (offset % 30))),
                    description="DEMO BALANCE SWEEP",
                )
            )
            remaining_delta = _quantize_currency(remaining_delta - adjustment_amount)

        if remaining_delta > Decimal("0.01"):
            logger.warning(
                "[DEMO_SEED] Could not fully normalize ending balance for account=%s remaining_delta=%s",
                account.name,
                remaining_delta,
            )

        return adjustments

    def _normalize_daily_account_balances(
        self,
        user_id: str,
        target_date: date,
        daily_transactions: List[Transaction],
        accounts: List[Account],
        category_by_name: Dict[str, Category],
    ) -> None:
        if not daily_transactions:
            return

        balancing_category = category_by_name["Balancing Transfer"]
        spec_by_name = {spec.name: spec for spec in ACCOUNT_SPECS}
        accounts_by_id = {str(account.id): account for account in accounts}
        daily_by_account: Dict[str, List[Transaction]] = {}

        for tx in daily_transactions:
            daily_by_account.setdefault(str(tx.account_id), []).append(tx)

        day_start = datetime.combine(target_date, datetime.min.time())

        for account_id, account_transactions in daily_by_account.items():
            account = accounts_by_id.get(account_id)
            if not account:
                continue

            spec = spec_by_name.get(account.name)
            if not spec:
                continue

            opening_sum = self.db.query(func.sum(Transaction.amount)).filter(
                Transaction.user_id == user_id,
                Transaction.account_id == account.id,
                Transaction.booked_at < day_start,
            ).scalar()
            opening_balance = _quantize_currency(
                Decimal(str(account.starting_balance or 0)) + Decimal(str(opening_sum or 0))
            )

            ordered_transactions = sorted(account_transactions, key=lambda tx: tx.booked_at)
            minimum_balance = self._minimum_balance(
                opening_balance=opening_balance,
                transactions=ordered_transactions,
            )
            if minimum_balance >= spec.minimum_balance_floor:
                continue

            top_up_amount = _quantize_currency(spec.minimum_balance_floor - minimum_balance)
            natural_ending_balance = self._ending_balance(opening_balance, ordered_transactions)
            desired_ending_balance = max(natural_ending_balance, spec.minimum_balance_floor)

            opening_adjustment = self._build_balance_adjustment_transaction(
                user_id=user_id,
                account=account,
                category=balancing_category,
                amount=top_up_amount,
                booked_date=target_date,
                booked_time=(6, 0, 0),
                description="DEMO DAILY FLOOR TOP-UP",
            )
            daily_transactions.append(opening_adjustment)

            closing_amount = _quantize_currency(
                (natural_ending_balance + top_up_amount) - desired_ending_balance
            )
            if closing_amount > Decimal("0.01"):
                daily_transactions.append(
                    self._build_balance_adjustment_transaction(
                        user_id=user_id,
                        account=account,
                        category=balancing_category,
                        amount=closing_amount * Decimal("-1"),
                        booked_date=target_date,
                        booked_time=(23, 59, 50),
                        description="DEMO DAILY BALANCE SWEEP",
                    )
                )

    def _minimum_prefix_sum(self, transactions: List[Transaction]) -> Decimal:
        balance = Decimal("0")
        minimum_balance = Decimal("0")

        for tx in sorted(transactions, key=lambda item: item.booked_at):
            balance += tx.amount or Decimal("0")
            if balance < minimum_balance:
                minimum_balance = balance

        return _quantize_currency(minimum_balance)

    def _minimum_balance(
        self,
        opening_balance: Decimal,
        transactions: List[Transaction],
    ) -> Decimal:
        balance = opening_balance
        minimum_balance = opening_balance

        for tx in sorted(transactions, key=lambda item: item.booked_at):
            balance += tx.amount or Decimal("0")
            if balance < minimum_balance:
                minimum_balance = balance

        return _quantize_currency(minimum_balance)

    def _ending_balance(
        self,
        opening_balance: Decimal,
        transactions: List[Transaction],
    ) -> Decimal:
        balance = opening_balance
        for tx in sorted(transactions, key=lambda item: item.booked_at):
            balance += tx.amount or Decimal("0")
        return _quantize_currency(balance)

    def _minimum_balance_after_date(
        self,
        opening_balance: Decimal,
        transactions: List[Transaction],
        candidate_date: date,
    ) -> Decimal:
        balance = opening_balance
        minimum_after: Optional[Decimal] = None
        captured_candidate = False

        for tx in sorted(transactions, key=lambda item: item.booked_at):
            if not captured_candidate and tx.booked_at.date() > candidate_date:
                minimum_after = balance
                captured_candidate = True

            balance += tx.amount or Decimal("0")
            if captured_candidate:
                minimum_after = balance if minimum_after is None else min(minimum_after, balance)

        if not captured_candidate:
            minimum_after = balance

        return _quantize_currency(minimum_after if minimum_after is not None else balance)

    def _balance_adjustment_dates(self, start_date: date, end_date: date) -> List[date]:
        dates = {start_date, end_date}
        for month_anchor in _iter_month_anchors(start_date, end_date):
            month_end = date(month_anchor.year, month_anchor.month, _days_in_month(month_anchor.year, month_anchor.month))
            dates.add(min(month_end, end_date))
        return sorted(dates)

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


def _holding_spec_lookup() -> Dict[Tuple[str, str, str], HoldingSpec]:
    """Map (source, symbol, instrument_type) -> HoldingSpec for the demo
    portfolio, so the daily append can recompute the same deterministic price
    path from persisted holdings."""
    lookup: Dict[Tuple[str, str, str], HoldingSpec] = {}
    for acct_spec in INVESTMENT_ACCOUNT_SPECS:
        for h_spec in acct_spec.holdings:
            lookup[(acct_spec.source, h_spec.symbol, h_spec.instrument_type)] = h_spec
    return lookup


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
