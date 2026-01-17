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
    is_system = Column(Boolean, default=False)
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
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    user = relationship("User", back_populates="transactions")
    account = relationship("Account", back_populates="transactions")
    category = relationship("Category", foreign_keys=[category_id], back_populates="transactions")
    category_system = relationship("Category", foreign_keys=[category_system_id], back_populates="system_transactions")

    # Indexes and constraints
    __table_args__ = (
        Index("idx_transactions_user", "user_id"),
        Index("idx_transactions_account", "account_id"),
        Index("idx_transactions_booked_at", "booked_at"),
        Index("idx_transactions_category", "category_id"),
        Index("idx_transactions_category_system", "category_system_id"),
        UniqueConstraint("account_id", "external_id", name="transactions_account_external_id"),
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
    Stores GoCardless/Nordigen bank connection information.
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
    created_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime, nullable=True)

    # Relationships
    user = relationship("User", back_populates="bank_connections")


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


# ============================================================================
# BetterAuth Tables (minimal models for foreign key relationships)
# ============================================================================

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
    functional_currency = Column(String(3), default="EUR")  # User's functional currency for reporting
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    accounts = relationship("Account", back_populates="user", cascade="all, delete-orphan")
    categories = relationship("Category", back_populates="user", cascade="all, delete-orphan")
    transactions = relationship("Transaction", back_populates="user", cascade="all, delete-orphan")
    categorization_rules = relationship("CategorizationRule", back_populates="user", cascade="all, delete-orphan")
    bank_connections = relationship("BankConnection", back_populates="user", cascade="all, delete-orphan")
