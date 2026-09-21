import re
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from datetime import datetime
from datetime import time as _time_type
from decimal import Decimal
from typing import Optional, List, Literal
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


# Account Schemas
class AccountBase(BaseModel):
    name: str
    account_type: str
    institution: Optional[str] = None
    currency: str = "EUR"
    credit_limit: Optional[Decimal] = None


class AccountCreate(AccountBase):
    provider: Optional[str] = None
    starting_balance: Optional[Decimal] = None


class AccountUpdate(BaseModel):
    name: Optional[str] = None
    account_type: Optional[str] = None
    institution: Optional[str] = None
    currency: Optional[str] = None
    starting_balance: Optional[Decimal] = None
    functional_balance: Optional[Decimal] = None
    credit_limit: Optional[Decimal] = None
    logo_id: Optional[UUID] = None
    is_active: Optional[bool] = None
    alias_patterns: list[str] = Field(default_factory=list)


class AccountLogoSchema(BaseModel):
    id: UUID
    logo_url: Optional[str] = None
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class AccountResponse(AccountBase):
    id: UUID
    is_active: bool
    alias_patterns: list[str] = Field(default_factory=list)
    provider: Optional[str] = None
    external_id: Optional[str] = None
    logo_id: Optional[UUID] = None
    logo: Optional[AccountLogoSchema] = None
    starting_balance: Decimal = Decimal("0")
    functional_balance: Optional[Decimal] = None
    balance_is_anchored: bool = False
    last_synced_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class RecalculateBalancesFromDateRequest(BaseModel):
    from_date: datetime
    starting_balance: Decimal
    exclude_transaction_id: Optional[UUID] = None


class AccountLogoSetRequest(BaseModel):
    logo_id: UUID


class AccountLogoResponse(BaseModel):
    logo_id: Optional[UUID] = None
    logo: Optional[AccountLogoSchema] = None


class AccountLogoSetResponse(AccountLogoResponse):
    applied: bool


class TransactionLogoSetRequest(BaseModel):
    logo_id: UUID


class TransactionLogoSetResponse(BaseModel):
    applied: bool
    logo_id: Optional[UUID] = None
    logo: Optional[AccountLogoSchema] = None


class AccountHardDeleteResponse(BaseModel):
    deleted_balances: int
    deleted_transactions: int


class AccountBalancePointResponse(BaseModel):
    date: datetime
    balance_in_account_currency: Decimal
    balance_in_functional_currency: Decimal


class DailyTransactionChangeResponse(BaseModel):
    date: str
    amount: Decimal


class TransactionSumResponse(BaseModel):
    total: Decimal


class EarliestTransactionDateResponse(BaseModel):
    date: Optional[datetime] = None


# Category Schemas
class CategoryBase(BaseModel):
    name: str
    parent_id: Optional[UUID] = None
    category_type: str = "expense"
    color: Optional[str] = None
    icon: Optional[str] = None
    description: Optional[str] = None
    categorization_instructions: Optional[str] = None
    hide_from_selection: bool = False
    system_key: Optional[str] = None


class CategoryCreate(CategoryBase):
    pass


class CategoryUpdate(BaseModel):
    name: Optional[str] = None
    parent_id: Optional[UUID] = None
    category_type: Optional[str] = None
    color: Optional[str] = None
    icon: Optional[str] = None
    description: Optional[str] = None
    categorization_instructions: Optional[str] = None
    hide_from_selection: Optional[bool] = None


class CategoryDeleteRequest(BaseModel):
    reassign_to_category_id: Optional[UUID] = None


class CategoryDeleteResponse(BaseModel):
    reassigned_count: int
    ungrouped_count: int = 0


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
    # Presence of any of these four triggers the "full mutation" path in
    # update_transaction (amount/account/date/type change together with a
    # currency + balance recalc), as opposed to a plain field patch.
    account_id: Optional[UUID] = None
    amount: Optional[Decimal] = None
    transaction_type: Optional[str] = None
    booked_at: Optional[datetime] = None


class CategoryAssign(BaseModel):
    category_id: UUID


class TransactionResponse(TransactionBase):
    id: UUID
    external_id: Optional[str] = None
    category_id: Optional[UUID] = None
    category_system_id: Optional[UUID] = None
    functional_amount: Optional[Decimal] = None
    creditor: Optional[str] = None
    debtor: Optional[str] = None
    internal_transfer_id: Optional[UUID] = None
    recurring_transaction_id: Optional[UUID] = None
    include_in_analytics: bool = True
    auto_generated: bool = False
    csv_import_id: Optional[UUID] = None
    pending: bool
    categorization_instructions: Optional[str] = None
    enrichment_data: Optional[dict] = None
    logo_id: Optional[UUID] = None
    logo: Optional[AccountLogoSchema] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class RecurringTransactionSummary(BaseModel):
    id: UUID
    name: str
    merchant: Optional[str] = None
    frequency: str
    logo_id: Optional[UUID] = None
    logo: Optional[AccountLogoSchema] = None

    model_config = ConfigDict(from_attributes=True)


class TransactionLinkSummary(BaseModel):
    id: UUID
    group_id: UUID
    link_role: str

    model_config = ConfigDict(from_attributes=True)


class TransferAccountSummary(BaseModel):
    id: UUID
    name: str

    model_config = ConfigDict(from_attributes=True)


class InternalTransferSummary(BaseModel):
    id: UUID
    source_txn_id: UUID
    mirror_txn_id: Optional[UUID] = None
    source_account_id: UUID
    pocket_account_id: UUID
    amount: Decimal
    currency: str
    source_account: Optional[TransferAccountSummary] = None
    pocket_account: Optional[TransferAccountSummary] = None

    model_config = ConfigDict(from_attributes=True)


class TransactionAccountSummary(BaseModel):
    id: UUID
    name: str
    institution: Optional[str] = None
    account_type: str
    logo_id: Optional[UUID] = None
    logo: Optional[AccountLogoSchema] = None

    model_config = ConfigDict(from_attributes=True)


class TransactionWithDetails(TransactionResponse):
    category_name: Optional[str] = None
    account_name: str
    account: Optional[TransactionAccountSummary] = None
    category: Optional[CategoryResponse] = None
    category_system: Optional[CategoryResponse] = None
    recurring_transaction: Optional[RecurringTransactionSummary] = None
    transaction_link: Optional[TransactionLinkSummary] = None
    internal_transfer: Optional[InternalTransferSummary] = None


# Transfer / interest / balancing / delete-impact schemas
class TransferTransactionCreate(BaseModel):
    source_account_id: UUID
    destination_account_id: UUID
    amount: Decimal
    description: str
    booked_at: datetime


class TransferTransactionResponse(BaseModel):
    source_transaction_id: UUID
    destination_transaction_id: UUID


class TransactionConvertToTransferRequest(BaseModel):
    source_account_id: UUID
    destination_account_id: UUID
    amount: Decimal
    description: str
    booked_at: datetime


class CreditCardRepaymentSource(BaseModel):
    source_account_id: UUID
    amount: Decimal


class CreditCardRepaymentCreate(BaseModel):
    credit_card_account_id: UUID
    sources: List[CreditCardRepaymentSource]
    description: str
    booked_at: datetime


class CreditCardRepaymentResponse(BaseModel):
    transfers: List[TransferTransactionResponse]


class InterestTransactionCreate(BaseModel):
    account_id: UUID
    amount: Decimal
    booked_at: datetime
    description: Optional[str] = None


class InterestTransactionResponse(BaseModel):
    transaction_id: UUID


class AccruedInterestResponse(BaseModel):
    total: Decimal


class BalancingTransactionUpsert(BaseModel):
    account_id: UUID
    target_balance: Decimal
    adjustment_date: datetime
    balancing_category_id: UUID


class BalancingTransactionUpsertResponse(BaseModel):
    transaction_id: Optional[UUID] = None
    is_update: bool = False


class AccountDeleteImpact(BaseModel):
    account_id: UUID
    account_name: str
    currency: str
    amount_change: Decimal
    current_balance: Decimal
    projected_balance: Decimal
    balance_is_anchored: bool


class DeleteImpactRequest(BaseModel):
    transaction_ids: List[UUID]


class DeleteImpactResponse(BaseModel):
    account_impacts: List[AccountDeleteImpact]
    total_transactions: int
    earliest_date: datetime


class BulkDeleteRequest(BaseModel):
    transaction_ids: List[UUID]


class BulkDeleteResponse(BaseModel):
    affected_account_ids: List[UUID]
    deleted_count: int


class FilteredTransactionTotalsResponse(BaseModel):
    total_in: Decimal
    total_out: Decimal


class TransactionPageResponse(BaseModel):
    rows: List[TransactionWithDetails]
    total_count: int
    filtered_totals: Optional[FilteredTransactionTotalsResponse] = None
    page: int
    page_size: int
    resolved_from: Optional[str] = None
    resolved_to: Optional[str] = None
    effective_horizon: Optional[int] = None


class BulkCategoryUpdateRequest(BaseModel):
    transaction_ids: List[UUID]
    category_id: Optional[UUID] = None


class BulkUpdateResponse(BaseModel):
    updated_count: int


class BulkAnalyticsUpdateRequest(BaseModel):
    transaction_ids: List[UUID]
    include_in_analytics: bool


class IncludeInAnalyticsUpdate(BaseModel):
    include_in_analytics: bool


# Transaction Link Schemas
class AccountOptionResponse(BaseModel):
    id: UUID
    name: str

    model_config = ConfigDict(from_attributes=True)


class CreateLinkGroupRequest(BaseModel):
    primary_id: UUID
    linked_ids: List[UUID]
    link_type: Literal["reimbursement", "expense"]


class CreateLinkGroupResponse(BaseModel):
    group_id: UUID


class AddToLinkGroupRequest(BaseModel):
    transaction_id: UUID
    role: Literal["primary", "reimbursement", "expense"]


class RemoveFromLinkGroupResponse(BaseModel):
    group_deleted: bool


class LinkedTransactionResponse(BaseModel):
    id: UUID
    amount: Decimal
    description: Optional[str] = None
    merchant: Optional[str] = None
    booked_at: datetime
    transaction_type: Optional[str] = None
    link_role: str


class TransactionLinkGroupResponse(BaseModel):
    group_id: UUID
    primary: Optional[LinkedTransactionResponse] = None
    linked: List[LinkedTransactionResponse]
    net_amount: Decimal
    currency: Optional[str] = None


class SuggestedLinkResponse(BaseModel):
    id: UUID
    amount: Decimal
    description: Optional[str] = None
    merchant: Optional[str] = None
    booked_at: datetime
    transaction_type: Optional[str] = None
    account_id: UUID
    account_name: Optional[str] = None
    score: float = 0


class LinkSearchResponse(BaseModel):
    transactions: List[SuggestedLinkResponse]
    total_count: int
    has_more: bool


class TransactionLinkInfoResponse(BaseModel):
    id: UUID
    group_id: UUID
    transaction_id: UUID
    link_role: str
    created_at: Optional[datetime] = None


class CreateLinkGroupFromSelectionRequest(BaseModel):
    transaction_ids: List[UUID]


# Receipt Scan Schemas
class ReceiptLineItemSchema(BaseModel):
    id: Optional[UUID] = None
    line_ref: Optional[str] = None
    position: Optional[int] = None
    raw_text: Optional[str] = None
    name: Optional[str] = None
    quantity: Optional[Decimal] = None
    gross_amount: Optional[Decimal] = None
    discount_amount: Optional[Decimal] = None
    net_amount: Optional[Decimal] = None
    kind: Optional[str] = None
    parent_line_ref: Optional[str] = None
    category_id: Optional[UUID] = None
    category_name: Optional[str] = None
    category_confidence: Optional[str] = None
    category_reason: Optional[str] = None
    user_edited: Optional[bool] = None

    # Legacy fields. `description`/`amount` are what the frontend's
    # toReceiptLineItem (actions.ts) still reads pre-Phase-4.5. Kept as
    # aliases of name/net_amount for one release -- Phase 4 extraction
    # (receipt_extract.py, replacing the deleted receipt_ocr.py) writes
    # name/net_amount, and the validator below mirrors them onto
    # description/amount so the response contract doesn't change out from
    # under the frontend. Do not remove until the frontend reads
    # name/net_amount directly.
    description: Optional[str] = None
    amount: Optional[Decimal] = None

    @model_validator(mode="after")
    def _sync_legacy_amount_aliases(self) -> "ReceiptLineItemSchema":
        if self.description is None and self.name is not None:
            self.description = self.name
        elif self.name is None and self.description is not None:
            self.name = self.description
        if self.amount is None and self.net_amount is not None:
            self.amount = self.net_amount
        elif self.net_amount is None and self.amount is not None:
            self.net_amount = self.amount
        return self


class ReceiptValidationErrorSchema(BaseModel):
    """Mirrors `app.services.receipt_validate.ValidationError` -- one
    reconcile failure the review UI highlights against the stored image
    (spec 1.2 / implementation 4.2)."""

    code: str
    message: str
    line_refs: List[str] = Field(default_factory=list)


class ReceiptScanExtractResponse(BaseModel):
    receipt_scan_id: UUID
    status: str
    merchant_name: Optional[str] = None
    receipt_date: Optional[datetime] = None
    receipt_total: Optional[Decimal] = None
    currency: Optional[str] = None
    items: List[ReceiptLineItemSchema] = Field(default_factory=list)
    validation_errors: List[ReceiptValidationErrorSchema] = Field(default_factory=list)
    error_message: Optional[str] = None


class ReceiptConfirmGroup(BaseModel):
    """One row of the confirm request -- what `receipt_resolve.resolve`
    calls a `TransactionGroup`, submitted by the review UI after the user
    has edited per-line categories (`frontend/features/receipt-scan/
    domain/contracts.ts`'s `ReceiptLineItem[]` stays the edit surface; this
    is its grouped-by-category projection). `line_refs` names the
    `ReceiptLineItem.line_ref`s folded into this group -- the server
    re-applies `category_id` onto those lines and re-runs `resolve` itself
    rather than trusting `amount`/`category_id` at face value (spec 6.2 /
    implementation 6.2)."""

    category_id: Optional[UUID] = None
    amount: Decimal
    description: str
    line_refs: List[str] = Field(default_factory=list)
    transaction_type: str = "debit"


class ReceiptScanConfirmRequest(BaseModel):
    groups: List[ReceiptConfirmGroup]
    # Defaults to `scan.booked_at`/`scan.receipt_date` server-side when
    # omitted (spec 6.2) -- required in the pre-Phase-6 contract, now
    # optional so the user can still override it.
    booked_at: Optional[datetime] = None


class ReceiptLineEditSchema(BaseModel):
    """One correction to an already-persisted line (Phase 6.5,
    `PATCH /{id}/lines`). Only the fields actually provided are applied --
    `None` means "leave unchanged", not "clear this field". If `net_amount`
    is corrected without also correcting `gross_amount`, `gross_amount` is
    recomputed server-side as `net_amount + discount_amount` so
    `gross - discount == net` keeps holding automatically -- the common
    correction is the user disagreeing with the charged price, not
    re-deriving gross/discount by hand for every edit."""

    line_ref: str
    name: Optional[str] = None
    gross_amount: Optional[Decimal] = None
    discount_amount: Optional[Decimal] = None
    net_amount: Optional[Decimal] = None


class ReceiptLineInsertSchema(BaseModel):
    """A line missing from extraction entirely (a hallucinated total, a
    misread that dropped a line) -- the server assigns `line_ref`, never the
    client (spec 6.5 requirement 1)."""

    name: Optional[str] = None
    gross_amount: Optional[Decimal] = None
    discount_amount: Optional[Decimal] = None
    net_amount: Decimal
    kind: str = "item"  # item | deposit
    # If set, must resolve to a surviving ("item") line -- either an
    # already-persisted line not being deleted in this same request, or
    # another "item" line inserted earlier in this same `inserts` list.
    parent_line_ref: Optional[str] = None


class ReceiptLineCorrectionRequest(BaseModel):
    """Body of `PATCH /{id}/lines` (Phase 6.5). `edits`/`inserts`/`deletes`
    are all optional and independent -- a caller only sends what actually
    changed, not the full line set."""

    edits: List[ReceiptLineEditSchema] = Field(default_factory=list)
    inserts: List[ReceiptLineInsertSchema] = Field(default_factory=list)
    deletes: List[str] = Field(default_factory=list)


class ReceiptResolvedGroupSchema(BaseModel):
    """One group as `receipt_resolve.resolve` computed it -- returned by the
    `/resolve` preview endpoint (uncollapsed and resolved side by side, so
    the review UI can show both without reimplementing the collapse policy
    in TypeScript) and echoed in the 409 the confirm endpoint raises when a
    submitted grouping doesn't match."""

    category_id: Optional[UUID] = None
    category_name: Optional[str] = None
    amount: Decimal
    line_refs: List[str] = Field(default_factory=list)


class ReceiptResolvePreviewLineOverride(BaseModel):
    """An in-progress (not-yet-saved) category edit the review UI wants
    reflected in a `/resolve` preview -- lines not named here use their
    currently-persisted `category_id`."""

    line_ref: str
    category_id: Optional[UUID] = None


class ReceiptResolvePreviewRequest(BaseModel):
    overrides: List[ReceiptResolvePreviewLineOverride] = Field(default_factory=list)


class ReceiptResolvePreviewResponse(BaseModel):
    uncollapsed: List[ReceiptResolvedGroupSchema]
    resolved: List[ReceiptResolvedGroupSchema]


class ReceiptConfirmResponse(BaseModel):
    """Response of `POST /{id}/confirm`. `already_booked=True` means the
    idempotency check (spec 6.3) found this exact receipt already booked on
    this account -- `transactions` is then the previously-created rows, not
    a fresh duplicate set."""

    transactions: List[TransactionWithDetails]
    already_booked: bool = False


# Analytics Schemas
class CategorySpending(BaseModel):
    category_id: Optional[UUID]
    category_name: Optional[str]
    total: Decimal
    count: int


class CategorySpendingCategoryResponse(BaseModel):
    id: str  # UUID string, or the literal "uncategorized"
    name: str
    color: Optional[str] = None
    icon: Optional[str] = None
    amount: Decimal
    share_pct: float
    delta_amount: Decimal
    delta_pct: float
    average_monthly_amount: Decimal


class CategorySpendingTopCategoryResponse(BaseModel):
    id: str
    name: str
    amount: Decimal


class CategorySpendingSummaryResponse(BaseModel):
    total_spend: Decimal
    average_monthly_spend: Decimal
    top_category: Optional[CategorySpendingTopCategoryResponse] = None


class CategorySpendingRangeResponse(BaseModel):
    start_date: str
    end_date: str
    comparison_start_date: str
    comparison_end_date: str
    month_count: int
    reference_date: str


class CategorySpendingDataResponse(BaseModel):
    currency: str
    categories: List[CategorySpendingCategoryResponse]
    summary: CategorySpendingSummaryResponse
    range: CategorySpendingRangeResponse


class CategorySpendingTransactionsPageResponse(BaseModel):
    rows: List[TransactionWithDetails]
    total_count: int
    page: int
    page_size: int


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
    transaction_type: Optional[str] = (
        None  # "debit" or "credit" - helps determine if expense or income
    )


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
    user_overrides: Optional[List[UserOverride]] = (
        None  # User-defined category overrides (applies to all transactions)
    )
    additional_instructions: Optional[List[str]] = (
        None  # User guidance for categorization (applies to all transactions)
    )


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
    avg_cost: Decimal
    funding_account_id: UUID


class HoldingUpdate(BaseModel):
    symbol: Optional[str] = None
    quantity: Optional[Decimal] = None
    as_of_date: Optional[_date_date] = None
    avg_cost: Optional[Decimal] = None
    provider_symbol: Optional[str] = None


class HoldingBuy(BaseModel):
    symbol: str
    provider_symbol: Optional[str] = None
    quantity: Decimal = Field(gt=0)
    instrument_type: Literal["equity", "etf"]
    currency: str
    price: Decimal = Field(gt=0)
    as_of_date: Optional[_date_date] = None


class HoldingSell(BaseModel):
    quantity: Decimal = Field(gt=0)
    price: Decimal = Field(gt=0)
    as_of_date: Optional[_date_date] = None


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
    """One trade row enriched with running quantity / cost."""

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


# Report Schemas
ReportFrequency = Literal["DAILY", "WEEKLY", "BIWEEKLY", "MONTHLY"]
ReportTransactionMode = Literal["RECENT", "TOP_N"]
ReportTransactionDirection = Literal["ALL", "EXPENSE", "INCOME", "INFLOW", "OUTFLOW"]

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_SEND_TIME_RE = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)(:([0-5]\d))?$")


def _validate_timezone(v: Optional[str]) -> Optional[str]:
    if v is None:
        return v
    try:
        ZoneInfo(v)
    except ZoneInfoNotFoundError:
        raise ValueError(f"Unknown timezone: {v}")
    return v


_MAX_RECIPIENT_EMAILS = 10


def _validate_recipient_emails(v: Optional[list[str]]) -> Optional[list[str]]:
    if v is None:
        return v
    if len(v) < 1:
        raise ValueError("recipient_emails must contain at least one email address")
    if len(v) > _MAX_RECIPIENT_EMAILS:
        raise ValueError(
            f"recipient_emails cannot contain more than {_MAX_RECIPIENT_EMAILS} addresses"
        )
    for email in v:
        if not _EMAIL_RE.match(email):
            raise ValueError(f"Invalid email address: {email}")
    return v


def _validate_send_time(v: Optional[str]) -> Optional[str]:
    if v is None:
        return v
    if not _SEND_TIME_RE.match(v):
        raise ValueError(f"Invalid send_time format (expected HH:MM or HH:MM:SS): {v}")
    return v


class ReportBase(BaseModel):
    name: str
    account_ids: list[str] = Field(default_factory=list)
    transaction_mode: ReportTransactionMode = "RECENT"  # RECENT, TOP_N
    transaction_count: int = Field(default=10, ge=1, le=100)
    transaction_direction: ReportTransactionDirection = (
        "ALL"  # ALL, EXPENSE, INCOME, INFLOW, OUTFLOW
    )
    frequency: ReportFrequency  # DAILY, WEEKLY, BIWEEKLY, MONTHLY
    send_time: str = "08:00:00"  # HH:MM:SS
    send_day_of_week: Optional[int] = Field(default=None, ge=0, le=6)
    send_day_of_month: Optional[int] = Field(default=None, ge=1, le=28)
    timezone: str = "UTC"
    recipient_emails: list[str]
    is_active: bool = True

    _check_timezone = field_validator("timezone")(_validate_timezone)
    # NOTE: send_time and recipient_emails are intentionally NOT validated
    # here — ReportResponse also inherits ReportBase, and pydantic v2 field
    # validators are inherited by subclasses even when the field type is
    # overridden (send_time) or the value comes from the ORM (recipient_emails
    # legacy rows could in principle be []), which would break response
    # serialization / reads with a 500 instead of just rejecting bad writes.
    # Validated on ReportCreate/ReportUpdate individually instead, so reads
    # are never blocked by a write-side validation rule. recipient_emails
    # also has no default here so that omitting it on create is itself a
    # 422 "field required" instead of silently defaulting to [] and only
    # failing later (previously: default_factory=list bypassed pydantic v2's
    # skip-validation-on-default behavior, letting an empty list reach the
    # DB unvalidated on create).


class ReportCreate(ReportBase):
    _check_send_time = field_validator("send_time")(_validate_send_time)
    _check_recipient_emails = field_validator("recipient_emails")(_validate_recipient_emails)

    @model_validator(mode="after")
    def _validate_required_day_fields(self) -> "ReportCreate":
        if self.frequency in ("WEEKLY", "BIWEEKLY") and self.send_day_of_week is None:
            raise ValueError("send_day_of_week is required when frequency is WEEKLY or BIWEEKLY")
        if self.frequency == "MONTHLY" and self.send_day_of_month is None:
            raise ValueError("send_day_of_month is required when frequency is MONTHLY")
        return self


class ReportUpdate(BaseModel):
    name: Optional[str] = None
    account_ids: Optional[list[str]] = None
    transaction_mode: Optional[ReportTransactionMode] = None
    transaction_count: Optional[int] = Field(default=None, ge=1, le=100)
    transaction_direction: Optional[ReportTransactionDirection] = None
    frequency: Optional[ReportFrequency] = None
    send_time: Optional[str] = None
    send_day_of_week: Optional[int] = Field(default=None, ge=0, le=6)
    send_day_of_month: Optional[int] = Field(default=None, ge=1, le=28)
    timezone: Optional[str] = None
    recipient_emails: Optional[list[str]] = None
    is_active: Optional[bool] = None
    # Note: no cross-field "day field required" validator here — a PATCH may
    # legitimately update only one field (e.g. recipient_emails) without
    # touching frequency/day fields. The route handler's _recompute_next_run
    # falls back to the already-persisted value for whichever field isn't in
    # this payload, so ReportCreate (which always has full context) is the
    # right place for that check.

    _check_timezone = field_validator("timezone")(_validate_timezone)
    _check_recipient_emails = field_validator("recipient_emails")(_validate_recipient_emails)
    _check_send_time = field_validator("send_time")(_validate_send_time)


class ReportResponse(ReportBase):
    id: UUID
    send_time: _time_type
    next_run_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ReportRunResponse(BaseModel):
    id: UUID
    scheduled_for: Optional[datetime] = None
    is_test: bool
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    status: str
    error_message: Optional[str] = None
    recipient_emails: list[str] = Field(default_factory=list)
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
