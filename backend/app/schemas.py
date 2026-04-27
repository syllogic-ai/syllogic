from pydantic import BaseModel, ConfigDict, Field
from datetime import datetime
from decimal import Decimal
from typing import Optional, List
from uuid import UUID


# Account Schemas
class AccountBase(BaseModel):
    name: str
    account_type: str
    institution: Optional[str] = None
    currency: str = "EUR"


class AccountCreate(AccountBase):
    pass


class AccountUpdate(BaseModel):
    name: Optional[str] = None
    institution: Optional[str] = None
    balance_current: Optional[Decimal] = None
    is_active: Optional[bool] = None
    alias_patterns: list[str] = Field(default_factory=list)


class AccountResponse(AccountBase):
    id: UUID
    is_active: bool
    alias_patterns: list[str] = Field(default_factory=list)
    provider: Optional[str] = None
    external_id: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


# Category Schemas
class CategoryBase(BaseModel):
    name: str
    parent_id: Optional[UUID] = None
    category_type: str = "expense"
    color: Optional[str] = None
    icon: Optional[str] = None


class CategoryCreate(CategoryBase):
    pass


class CategoryUpdate(BaseModel):
    name: Optional[str] = None
    parent_id: Optional[UUID] = None
    color: Optional[str] = None
    icon: Optional[str] = None


class CategoryResponse(CategoryBase):
    id: UUID
    is_system: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# Transaction Schemas
class TransactionBase(BaseModel):
    account_id: UUID
    transaction_type: str  # debit, credit
    amount: Decimal
    currency: str = "EUR"
    description: str
    merchant: Optional[str] = None
    booked_at: datetime


class TransactionCreate(TransactionBase):
    category_id: Optional[UUID] = None
    category_system_id: Optional[UUID] = None
    categorization_instructions: Optional[str] = None


class TransactionUpdate(BaseModel):
    description: Optional[str] = None
    merchant: Optional[str] = None
    category_id: Optional[UUID] = None
    category_system_id: Optional[UUID] = None
    categorization_instructions: Optional[str] = None
    enrichment_data: Optional[dict] = None


class CategoryAssign(BaseModel):
    category_id: UUID


class TransactionResponse(TransactionBase):
    id: UUID
    external_id: Optional[str] = None
    category_id: Optional[UUID] = None
    category_system_id: Optional[UUID] = None
    pending: bool
    categorization_instructions: Optional[str] = None
    enrichment_data: Optional[dict] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class TransactionWithDetails(TransactionResponse):
    category_name: Optional[str] = None
    account_name: str


# Analytics Schemas
class CategorySpending(BaseModel):
    category_id: Optional[UUID]
    category_name: Optional[str]
    total: Decimal
    count: int


class AccountSummary(BaseModel):
    id: UUID
    name: str
    account_type: str
    balance: Decimal


# Transaction Input/Output Schemas
class TransactionInput(BaseModel):
    """Input transaction for categorization."""
    description: Optional[str] = None
    merchant: Optional[str] = None
    amount: Decimal
    transaction_type: Optional[str] = None  # "debit" or "credit" - helps determine if expense or income


class TransactionResult(BaseModel):
    """Result of categorization for a single transaction."""
    description: Optional[str]
    merchant: Optional[str]
    amount: Decimal
    category_name: Optional[str] = None
    category_id: Optional[UUID] = None
    method: str  # 'override', 'deterministic', 'llm', or 'none'
    confidence_score: Optional[float] = None
    matched_keywords: Optional[List[str]] = None
    tokens_used: Optional[int] = None
    cost_usd: Optional[float] = None


class UserOverride(BaseModel):
    """User override for a specific transaction pattern."""
    description: Optional[str] = None
    merchant: Optional[str] = None
    amount: Optional[Decimal] = None
    category_name: str  # Required: the category to use for matching transactions


class BatchCategorizationRequest(BaseModel):
    """Request for batch categorization."""
    transactions: List[TransactionInput]
    use_llm: bool = True
    user_overrides: Optional[List[UserOverride]] = None  # User-defined category overrides
    additional_instructions: Optional[List[str]] = None  # User guidance for categorization


class BatchCategorizationResponse(BaseModel):
    """Response for batch categorization."""
    results: List[TransactionResult]
    total_transactions: int
    categorized_count: int
    deterministic_count: int
    llm_count: int
    uncategorized_count: int
    total_tokens_used: int
    total_cost_usd: float
    llm_errors: Optional[List[str]] = None  # List of LLM error messages
    llm_warnings: Optional[List[str]] = None  # List of LLM warning messages


# Production categorization schemas
class CategorizeTransactionRequest(BaseModel):
    """Request to categorize a single transaction."""
    description: Optional[str] = None
    merchant: Optional[str] = None
    amount: Decimal
    transaction_type: Optional[str] = None  # 'debit' or 'credit'
    use_llm: bool = True
    user_overrides: Optional[List[UserOverride]] = None  # User-defined category overrides
    additional_instructions: Optional[List[str]] = None  # User guidance for categorization


class CategorizeTransactionResponse(BaseModel):
    """Response for single transaction categorization."""
    category_id: Optional[UUID] = None
    category_name: Optional[str] = None
    method: str  # 'override', 'deterministic', 'llm', or 'none'
    confidence_score: Optional[float] = None
    matched_keywords: Optional[List[str]] = None
    tokens_used: Optional[int] = None
    cost_usd: Optional[float] = None


class BatchCategorizeRequest(BaseModel):
    """Request to categorize multiple transactions."""
    transactions: List[TransactionInput]
    use_llm: bool = True
    user_overrides: Optional[List[UserOverride]] = None  # User-defined category overrides (applies to all transactions)
    additional_instructions: Optional[List[str]] = None  # User guidance for categorization (applies to all transactions)


class BatchCategorizeResponse(BaseModel):
    """Response for batch transaction categorization."""
    results: List[TransactionResult]
    total_transactions: int
    categorized_count: int
    deterministic_count: int
    llm_count: int
    uncategorized_count: int
    total_tokens_used: int
    total_cost_usd: float
    llm_errors: Optional[List[str]] = None
    llm_warnings: Optional[List[str]] = None


# Daily Balance Import Schemas
class DailyBalanceImport(BaseModel):
    """Daily balance data extracted from CSV for import."""
    date: str  # ISO date format YYYY-MM-DD
    balance: Decimal


# Investment Schemas
from datetime import date as _date_date
from typing import Literal


class BrokerConnectionCreate(BaseModel):
    provider: Literal["ibkr_flex"]
    flex_token: str
    query_id_positions: str
    query_id_trades: str
    account_name: str
    base_currency: str = "EUR"


class BrokerConnectionResponse(BaseModel):
    id: UUID
    account_id: UUID
    provider: str
    last_sync_at: Optional[datetime]
    last_sync_status: Optional[str]
    last_sync_error: Optional[str]


class ManualAccountCreate(BaseModel):
    name: str
    base_currency: str = "EUR"


class HoldingCreate(BaseModel):
    symbol: str
    provider_symbol: Optional[str] = None
    quantity: Decimal
    instrument_type: Literal["equity", "etf", "cash"]
    currency: str
    as_of_date: Optional[_date_date] = None
    avg_cost: Optional[Decimal] = None


class HoldingUpdate(BaseModel):
    symbol: Optional[str] = None
    quantity: Optional[Decimal] = None
    as_of_date: Optional[_date_date] = None
    avg_cost: Optional[Decimal] = None
    provider_symbol: Optional[str] = None


class HoldingResponse(BaseModel):
    id: UUID
    account_id: UUID
    symbol: str
    provider_symbol: Optional[str] = None
    name: Optional[str]
    currency: str
    instrument_type: str
    quantity: Decimal
    avg_cost: Optional[Decimal]
    as_of_date: Optional[_date_date]
    source: str
    current_price: Optional[Decimal] = None
    current_value_user_currency: Optional[Decimal] = None
    cost_basis_user_currency: Optional[Decimal] = None
    is_stale: bool = False


class PortfolioSummary(BaseModel):
    total_value: Decimal
    total_value_today_change: Decimal
    currency: str
    accounts: list[dict]
    allocation_by_type: dict[str, Decimal]
    allocation_by_currency: dict[str, Decimal]


class ValuationPoint(BaseModel):
    date: _date_date
    value: Decimal


class HoldingTrade(BaseModel):
    """One BrokerTrade row enriched with running quantity / cost."""
    id: UUID
    trade_date: _date_date
    symbol: str
    side: str
    quantity: Decimal
    price: Decimal
    currency: str
    fees: Decimal
    external_id: Optional[str] = None
    cost_native: Optional[Decimal] = None
    proceeds_native: Optional[Decimal] = None
    running_quantity: Decimal


class HoldingLot(BaseModel):
    """One open FIFO lot for a holding."""
    open_date: _date_date
    quantity_remaining: Decimal
    cost_per_share_native: Decimal
    cost_per_share_user: Optional[Decimal] = None
    age_days: int
    currency: str


class SymbolSearchResult(BaseModel):
    symbol: str
    name: str
    exchange: Optional[str] = None
    currency: Optional[str] = None