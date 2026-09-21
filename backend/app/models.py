"""
SQLAlchemy models matching the Drizzle schema.ts structure.
These models mirror the frontend Drizzle schema for consistency.
"""

import uuid
from datetime import datetime, time, timezone
from sqlalchemy import (
    Column,
    String,
    Boolean,
    Date,
    DateTime,
    Time,
    Numeric,
    Text,
    Integer,
    ForeignKey,
    Index,
    JSON,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from decimal import Decimal

from app.database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


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
    logo_id = Column(
        UUID(as_uuid=True), ForeignKey("company_logos.id", ondelete="SET NULL"), nullable=True
    )
    currency = Column(String(3), default="EUR")
    provider = Column(String(50), nullable=True)  # gocardless, manual
    external_id = Column(String(255), nullable=True)  # Provider's account ID
    external_id_ciphertext = Column(Text, nullable=True)
    external_id_hash = Column(String(64), nullable=True, index=True)
    iban_ciphertext = Column(Text, nullable=True)
    iban_hash = Column(
        String(64), nullable=True, index=False
    )  # composite index defined in __table_args__
    bank_connection_id = Column(
        UUID(as_uuid=True), ForeignKey("bank_connections.id", ondelete="SET NULL"), nullable=True
    )
    balance_available = Column(Numeric(15, 2), nullable=True)
    starting_balance = Column(
        Numeric(15, 2), default=Decimal("0")
    )  # Starting balance for calculation
    credit_limit = Column(
        Numeric(15, 2), nullable=True
    )  # Credit card limit, used to derive available credit
    functional_balance = Column(
        Numeric(15, 2), nullable=True
    )  # Calculated balance (sum of transactions + starting_balance)
    balance_is_anchored = Column(
        Boolean, default=False
    )  # True when starting_balance is from verified bank data
    is_active = Column(Boolean, default=True)
    alias_patterns = Column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))
    last_synced_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=_utcnow)
    updated_at = Column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)

    # Relationships
    user = relationship("User", back_populates="accounts")
    logo = relationship("CompanyLogo", back_populates="accounts")
    bank_connection = relationship("BankConnection", back_populates="accounts")
    transactions = relationship(
        "Transaction",
        back_populates="account",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    csv_imports = relationship("CsvImport", back_populates="account")
    receipt_scans = relationship("ReceiptScan", back_populates="account")
    balances = relationship("AccountBalance", back_populates="account")
    recurring_transactions = relationship("RecurringTransaction", back_populates="account")
    subscription_suggestions = relationship("SubscriptionSuggestion", back_populates="account")

    # Indexes and constraints
    __table_args__ = (
        Index("idx_accounts_user", "user_id"),
        UniqueConstraint(
            "user_id", "provider", "external_id", name="accounts_user_provider_external_id"
        ),
        Index(
            "accounts_user_provider_external_id_hash_uq",
            "user_id",
            "provider",
            "external_id_hash",
            unique=True,
            postgresql_where=text("external_id_hash IS NOT NULL"),
        ),
        Index("idx_accounts_bank_connection", "bank_connection_id"),
        Index("idx_accounts_user_iban_hash", "user_id", "iban_hash"),
    )


class BankConnection(Base):
    """
    Bank connection model for Enable Banking sessions.
    Tracks consent lifecycle and sync state.
    """

    __tablename__ = "bank_connections"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    provider = Column(String(50), nullable=False, default="enable_banking")
    session_id = Column(String(255), nullable=False)
    aspsp_name = Column(String(255), nullable=False)
    aspsp_country = Column(String(2), nullable=False)
    consent_expires_at = Column(DateTime(timezone=True), nullable=True)
    consent_notified_at = Column(DateTime(timezone=True), nullable=True)
    status = Column(String(20), nullable=False, default="active")
    last_synced_at = Column(DateTime(timezone=True), nullable=True)
    sync_started_at = Column(DateTime(timezone=True), nullable=True)
    last_sync_error = Column(Text, nullable=True)
    sync_cursor = Column(JSONB, nullable=True)
    initial_sync_days = Column(Integer, nullable=False, server_default="90")
    raw_session_data = Column(JSONB, nullable=True)
    created_at = Column(DateTime(timezone=True), default=_utcnow)
    updated_at = Column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)

    # Relationships
    user = relationship("User", back_populates="bank_connections")
    accounts = relationship("Account", back_populates="bank_connection")

    __table_args__ = (
        Index("idx_bank_connections_user", "user_id"),
        Index("idx_bank_connections_status", "status"),
        Index("idx_bank_connections_consent_expires", "consent_expires_at"),
        UniqueConstraint("user_id", "session_id", name="bank_connections_user_session"),
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
    categorization_instructions = Column(
        Text, nullable=True
    )  # User instructions for AI categorization
    is_system = Column(Boolean, default=False)
    hide_from_selection = Column(Boolean, default=False)
    system_key = Column(
        String(50), nullable=True, index=True
    )  # stable, non-translated identifier for system categories
    created_at = Column(DateTime(timezone=True), default=_utcnow)

    # Relationships
    user = relationship("User", back_populates="categories")
    parent = relationship("Category", remote_side=[id], backref="children")
    transactions = relationship(
        "Transaction", back_populates="category", foreign_keys="Transaction.category_id"
    )
    system_transactions = relationship(
        "Transaction",
        back_populates="category_system",
        foreign_keys="Transaction.category_system_id",
    )
    categorization_rules = relationship("CategorizationRule", back_populates="category")
    subscription_suggestions = relationship(
        "SubscriptionSuggestion", back_populates="suggested_category"
    )
    receipt_line_items = relationship("ReceiptLineItem", back_populates="category")
    budget_categories = relationship("BudgetCategory", back_populates="category")

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
    account_id = Column(
        UUID(as_uuid=True),
        ForeignKey("accounts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    external_id = Column(String(255), nullable=True)
    transaction_type = Column(String(20))  # debit, credit
    amount = Column(Numeric(15, 2), nullable=False)
    currency = Column(String(3), default="EUR")
    functional_amount = Column(
        Numeric(15, 2), nullable=True
    )  # Amount converted to user's functional currency
    description = Column(Text)
    merchant = Column(String(255))
    creditor = Column(String(255), nullable=True)  # Counterparty name for debits (payee)
    debtor = Column(String(255), nullable=True)  # Counterparty name for credits (payer)
    counterparty_iban_ciphertext = Column(Text, nullable=True)
    counterparty_iban_hash = Column(String(64), nullable=True)
    internal_transfer_id = Column(
        UUID(as_uuid=True),
        ForeignKey("internal_transfers.id", ondelete="SET NULL"),
        nullable=True,
    )
    category_id = Column(
        UUID(as_uuid=True), ForeignKey("categories.id"), nullable=True, index=True
    )  # User-overridden category
    category_system_id = Column(
        UUID(as_uuid=True), ForeignKey("categories.id"), nullable=True, index=True
    )  # AI-assigned category
    booked_at = Column(DateTime(timezone=True), nullable=False, index=True)
    pending = Column(Boolean, default=False)
    categorization_instructions = Column(Text)  # User instructions for AI categorization
    enrichment_data = Column(JSONB)  # Enriched merchant info, logos, etc.
    logo_id = Column(
        UUID(as_uuid=True), ForeignKey("company_logos.id", ondelete="SET NULL"), nullable=True
    )
    recurring_transaction_id = Column(
        UUID(as_uuid=True),
        ForeignKey("recurring_transactions.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )  # Link to recurring transaction label
    include_in_analytics = Column(
        Boolean, default=True, nullable=False
    )  # Whether to include in analytics (charts, KPIs, etc.)
    # True while this row is a placeholder materialized from a
    # RecurringTransaction schedule. Cleared when a bank/CSV row is adopted
    # onto it (see services/recurring_transaction_dedupe.py).
    auto_generated = Column(Boolean, default=False, nullable=False, server_default="false")
    csv_import_id = Column(
        UUID(as_uuid=True),
        ForeignKey("csv_imports.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )  # Source CSV import (null for manual/bank-synced)
    receipt_scan_id = Column(
        UUID(as_uuid=True),
        ForeignKey("receipt_scans.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )  # Source receipt scan (null unless created by splitting a scanned receipt)
    created_at = Column(DateTime(timezone=True), default=_utcnow)
    updated_at = Column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)

    # Relationships
    user = relationship("User", back_populates="transactions")
    account = relationship("Account", back_populates="transactions")
    category = relationship("Category", foreign_keys=[category_id], back_populates="transactions")
    category_system = relationship(
        "Category", foreign_keys=[category_system_id], back_populates="system_transactions"
    )
    recurring_transaction = relationship(
        "RecurringTransaction", back_populates="linked_transactions"
    )
    transaction_link = relationship("TransactionLink", back_populates="transaction", uselist=False)
    csv_import = relationship("CsvImport", back_populates="transactions")
    receipt_scan = relationship("ReceiptScan", back_populates="transactions")
    internal_transfer = relationship("InternalTransfer", foreign_keys=[internal_transfer_id])
    logo = relationship("CompanyLogo", back_populates="transactions")
    receipt_line_items = relationship("ReceiptLineItem", back_populates="booked_transaction")

    # Indexes and constraints
    __table_args__ = (
        Index("idx_transactions_user", "user_id"),
        Index("idx_transactions_account", "account_id"),
        Index("idx_transactions_booked_at", "booked_at"),
        Index("idx_transactions_category", "category_id"),
        Index("idx_transactions_category_system", "category_system_id"),
        Index("idx_transactions_recurring", "recurring_transaction_id"),
        Index("idx_transactions_logo", "logo_id"),
        Index("idx_transactions_csv_import", "csv_import_id"),
        Index("idx_transactions_receipt_scan", "receipt_scan_id"),
        UniqueConstraint("account_id", "external_id", name="transactions_account_external_id"),
        Index("idx_transactions_user_counterparty_iban", "user_id", "counterparty_iban_hash"),
        # Composite indexes matching the dominant access pattern: one user's
        # transactions, newest first, optionally narrowed by account or
        # category -- covers list_transactions/get_transaction_page without
        # Postgres having to combine separate single-column indexes or sort.
        #
        # The GIN/pg_trgm indexes backing MCP transaction search are declared
        # only in migration 0046, not here: they need the pg_trgm extension,
        # and create_all() in tests must not depend on it being installed.
        Index("idx_transactions_user_booked_at", "user_id", booked_at.desc()),
        Index("idx_transactions_user_account_booked_at", "user_id", "account_id", booked_at.desc()),
        Index(
            "idx_transactions_user_category_booked_at", "user_id", "category_id", booked_at.desc()
        ),
    )


class Report(Base):
    """Newsletter report configuration."""

    __tablename__ = "reports"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(255), nullable=False)
    account_ids = Column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))
    transaction_mode = Column(String(20), nullable=False, default="RECENT")
    transaction_count = Column(Integer, nullable=False, default=10)
    transaction_direction = Column(String(20), nullable=False, default="ALL")
    frequency = Column(String(20), nullable=False)
    send_time = Column(Time, nullable=False, default=time(8, 0))
    send_day_of_week = Column(Integer, nullable=True)
    send_day_of_month = Column(Integer, nullable=True)
    timezone = Column(String(64), nullable=False, default="UTC")
    recipient_emails = Column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))
    is_active = Column(Boolean, default=True, nullable=False)
    next_run_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=_utcnow)
    updated_at = Column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)

    user = relationship("User")
    runs = relationship("ReportRun", back_populates="report", cascade="all, delete-orphan")

    __table_args__ = (
        Index("idx_reports_user", "user_id"),
        Index("idx_reports_next_run_at", "next_run_at"),
    )


class ReportRun(Base):
    """Single scheduled or ad-hoc execution of a Report."""

    __tablename__ = "report_runs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    report_id = Column(
        UUID(as_uuid=True), ForeignKey("reports.id", ondelete="CASCADE"), nullable=False
    )
    scheduled_for = Column(DateTime(timezone=True), nullable=True)
    is_test = Column(Boolean, default=False, nullable=False)
    started_at = Column(DateTime(timezone=True), nullable=True)
    finished_at = Column(DateTime(timezone=True), nullable=True)
    status = Column(String(20), nullable=False, default="SCHEDULED")
    error_message = Column(Text, nullable=True)
    recipient_emails = Column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))
    created_at = Column(DateTime(timezone=True), default=_utcnow)

    report = relationship("Report", back_populates="runs")

    __table_args__ = (
        Index("idx_report_runs_report", "report_id"),
        Index("idx_report_runs_status", "status"),
    )


class InternalTransfer(Base):
    """
    Internal transfer model matching Drizzle schema.
    Links a source transaction on a synced account to a mirror transaction
    on a manually-registered pocket account, matched by counterparty IBAN.
    """

    __tablename__ = "internal_transfers"

    id = Column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    source_txn_id = Column(
        UUID(as_uuid=True),
        ForeignKey("transactions.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    mirror_txn_id = Column(
        UUID(as_uuid=True),
        ForeignKey("transactions.id", ondelete="SET NULL"),
        nullable=True,
        unique=True,
    )
    source_account_id = Column(
        UUID(as_uuid=True),
        ForeignKey("accounts.id", ondelete="CASCADE"),
        nullable=False,
    )
    pocket_account_id = Column(
        UUID(as_uuid=True),
        ForeignKey("accounts.id", ondelete="CASCADE"),
        nullable=False,
    )
    amount = Column(Numeric(15, 2), nullable=False)
    currency = Column(String(3), nullable=False)
    detected_at = Column(DateTime(timezone=True), server_default=text("now()"))
    created_at = Column(DateTime(timezone=True), server_default=text("now()"))

    source_account = relationship("Account", foreign_keys=[source_account_id])
    pocket_account = relationship("Account", foreign_keys=[pocket_account_id])

    __table_args__ = (
        Index("idx_internal_transfers_user", "user_id"),
        Index("idx_internal_transfers_pocket", "pocket_account_id"),
    )


class RecurringTransaction(Base):
    """
    Recurring Transaction model matching Drizzle schema.
    Stores recurring transaction labels (subscriptions, bills, etc.) for automatic linking.
    """

    __tablename__ = "recurring_transactions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    account_id = Column(
        UUID(as_uuid=True),
        ForeignKey("accounts.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    name = Column(String(255), nullable=False)
    merchant = Column(String(255), nullable=True)
    amount = Column(
        Numeric(15, 2), nullable=False
    )  # estimated/typical amount when is_variable_amount
    is_variable_amount = Column(Boolean, nullable=False, default=False, server_default="false")
    currency = Column(String(3), default="EUR")
    category_id = Column(UUID(as_uuid=True), ForeignKey("categories.id"), nullable=True, index=True)
    logo_id = Column(
        UUID(as_uuid=True), ForeignKey("company_logos.id", ondelete="SET NULL"), nullable=True
    )
    importance = Column(Integer, nullable=False, default=3)  # 1-5 scale
    frequency = Column(String(20), nullable=False)  # monthly, weekly, yearly, quarterly, biweekly
    is_active = Column(Boolean, default=True)
    description = Column(Text, nullable=True)
    # Schedule fields: when set, `check_due_recurring_transactions` (Celery beat)
    # materializes a real Transaction on/after next_due_date and advances it.
    # Rows created by subscription_detector.py leave these null (label-only,
    # no auto-generation) to preserve pre-existing behavior.
    next_due_date = Column(Date, nullable=True, index=True)
    end_date = Column(Date, nullable=True)
    auto_generate = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime(timezone=True), default=_utcnow)
    updated_at = Column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)

    # Relationships
    user = relationship("User", back_populates="recurring_transactions")
    account = relationship("Account", back_populates="recurring_transactions")
    category = relationship("Category")
    logo = relationship("CompanyLogo", back_populates="recurring_transactions")
    linked_transactions = relationship("Transaction", back_populates="recurring_transaction")

    # Indexes and constraints
    __table_args__ = (
        Index("idx_recurring_transactions_user", "user_id"),
        Index("idx_recurring_transactions_account", "account_id"),
        Index("idx_recurring_transactions_category", "category_id"),
        Index("idx_recurring_transactions_active", "is_active"),
        Index("idx_recurring_transactions_next_due", "next_due_date"),
    )


class Budget(Base):
    """
    Budget model matching Drizzle schema.
    Stores a user-defined spending limit across one or more categories.
    """

    __tablename__ = "budgets"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(255), nullable=False)
    amount = Column(Numeric(15, 2), nullable=False)
    currency = Column(String(3), default="EUR")
    period = Column(String(20), nullable=False, default="monthly")  # monthly, weekly, yearly
    start_date = Column(Date, nullable=True)  # anchor for weekly/yearly period boundary math
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), default=_utcnow)
    updated_at = Column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)

    # Relationships
    user = relationship("User", back_populates="budgets")
    budget_categories = relationship(
        "BudgetCategory", back_populates="budget", cascade="all, delete-orphan"
    )

    # Indexes and constraints
    __table_args__ = (
        Index("idx_budgets_user", "user_id"),
        Index("idx_budgets_user_active", "user_id", "is_active"),
    )


class BudgetCategory(Base):
    __tablename__ = "budget_categories"

    budget_id = Column(
        UUID(as_uuid=True), ForeignKey("budgets.id", ondelete="CASCADE"), primary_key=True
    )
    category_id = Column(
        UUID(as_uuid=True), ForeignKey("categories.id", ondelete="CASCADE"), primary_key=True
    )
    sub_limit = Column(Numeric(15, 2), nullable=True)  # per-category cap within this budget
    created_at = Column(DateTime(timezone=True), default=_utcnow, nullable=False)

    # Relationships
    budget = relationship("Budget", back_populates="budget_categories")
    category = relationship("Category", back_populates="budget_categories")

    # Indexes and constraints
    __table_args__ = (Index("idx_budget_categories_category", "category_id"),)


class CategorizationRule(Base):
    """
    Categorization rules model matching Drizzle schema.
    Stores user-provided instructions for AI categorization.
    """

    __tablename__ = "categorization_rules"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    category_id = Column(
        UUID(as_uuid=True), ForeignKey("categories.id", ondelete="CASCADE"), nullable=False
    )
    instructions = Column(Text)  # User-provided instructions for AI categorization
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), default=_utcnow)

    # Relationships
    user = relationship("User", back_populates="categorization_rules")
    category = relationship("Category", back_populates="categorization_rules")


class CsvImport(Base):
    """
    CSV Import model matching Drizzle schema.
    Stores CSV import job information.
    """

    __tablename__ = "csv_imports"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    account_id = Column(
        UUID(as_uuid=True),
        ForeignKey("accounts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    file_name = Column(String(255), nullable=False)
    file_path = Column(Text, nullable=True)
    file_path_ciphertext = Column(Text, nullable=True)
    status = Column(
        String(20), default="pending"
    )  # pending, mapping, previewing, importing, completed, failed
    column_mapping = Column(JSONB, nullable=True)
    total_rows = Column(Integer, nullable=True)
    imported_rows = Column(Integer, nullable=True)
    duplicates_found = Column(Integer, nullable=True)
    error_message = Column(Text, nullable=True)
    # Background worker fields
    celery_task_id = Column(String(255), nullable=True)
    progress_count = Column(Integer, default=0)
    selected_indices = Column(JSONB, nullable=True)  # Array of row indices selected for import
    created_at = Column(DateTime(timezone=True), default=_utcnow)
    completed_at = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    user = relationship("User", back_populates="csv_imports")
    account = relationship("Account", back_populates="csv_imports")
    transactions = relationship("Transaction", back_populates="csv_import")

    # Indexes and constraints
    __table_args__ = (
        Index("idx_csv_imports_user", "user_id"),
        Index("idx_csv_imports_account", "account_id"),
    )


class ReceiptScan(Base):
    """
    Receipt scan job: an uploaded receipt photo OCR'd and split into
    one or more categorized Transaction rows. Processed synchronously
    (no Celery/background fields, unlike CsvImport).
    """

    __tablename__ = "receipt_scans"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    account_id = Column(
        UUID(as_uuid=True),
        ForeignKey("accounts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    file_path = Column(Text, nullable=True)
    file_path_ciphertext = Column(Text, nullable=True)
    status = Column(
        String(20), default="pending"
    )  # pending, processed, completed, failed, needs_review
    raw_ocr_text = Column(Text, nullable=True)
    merchant_name = Column(String(255), nullable=True)
    receipt_total = Column(Numeric(15, 2), nullable=True)
    receipt_date = Column(DateTime(timezone=True), nullable=True)
    error_message = Column(Text, nullable=True)
    # Receipt currency; may differ from the account's.
    currency = Column(String(3), nullable=True)
    # Replaces receipt_total; "printed" names the contract -- copied, not
    # computed. receipt_total is kept for one more release since the extract
    # and get routes still return it (schemas.py, dropped a release later).
    printed_total = Column(Numeric(15, 2), nullable=True)
    printed_discount_total = Column(Numeric(15, 2), nullable=True)
    merchant_legal_name = Column(String(255), nullable=True)
    merchant_address = Column(Text, nullable=True)
    receipt_no = Column(String(64), nullable=True)
    fiscal_code = Column(String(64), nullable=True)
    vat_id = Column(String(64), nullable=True)
    payment_method = Column(String(16), nullable=True)  # card | cash | other | unknown
    card_last4 = Column(String(4), nullable=True)
    # Extraction cache key (Part 6). Postgres gets a real CHAR(64); SQLite
    # (route tests) doesn't distinguish, so plain String is used here too.
    file_sha256 = Column(String(64), nullable=True)
    # Structured reconcile failures for the review UI. JSON on SQLite (route
    # tests run in-memory there), JSONB on Postgres -- see plan 2.1.
    validation_errors = Column(JSON().with_variant(JSONB, "postgresql"), nullable=True)
    extraction_model = Column(String(128), nullable=True)
    created_at = Column(DateTime(timezone=True), default=_utcnow)
    completed_at = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    user = relationship("User", back_populates="receipt_scans")
    account = relationship("Account", back_populates="receipt_scans")
    transactions = relationship("Transaction", back_populates="receipt_scan")
    line_items = relationship(
        "ReceiptLineItem",
        back_populates="receipt_scan",
        cascade="all, delete-orphan",
        order_by="ReceiptLineItem.position",
    )

    # Indexes and constraints
    __table_args__ = (
        Index("idx_receipt_scans_user", "user_id"),
        Index("idx_receipt_scans_account", "account_id"),
        Index(
            "idx_receipt_scans_sha256",
            "user_id",
            "file_sha256",
            postgresql_where=text("file_sha256 IS NOT NULL"),
        ),
    )


class ReceiptLineItem(Base):
    """
    One line of a receipt scan -- an item or a deposit -- resolved into a
    row so it can carry its own category, be edited, and be linked back to
    the booked Transaction it was grouped into.
    """

    __tablename__ = "receipt_line_items"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    receipt_scan_id = Column(
        UUID(as_uuid=True),
        ForeignKey("receipt_scans.id", ondelete="CASCADE"),
        nullable=False,
    )
    # The model's own "L1", "L2", ... reference for this scan. Unique per
    # scan, which is what makes parent_line_ref resolvable.
    line_ref = Column(String(8), nullable=False)
    position = Column(Integer, nullable=False)
    raw_text = Column(Text, nullable=True)
    name = Column(Text, nullable=True)
    quantity = Column(Numeric(12, 3), nullable=True)
    gross_amount = Column(Numeric(15, 2), nullable=True)
    discount_amount = Column(Numeric(15, 2), nullable=True, default=0)
    net_amount = Column(Numeric(15, 2), nullable=True)
    kind = Column(String(16), nullable=False, default="item")  # item | deposit
    # References a sibling's line_ref within the same scan, not `id` -- the
    # model emits "L3" before any row has an id, and a self-FK would force a
    # two-pass insert to buy nothing (plan 2.3).
    parent_line_ref = Column(String(8), nullable=True)
    # No ON DELETE clause, matching Transaction.category_id -- deleting a
    # category with receipt lines attached raises rather than silently
    # nulling them.
    category_id = Column(UUID(as_uuid=True), ForeignKey("categories.id"), nullable=True)
    category_confidence = Column(String(8), nullable=True)  # high | medium | low
    category_reason = Column(Text, nullable=True)
    user_edited = Column(Boolean, nullable=False, default=False)
    booked_transaction_id = Column(
        UUID(as_uuid=True),
        ForeignKey("transactions.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at = Column(DateTime(timezone=True), default=_utcnow)
    updated_at = Column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)

    # Relationships
    receipt_scan = relationship("ReceiptScan", back_populates="line_items")
    category = relationship("Category", back_populates="receipt_line_items")
    booked_transaction = relationship("Transaction", back_populates="receipt_line_items")

    __table_args__ = (
        UniqueConstraint("receipt_scan_id", "line_ref", name="receipt_line_items_scan_ref_uq"),
        Index("idx_receipt_line_items_scan", "receipt_scan_id"),
        Index("idx_receipt_line_items_txn", "booked_transaction_id"),
    )


class ExchangeRate(Base):
    """
    Exchange rate model for currency conversion.
    Stores daily exchange rates between base currencies and target currencies (EUR, USD).
    """

    __tablename__ = "exchange_rates"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    date = Column(DateTime(timezone=True), nullable=False, index=True)  # Date of the exchange rate
    base_currency = Column(
        String(3), nullable=False, index=True
    )  # Source currency (transaction currency)
    target_currency = Column(String(3), nullable=False, index=True)  # Target currency (EUR or USD)
    rate = Column(
        Numeric(18, 8), nullable=False
    )  # Exchange rate (how many target currency = 1 base currency)
    created_at = Column(DateTime(timezone=True), default=_utcnow)
    updated_at = Column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)

    # Indexes and constraints
    __table_args__ = (
        Index("idx_exchange_rates_date", "date"),
        Index("idx_exchange_rates_base", "base_currency"),
        Index("idx_exchange_rates_target", "target_currency"),
        UniqueConstraint(
            "date", "base_currency", "target_currency", name="exchange_rates_date_base_target"
        ),
    )


class AccountBalance(Base):
    """
    Account balance model for daily balance snapshots.
    Stores daily balance for each account in both account currency and functional currency.
    """

    __tablename__ = "account_balances"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    account_id = Column(
        UUID(as_uuid=True),
        ForeignKey("accounts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    date = Column(
        DateTime(timezone=True), nullable=False, index=True
    )  # Date of the balance snapshot
    balance_in_account_currency = Column(
        Numeric(15, 2), nullable=False
    )  # Balance in account's currency
    balance_in_functional_currency = Column(
        Numeric(15, 2), nullable=False
    )  # Balance converted to functional currency
    created_at = Column(DateTime(timezone=True), default=_utcnow)
    updated_at = Column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)

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
    created_at = Column(DateTime(timezone=True), default=_utcnow)
    updated_at = Column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)

    # Relationships
    user = relationship("User", back_populates="properties")

    # Indexes and constraints
    __table_args__ = (Index("idx_properties_user", "user_id"),)


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
    created_at = Column(DateTime(timezone=True), default=_utcnow)
    updated_at = Column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)

    # Relationships
    user = relationship("User", back_populates="vehicles")

    # Indexes and constraints
    __table_args__ = (Index("idx_vehicles_user", "user_id"),)


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
    is_variable_amount = Column(Boolean, nullable=False, default=False, server_default="false")
    currency = Column(String(3), default="EUR", nullable=False)
    detected_frequency = Column(
        String(20), nullable=False
    )  # weekly, biweekly, monthly, quarterly, yearly
    confidence = Column(Integer, nullable=False)  # 0-100
    account_id = Column(
        UUID(as_uuid=True),
        ForeignKey("accounts.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    suggested_category_id = Column(
        UUID(as_uuid=True),
        ForeignKey("categories.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # Linked transactions (stored as JSON array of IDs)
    matched_transaction_ids = Column(Text, nullable=False)  # JSON array

    # Status
    status = Column(String(20), default="pending", nullable=False)  # pending, approved, dismissed

    # Timestamps
    created_at = Column(DateTime(timezone=True), default=_utcnow, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False)

    # Relationships
    user = relationship("User", back_populates="subscription_suggestions")
    account = relationship("Account", back_populates="subscription_suggestions")
    suggested_category = relationship("Category", back_populates="subscription_suggestions")

    # Indexes
    __table_args__ = (
        Index("idx_subscription_suggestions_user", "user_id"),
        Index("idx_subscription_suggestions_status", "status"),
        Index("idx_subscription_suggestions_account", "account_id"),
        Index("idx_subscription_suggestions_category", "suggested_category_id"),
    )


class TransactionLink(Base):
    """
    Transaction link model matching Drizzle schema.
    Links transactions together for reimbursement/expense tracking.
    """

    __tablename__ = "transaction_links"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    group_id = Column(
        UUID(as_uuid=True), nullable=False, index=True
    )  # Groups linked transactions together
    transaction_id = Column(
        UUID(as_uuid=True), ForeignKey("transactions.id", ondelete="CASCADE"), nullable=False
    )
    link_role = Column(String(20), nullable=False)  # "primary" | "reimbursement" | "expense"
    created_at = Column(DateTime(timezone=True), default=_utcnow)

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
    last_checked_at = Column(DateTime(timezone=True), default=_utcnow)
    created_at = Column(DateTime(timezone=True), default=_utcnow)
    updated_at = Column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)

    # Relationships
    accounts = relationship("Account", back_populates="logo")
    recurring_transactions = relationship("RecurringTransaction", back_populates="logo")
    transactions = relationship("Transaction", back_populates="logo")

    # Indexes and constraints
    __table_args__ = (
        Index("idx_company_logos_domain", "domain"),
        Index("idx_company_logos_name", "company_name"),
        UniqueConstraint("domain", name="company_logos_domain_unique"),
    )


class MerchantAlias(Base):
    """
    Maps a raw merchant/description pattern to a canonical merchant name plus
    optional default category and logo domain hints. Seeded from
    MerchantExtractor.KNOWN_MERCHANTS (see postgres_migration/add_merchant_aliases_table.py)
    and consulted by MerchantExtractor/CategoryMatcher during ingestion so
    that merchant variants collapse to one consistent name/category/logo.
    """

    __tablename__ = "merchant_aliases"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    pattern = Column(String(255), nullable=False)  # lowercase match key, e.g. "netflix"
    canonical_name = Column(String(255), nullable=False)  # e.g. "Netflix"
    category_id = Column(
        UUID(as_uuid=True), ForeignKey("categories.id", ondelete="SET NULL"), nullable=True
    )
    logo_domain = Column(String(255), nullable=True)  # e.g. "netflix.com"
    created_at = Column(DateTime(timezone=True), default=_utcnow)
    updated_at = Column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)

    category = relationship("Category")

    __table_args__ = (
        Index("idx_merchant_aliases_pattern", "pattern"),
        UniqueConstraint("pattern", name="merchant_aliases_pattern_unique"),
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
    value = Column(String, nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    created_at = Column(DateTime(timezone=True), default=_utcnow)
    updated_at = Column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)


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
    expires_at = Column(DateTime(timezone=True), nullable=False)
    ip_address = Column(Text, nullable=True)
    user_agent = Column(Text, nullable=True)
    impersonated_by = Column(Text, nullable=True)  # better-auth admin plugin: impersonation
    created_at = Column(DateTime(timezone=True), default=_utcnow)
    updated_at = Column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)

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
    access_token_expires_at = Column(DateTime(timezone=True), nullable=True)
    refresh_token_expires_at = Column(DateTime(timezone=True), nullable=True)
    scope = Column(Text, nullable=True)
    id_token = Column(Text, nullable=True)
    password = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=_utcnow)
    updated_at = Column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)

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
    role = Column(Text, nullable=True)  # better-auth admin plugin: "admin" or "user"
    banned = Column(Boolean, default=False)  # better-auth admin plugin
    ban_reason = Column(Text, nullable=True)
    ban_expires = Column(DateTime(timezone=True), nullable=True)
    hide_balances = Column(Boolean, default=False)  # Mask balance amounts across the app
    tutorials_enabled = Column(Boolean, default=True)  # Show page tours/onboarding tips
    onboarding_status = Column(
        String(20), default="pending"
    )  # pending, step_1, step_2, step_3, completed
    onboarding_completed_at = Column(DateTime(timezone=True), nullable=True)
    functional_currency = Column(
        String(3), default="EUR"
    )  # User's functional currency for reporting
    profile_photo_path = Column(Text, nullable=True)
    # Drizzle declares this with a foreign key to accounts.id; it is mapped
    # here as a plain column so that users and accounts do not become a
    # mutually dependent pair in Base.metadata, which SQLAlchemy cannot sort.
    default_account_id = Column(UUID(as_uuid=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=_utcnow)
    updated_at = Column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)

    # Relationships
    sessions = relationship("Session", back_populates="user", cascade="all, delete-orphan")
    auth_accounts = relationship("AuthAccount", back_populates="user", cascade="all, delete-orphan")
    accounts = relationship("Account", back_populates="user", cascade="all, delete-orphan")
    categories = relationship("Category", back_populates="user", cascade="all, delete-orphan")
    transactions = relationship("Transaction", back_populates="user", cascade="all, delete-orphan")
    recurring_transactions = relationship(
        "RecurringTransaction", back_populates="user", cascade="all, delete-orphan"
    )
    categorization_rules = relationship(
        "CategorizationRule", back_populates="user", cascade="all, delete-orphan"
    )
    csv_imports = relationship("CsvImport", back_populates="user", cascade="all, delete-orphan")
    receipt_scans = relationship("ReceiptScan", back_populates="user", cascade="all, delete-orphan")
    properties = relationship("Property", back_populates="user", cascade="all, delete-orphan")
    vehicles = relationship("Vehicle", back_populates="user", cascade="all, delete-orphan")
    subscription_suggestions = relationship(
        "SubscriptionSuggestion", back_populates="user", cascade="all, delete-orphan"
    )
    api_keys = relationship("ApiKey", back_populates="user", cascade="all, delete-orphan")
    transaction_links = relationship(
        "TransactionLink", back_populates="user", cascade="all, delete-orphan"
    )
    bank_connections = relationship(
        "BankConnection", back_populates="user", cascade="all, delete-orphan"
    )
    budgets = relationship("Budget", back_populates="user", cascade="all, delete-orphan")


class ApiKey(Base):
    """
    API Key model for MCP server authentication.
    Stores hashed API keys for secure authentication.
    """

    __tablename__ = "api_keys"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(255), nullable=False)
    key_hash = Column(
        String(128), nullable=False, index=True
    )  # Supports bcrypt (60 chars) and SHA-256 (64 chars)
    key_prefix = Column(String(12), nullable=False)
    last_used_at = Column(DateTime(timezone=True), nullable=True)
    expires_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=_utcnow)

    # Relationships
    user = relationship("User", back_populates="api_keys")

    # Indexes
    __table_args__ = (
        Index("idx_api_keys_user", "user_id"),
        Index("idx_api_keys_hash", "key_hash"),
        Index("idx_api_keys_prefix", "key_prefix"),
    )


class AppSetting(Base):
    """
    Global application setting.
    Secret values are stored encrypted in value_encrypted.
    """

    __tablename__ = "app_settings"

    key = Column(String(255), primary_key=True)
    value_encrypted = Column(Text, nullable=True)
    updated_by_user_id = Column(String, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), default=_utcnow)
    updated_at = Column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)


class Holding(Base):
    __tablename__ = "holdings"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    account_id = Column(
        UUID(as_uuid=True), ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False
    )
    symbol = Column(String(64), nullable=False)
    provider_symbol = Column(String(64), nullable=True)
    name = Column(String(255))
    currency = Column(String(3), nullable=False)
    instrument_type = Column(String(20), nullable=False)
    quantity = Column(Numeric(28, 8), nullable=False)
    avg_cost = Column(Numeric(28, 8), nullable=True)
    as_of_date = Column(Date, nullable=True)
    source = Column(String(20), nullable=False)
    last_price_error = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=_utcnow)
    updated_at = Column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)

    valuations = relationship(
        "HoldingValuation", back_populates="holding", cascade="all, delete-orphan"
    )

    __table_args__ = (
        UniqueConstraint(
            "account_id", "symbol", "instrument_type", name="holdings_account_symbol_type_uq"
        ),
        Index("idx_holdings_account", "account_id"),
    )


class BrokerTrade(Base):
    """One buy/sell trade row. Populated for manual holdings by the
    investments buy/sell routes; reserved for broker-import trade history
    on synced accounts (unused today)."""

    __tablename__ = "broker_trades"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    account_id = Column(
        UUID(as_uuid=True), ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False
    )
    symbol = Column(String(64), nullable=False)
    trade_date = Column(Date, nullable=False)
    side = Column(String(10), nullable=False)
    quantity = Column(Numeric(28, 8), nullable=False)
    price = Column(Numeric(28, 8), nullable=False)
    fees = Column(Numeric(28, 8), nullable=False, server_default="0", default=0)
    currency = Column(String(3), nullable=False)
    external_id = Column(String(255), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)

    __table_args__ = (
        UniqueConstraint("account_id", "external_id", name="broker_trades_account_external_uq"),
    )


class PriceSnapshot(Base):
    __tablename__ = "price_snapshots"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    symbol = Column(String(64), nullable=False)
    currency = Column(String(3), nullable=False)
    date = Column(Date, nullable=False)
    close = Column(Numeric(28, 8), nullable=False)
    provider = Column(String(20), nullable=False)

    __table_args__ = (UniqueConstraint("symbol", "date", name="price_snapshots_symbol_date_uq"),)


class HoldingValuation(Base):
    __tablename__ = "holding_valuations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    holding_id = Column(
        UUID(as_uuid=True), ForeignKey("holdings.id", ondelete="CASCADE"), nullable=False
    )
    date = Column(Date, nullable=False)
    quantity = Column(Numeric(28, 8), nullable=False)
    price = Column(Numeric(28, 8), nullable=False)
    value_user_currency = Column(Numeric(15, 2), nullable=False)
    is_stale = Column(Boolean, default=False)

    holding = relationship("Holding", back_populates="valuations")

    __table_args__ = (
        UniqueConstraint("holding_id", "date", name="holding_valuations_holding_date_uq"),
    )


class Person(Base):
    __tablename__ = "people"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(Text, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(255), nullable=False)
    kind = Column(String(20), nullable=False, default="member")
    color = Column(String(7), nullable=True)
    avatar_path = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=_utcnow, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False)

    user = relationship("User", backref="people")

    __table_args__ = (Index("idx_people_user", "user_id"),)


class AccountOwner(Base):
    __tablename__ = "account_owners"

    account_id = Column(
        UUID(as_uuid=True), ForeignKey("accounts.id", ondelete="CASCADE"), primary_key=True
    )
    person_id = Column(
        UUID(as_uuid=True), ForeignKey("people.id", ondelete="CASCADE"), primary_key=True
    )
    share = Column(Numeric(5, 4), nullable=True)
    created_at = Column(DateTime(timezone=True), default=_utcnow, nullable=False)


class PropertyOwner(Base):
    __tablename__ = "property_owners"

    property_id = Column(
        UUID(as_uuid=True), ForeignKey("properties.id", ondelete="CASCADE"), primary_key=True
    )
    person_id = Column(
        UUID(as_uuid=True), ForeignKey("people.id", ondelete="CASCADE"), primary_key=True
    )
    share = Column(Numeric(5, 4), nullable=True)
    created_at = Column(DateTime(timezone=True), default=_utcnow, nullable=False)


class VehicleOwner(Base):
    __tablename__ = "vehicle_owners"

    vehicle_id = Column(
        UUID(as_uuid=True), ForeignKey("vehicles.id", ondelete="CASCADE"), primary_key=True
    )
    person_id = Column(
        UUID(as_uuid=True), ForeignKey("people.id", ondelete="CASCADE"), primary_key=True
    )
    share = Column(Numeric(5, 4), nullable=True)
    created_at = Column(DateTime(timezone=True), default=_utcnow, nullable=False)


class MCPIdempotencyKey(Base):
    """A remembered MCP write, so a retry does not create a second one.

    An agent that loses the response to `create_budget` has no way to tell a
    call that failed from one that succeeded and went unheard, and the
    reasonable thing for it to do -- retry -- is exactly what produces the
    duplicate. The key lets it retry safely: the same key with the same
    arguments replays the stored response instead of writing again.

    `request_hash` is what makes that safe rather than merely quiet. The same
    key arriving with *different* arguments is a client bug, and returning
    either the old response or a new write would hide it, so it is rejected
    instead.

    Rows are swept after 24h by
    tasks.mcp_idempotency_tasks.prune_mcp_idempotency_keys -- long enough to
    cover any plausible retry, short enough that the table stays small.
    """

    __tablename__ = "mcp_idempotency_keys"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    tool_name = Column(String(100), nullable=False)
    idempotency_key = Column(String(255), nullable=False)
    request_hash = Column(String(64), nullable=False)
    response = Column(JSONB, nullable=False)
    created_at = Column(DateTime(timezone=True), default=_utcnow, nullable=False, index=True)

    __table_args__ = (
        UniqueConstraint("user_id", "tool_name", "idempotency_key", name="mcp_idempotency_unique"),
    )
