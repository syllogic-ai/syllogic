"""
SQLAlchemy models matching the Drizzle schema.ts structure.
These models mirror the frontend Drizzle schema for consistency.
"""
import uuid
from datetime import datetime
from sqlalchemy import (
    Column,
    String,
    Boolean,
    DateTime,
    Numeric,
    Text,
    Integer,
    ForeignKey,
    Index,
    UniqueConstraint,
    JSON,
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from decimal import Decimal

from app.database import Base


class Account(Base):
    """
    Account model matching Drizzle schema.
    Note: Includes userId for multi-tenancy support.
    """
    __tablename__ = "accounts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(255), nullable=False)
    account_type = Column(String(50), nullable=False)  # checking, savings, credit
    institution = Column(String(255))
    currency = Column(String(3), default="EUR")
    provider = Column(String(50), nullable=True)  # gocardless, manual
    external_id = Column(String(255), nullable=True)  # Provider's account ID
    balance_available = Column(Numeric(15, 2), nullable=True)
    starting_balance = Column(Numeric(15, 2), default=Decimal("0"))  # Starting balance for calculation
    functional_balance = Column(Numeric(15, 2), nullable=True)  # Calculated balance (sum of transactions + starting_balance)
    is_active = Column(Boolean, default=True)
    last_synced_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    user = relationship("User", back_populates="accounts")
    transactions = relationship("Transaction", back_populates="account")
    csv_imports = relationship("CsvImport", back_populates="account")
    balances = relationship("AccountBalance", back_populates="account")

    # Indexes and constraints
    __table_args__ = (
        Index("idx_accounts_user", "user_id"),
        UniqueConstraint("user_id", "provider", "external_id", name="accounts_user_provider_external_id"),
    )


class Category(Base):
    """
    Category model matching Drizzle schema.
    Note: Includes userId for multi-tenancy support.
    """
    __tablename__ = "categories"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(255), nullable=False)
    parent_id = Column(UUID(as_uuid=True), ForeignKey("categories.id"), nullable=True)
    category_type = Column(String(20), default="expense")  # expense, income, transfer
    color = Column(String(7))  # Hex color
    icon = Column(String(50))  # Remix icon name
    description = Column(Text, nullable=True)  # Category description
    categorization_instructions = Column(Text, nullable=True)  # User instructions for AI categorization
    is_system = Column(Boolean, default=False)
    hide_from_selection = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    user = relationship("User", back_populates="categories")
    parent = relationship("Category", remote_side=[id], backref="children")
    transactions = relationship("Transaction", back_populates="category", foreign_keys="Transaction.category_id")
    system_transactions = relationship("Transaction", back_populates="category_system", foreign_keys="Transaction.category_system_id")
    categorization_rules = relationship("CategorizationRule", back_populates="category")

    # Indexes and constraints
    __table_args__ = (
        Index("idx_categories_user", "user_id"),
        UniqueConstraint("user_id", "name", "parent_id", name="categories_user_name_parent"),
    )


class Transaction(Base):
    """
    Transaction model matching Drizzle schema.
    Note: Includes userId for multi-tenancy support and separate category fields.
    """
    __tablename__ = "transactions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    account_id = Column(UUID(as_uuid=True), ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False, index=True)
    external_id = Column(String(255), nullable=True)
    transaction_type = Column(String(20))  # debit, credit
    amount = Column(Numeric(15, 2), nullable=False)
    currency = Column(String(3), default="EUR")
    functional_amount = Column(Numeric(15, 2), nullable=True)  # Amount converted to user's functional currency
    description = Column(Text)
    merchant = Column(String(255))
    category_id = Column(UUID(as_uuid=True), ForeignKey("categories.id"), nullable=True, index=True)  # User-overridden category
    category_system_id = Column(UUID(as_uuid=True), ForeignKey("categories.id"), nullable=True, index=True)  # AI-assigned category
    booked_at = Column(DateTime, nullable=False, index=True)
    pending = Column(Boolean, default=False)
    categorization_instructions = Column(Text)  # User instructions for AI categorization
    enrichment_data = Column(JSONB)  # Enriched merchant info, logos, etc.
    recurring_transaction_id = Column(UUID(as_uuid=True), ForeignKey("recurring_transactions.id", ondelete="SET NULL"), nullable=True, index=True)  # Link to recurring transaction label
    include_in_analytics = Column(Boolean, default=True, nullable=False)  # Whether to include in analytics (charts, KPIs, etc.)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    user = relationship("User", back_populates="transactions")
    account = relationship("Account", back_populates="transactions")
    category = relationship("Category", foreign_keys=[category_id], back_populates="transactions")
    category_system = relationship("Category", foreign_keys=[category_system_id], back_populates="system_transactions")
    recurring_transaction = relationship("RecurringTransaction", back_populates="linked_transactions")
    transaction_link = relationship("TransactionLink", back_populates="transaction", uselist=False)

    # Indexes and constraints
    __table_args__ = (
        Index("idx_transactions_user", "user_id"),
        Index("idx_transactions_account", "account_id"),
        Index("idx_transactions_booked_at", "booked_at"),
        Index("idx_transactions_category", "category_id"),
        Index("idx_transactions_category_system", "category_system_id"),
        Index("idx_transactions_recurring", "recurring_transaction_id"),
        UniqueConstraint("account_id", "external_id", name="transactions_account_external_id"),
    )


class RecurringTransaction(Base):
    """
    Recurring Transaction model matching Drizzle schema.
    Stores recurring transaction labels (subscriptions, bills, etc.) for automatic linking.
    """
    __tablename__ = "recurring_transactions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(255), nullable=False)
    merchant = Column(String(255), nullable=True)
    amount = Column(Numeric(15, 2), nullable=False)
    currency = Column(String(3), default="EUR")
    category_id = Column(UUID(as_uuid=True), ForeignKey("categories.id"), nullable=True, index=True)
    logo_id = Column(UUID(as_uuid=True), ForeignKey("company_logos.id", ondelete="SET NULL"), nullable=True)
    importance = Column(Integer, nullable=False, default=3)  # 1-5 scale
    frequency = Column(String(20), nullable=False)  # monthly, weekly, yearly, quarterly, biweekly
    is_active = Column(Boolean, default=True)
    description = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    user = relationship("User", back_populates="recurring_transactions")
    category = relationship("Category")
    logo = relationship("CompanyLogo", back_populates="recurring_transactions")
    linked_transactions = relationship("Transaction", back_populates="recurring_transaction")

    # Indexes and constraints
    __table_args__ = (
        Index("idx_recurring_transactions_user", "user_id"),
        Index("idx_recurring_transactions_category", "category_id"),
        Index("idx_recurring_transactions_active", "is_active"),
    )


class CategorizationRule(Base):
    """
    Categorization rules model matching Drizzle schema.
    Stores user-provided instructions for AI categorization.
    """
    __tablename__ = "categorization_rules"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    category_id = Column(UUID(as_uuid=True), ForeignKey("categories.id", ondelete="CASCADE"), nullable=False)
    instructions = Column(Text)  # User-provided instructions for AI categorization
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    user = relationship("User", back_populates="categorization_rules")
    category = relationship("Category", back_populates="categorization_rules")


class BankConnection(Base):
    """
    Bank connections model matching Drizzle schema.
    Stores GoCardless/Nordigen/Ponto bank connection information.
    """
    __tablename__ = "bank_connections"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    institution_id = Column(String(255), nullable=False)
    institution_name = Column(String(255))
    requisition_id = Column(String(255), unique=True)
    status = Column(String(50))  # pending, linked, expired, revoked
    agreement_id = Column(String(255))
    link = Column(Text)  # Authorization link
    provider = Column(String(50), nullable=True)  # gocardless, ponto, etc.
    sync_status = Column(String(50), nullable=True)  # syncing, synced, failed, idle
    last_synced_at = Column(DateTime, nullable=True)
    error_message = Column(Text, nullable=True)
    # Ponto-specific fields
    organization_id = Column(String(255), nullable=True)  # Ponto organization ID
    access_token = Column(Text, nullable=True)  # Encrypted Ponto access token
    refresh_token = Column(Text, nullable=True)  # Encrypted Ponto refresh token
    access_token_expires_at = Column(DateTime, nullable=True)  # Token expiry
    created_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime, nullable=True)

    # Relationships
    user = relationship("User", back_populates="bank_connections")


class CsvImport(Base):
    """
    CSV Import model matching Drizzle schema.
    Stores CSV import job information.
    """
    __tablename__ = "csv_imports"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    account_id = Column(UUID(as_uuid=True), ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False, index=True)
    file_name = Column(String(255), nullable=False)
    file_path = Column(Text, nullable=True)
    status = Column(String(20), default="pending")  # pending, mapping, previewing, importing, completed, failed
    column_mapping = Column(JSONB, nullable=True)
    total_rows = Column(Integer, nullable=True)
    imported_rows = Column(Integer, nullable=True)
    duplicates_found = Column(Integer, nullable=True)
    error_message = Column(Text, nullable=True)
    # Background worker fields
    celery_task_id = Column(String(255), nullable=True)
    progress_count = Column(Integer, default=0)
    selected_indices = Column(JSONB, nullable=True)  # Array of row indices selected for import
    created_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)

    # Relationships
    user = relationship("User", back_populates="csv_imports")
    account = relationship("Account", back_populates="csv_imports")

    # Indexes and constraints
    __table_args__ = (
        Index("idx_csv_imports_user", "user_id"),
        Index("idx_csv_imports_account", "account_id"),
    )


class ExchangeRate(Base):
    """
    Exchange rate model for currency conversion.
    Stores daily exchange rates between base currencies and target currencies (EUR, USD).
    """
    __tablename__ = "exchange_rates"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    date = Column(DateTime, nullable=False, index=True)  # Date of the exchange rate
    base_currency = Column(String(3), nullable=False, index=True)  # Source currency (transaction currency)
    target_currency = Column(String(3), nullable=False, index=True)  # Target currency (EUR or USD)
    rate = Column(Numeric(18, 8), nullable=False)  # Exchange rate (how many target currency = 1 base currency)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Indexes and constraints
    __table_args__ = (
        Index("idx_exchange_rates_date", "date"),
        Index("idx_exchange_rates_base", "base_currency"),
        Index("idx_exchange_rates_target", "target_currency"),
        UniqueConstraint("date", "base_currency", "target_currency", name="exchange_rates_date_base_target"),
    )


class AccountBalance(Base):
    """
    Account balance model for daily balance snapshots.
    Stores daily balance for each account in both account currency and functional currency.
    """
    __tablename__ = "account_balances"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    account_id = Column(UUID(as_uuid=True), ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False, index=True)
    date = Column(DateTime, nullable=False, index=True)  # Date of the balance snapshot
    balance_in_account_currency = Column(Numeric(15, 2), nullable=False)  # Balance in account's currency
    balance_in_functional_currency = Column(Numeric(15, 2), nullable=False)  # Balance converted to functional currency
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    account = relationship("Account", back_populates="balances")

    # Indexes and constraints
    __table_args__ = (
        Index("idx_account_balances_account", "account_id"),
        Index("idx_account_balances_date", "date"),
        UniqueConstraint("account_id", "date", name="account_balances_account_date"),
    )


class Property(Base):
    """
    Property model matching Drizzle schema.
    Stores real estate properties owned by users.
    """
    __tablename__ = "properties"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(255), nullable=False)
    property_type = Column(String(50), nullable=False)  # residential, commercial, land, other
    address = Column(Text, nullable=True)
    current_value = Column(Numeric(15, 2), default=Decimal("0"))
    currency = Column(String(3), default="EUR")
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    user = relationship("User", back_populates="properties")

    # Indexes and constraints
    __table_args__ = (
        Index("idx_properties_user", "user_id"),
    )


class Vehicle(Base):
    """
    Vehicle model matching Drizzle schema.
    Stores vehicles owned by users.
    """
    __tablename__ = "vehicles"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(255), nullable=False)
    vehicle_type = Column(String(50), nullable=False)  # car, motorcycle, boat, rv, other
    make = Column(String(100), nullable=True)
    model = Column(String(100), nullable=True)
    year = Column(Integer, nullable=True)
    current_value = Column(Numeric(15, 2), default=Decimal("0"))
    currency = Column(String(3), default="EUR")
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    user = relationship("User", back_populates="vehicles")

    # Indexes and constraints
    __table_args__ = (
        Index("idx_vehicles_user", "user_id"),
    )


class SubscriptionSuggestion(Base):
    """
    Subscription suggestion model matching Drizzle schema.
    Stores detected subscription patterns for user review.
    """
    __tablename__ = "subscription_suggestions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)

    # Suggestion details
    suggested_name = Column(String(255), nullable=False)
    suggested_merchant = Column(String(255), nullable=True)
    suggested_amount = Column(Numeric(15, 2), nullable=False)
    currency = Column(String(3), default="EUR", nullable=False)
    detected_frequency = Column(String(20), nullable=False)  # weekly, biweekly, monthly, quarterly, yearly
    confidence = Column(Integer, nullable=False)  # 0-100

    # Linked transactions (stored as JSON array of IDs)
    matched_transaction_ids = Column(Text, nullable=False)  # JSON array

    # Status
    status = Column(String(20), default="pending", nullable=False)  # pending, approved, dismissed

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationships
    user = relationship("User", back_populates="subscription_suggestions")

    # Indexes
    __table_args__ = (
        Index("idx_subscription_suggestions_user", "user_id"),
        Index("idx_subscription_suggestions_status", "status"),
    )


class TransactionLink(Base):
    """
    Transaction link model matching Drizzle schema.
    Links transactions together for reimbursement/expense tracking.
    """
    __tablename__ = "transaction_links"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    group_id = Column(UUID(as_uuid=True), nullable=False, index=True)  # Groups linked transactions together
    transaction_id = Column(UUID(as_uuid=True), ForeignKey("transactions.id", ondelete="CASCADE"), nullable=False)
    link_role = Column(String(20), nullable=False)  # "primary" | "reimbursement" | "expense"
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    user = relationship("User", back_populates="transaction_links")
    transaction = relationship("Transaction", back_populates="transaction_link")

    # Indexes and constraints
    __table_args__ = (
        Index("idx_transaction_links_user", "user_id"),
        Index("idx_transaction_links_group", "group_id"),
        UniqueConstraint("transaction_id", name="transaction_links_transaction_unique"),
    )


class CompanyLogo(Base):
    """
    Company logo model matching Drizzle schema.
    Stores company logos for subscriptions and recurring transactions.
    """
    __tablename__ = "company_logos"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    domain = Column(String(255), nullable=True)  # "netflix.com"
    company_name = Column(String(255), nullable=True)  # "Netflix"
    logo_url = Column(Text, nullable=True)  # Local path: "/uploads/logos/netflix.png"
    status = Column(String(20), default="found", nullable=False)  # "found" | "not_found"
    last_checked_at = Column(DateTime, default=datetime.utcnow)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    recurring_transactions = relationship("RecurringTransaction", back_populates="logo")

    # Indexes and constraints
    __table_args__ = (
        Index("idx_company_logos_domain", "domain"),
        Index("idx_company_logos_name", "company_name"),
        UniqueConstraint("domain", name="company_logos_domain_unique"),
    )


# ============================================================================
# BetterAuth Tables (minimal models for foreign key relationships)
# ============================================================================

class VerificationToken(Base):
    """
    VerificationToken model for BetterAuth integration.
    Stores email verification tokens.
    Minimal model matching Drizzle schema for foreign key relationships.
    """
    __tablename__ = "verification_tokens"

    id = Column(String, primary_key=True)
    identifier = Column(String, nullable=False)
    token = Column(String, unique=True, nullable=False)
    expires_at = Column(DateTime, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Session(Base):
    """
    Session model for BetterAuth integration.
    Stores user session information.
    Minimal model matching Drizzle schema for foreign key relationships.
    """
    __tablename__ = "sessions"

    id = Column(String, primary_key=True)
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    token = Column(String, unique=True, nullable=False)
    expires_at = Column(DateTime, nullable=False)
    ip_address = Column(Text, nullable=True)
    user_agent = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    user = relationship("User", back_populates="sessions")


class AuthAccount(Base):
    """
    AuthAccount model for BetterAuth integration.
    Stores authentication account information (OAuth providers, credentials, etc.).
    Minimal model matching Drizzle schema for foreign key relationships.
    """
    __tablename__ = "auth_accounts"

    id = Column(String, primary_key=True)
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    account_id = Column(String, nullable=False)
    provider_id = Column(String, nullable=False)
    access_token = Column(Text, nullable=True)
    refresh_token = Column(Text, nullable=True)
    access_token_expires_at = Column(DateTime, nullable=True)
    refresh_token_expires_at = Column(DateTime, nullable=True)
    scope = Column(Text, nullable=True)
    id_token = Column(Text, nullable=True)
    password = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    user = relationship("User", back_populates="auth_accounts")


class User(Base):
    """
    User model for BetterAuth integration.
    Minimal model for foreign key relationships.
    Full user management is handled by BetterAuth in the frontend.
    """
    __tablename__ = "users"

    id = Column(String, primary_key=True)
    name = Column(Text, nullable=True)
    email = Column(Text, unique=True, nullable=False)
    email_verified = Column(Boolean, default=False)
    image = Column(Text, nullable=True)
    onboarding_status = Column(String(20), default="pending")  # pending, step_1, step_2, step_3, completed
    onboarding_completed_at = Column(DateTime, nullable=True)
    functional_currency = Column(String(3), default="EUR")  # User's functional currency for reporting
    profile_photo_path = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    sessions = relationship("Session", back_populates="user", cascade="all, delete-orphan")
    auth_accounts = relationship("AuthAccount", back_populates="user", cascade="all, delete-orphan")
    accounts = relationship("Account", back_populates="user", cascade="all, delete-orphan")
    categories = relationship("Category", back_populates="user", cascade="all, delete-orphan")
    transactions = relationship("Transaction", back_populates="user", cascade="all, delete-orphan")
    recurring_transactions = relationship("RecurringTransaction", back_populates="user", cascade="all, delete-orphan")
    categorization_rules = relationship("CategorizationRule", back_populates="user", cascade="all, delete-orphan")
    bank_connections = relationship("BankConnection", back_populates="user", cascade="all, delete-orphan")
    csv_imports = relationship("CsvImport", back_populates="user", cascade="all, delete-orphan")
    properties = relationship("Property", back_populates="user", cascade="all, delete-orphan")
    vehicles = relationship("Vehicle", back_populates="user", cascade="all, delete-orphan")
    subscription_suggestions = relationship("SubscriptionSuggestion", back_populates="user", cascade="all, delete-orphan")
    api_keys = relationship("ApiKey", back_populates="user", cascade="all, delete-orphan")
    transaction_links = relationship("TransactionLink", back_populates="user", cascade="all, delete-orphan")


class ApiKey(Base):
    """
    API Key model for MCP server authentication.
    Stores hashed API keys for secure authentication.
    """
    __tablename__ = "api_keys"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(255), nullable=False)
    key_hash = Column(String(128), nullable=False, index=True)  # Supports bcrypt (60 chars) and SHA-256 (64 chars)
    key_prefix = Column(String(12), nullable=False)
    last_used_at = Column(DateTime, nullable=True)
    expires_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    user = relationship("User", back_populates="api_keys")

    # Indexes
    __table_args__ = (
        Index("idx_api_keys_user", "user_id"),
        Index("idx_api_keys_hash", "key_hash"),
    )