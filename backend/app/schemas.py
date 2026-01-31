from pydantic import BaseModel, ConfigDict
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


class AccountResponse(AccountBase):
    id: UUID
    is_active: bool
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