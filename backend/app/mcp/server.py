"""
Main FastMCP server setup for Syllogic.
Registers all tools from the tools modules.
"""
from fastmcp import FastMCP
from fastmcp.server.auth import RemoteAuthProvider
from pydantic import AnyHttpUrl

from app.db_helpers import get_mcp_user_id
from app.mcp.auth import CompositeAuthProvider, AS_ISSUER, MCP_PUBLIC_URL
from app.mcp.tools import accounts, categories, transactions, analytics, recurring, investments

_auth = RemoteAuthProvider(
    token_verifier=CompositeAuthProvider(),
    authorization_servers=[AnyHttpUrl(AS_ISSUER)],
    # Server root (no /mcp path). FastMCP appends the route itself when
    # advertising the Protected Resource, so passing "https://mcp.syllogic.ai/mcp"
    # here produced a broken resource URL of "https://mcp.syllogic.ai/mcp/mcp".
    base_url=MCP_PUBLIC_URL,
)

# Initialize FastMCP server
mcp = FastMCP(
    name="Syllogic MCP",
    instructions="""
Syllogic MCP Server - Access financial data and manage transactions.

All requests require a bearer token in the Authorization header. Two token
types are accepted:
- API keys (`Authorization: Bearer pf_...`) for Claude Desktop / Code and
  other local clients.
- OAuth 2.1 access tokens (JWTs) issued by the Syllogic authorization server
  for Claude on the web, iOS, Android, and any other custom connector.

The `user_id` parameter is optional on all tools but must match the authenticated user.

## Available functionality
- **Accounts**: List, view, and check balance history
- **Categories**: List, view, get tree structure, and update description/categorization_instructions
- **Transactions**: List, search, view, and update categories
- **Analytics**: Spending/income by category, monthly cashflow, financial summary
- **Recurring**: List and view subscriptions/bills
- **Investments**: List holdings, portfolio summary/history, symbol search,
  import broker trades (CSV/PDF/XLSX statements), realized & unrealized P&L (FIFO)

## Bulk recategorization workflow (recommended)

Use `search_transactions_multi` for efficient bulk operations:

```
# Step 1: Get category ID
categories = list_categories()
groceries_id = <find groceries category id>

# Step 2: Find all matching transactions in ONE call
result = search_transactions_multi(
    queries=["Jumbo", "Albert Heijn", "ALDI", "LIDL"],
    exclude_category_id=groceries_id,  # Skip already-categorized
    match_mode="word",  # Avoid false positives
    ids_only=True  # Faster, fewer tokens
)

# Step 3: Bulk update
bulk_update_transaction_categories(
    category_id=groceries_id,
    transaction_ids=result["transaction_ids"]
)
```

## Search options

- `match_mode="contains"` (default): Substring match - "Action" matches "Transaction"
- `match_mode="starts_with"`: "Action" matches "Action Store" but not "Reaction"
- `match_mode="word"`: Word boundary - "Action" matches "Action Store" but NOT "Transaction"

Use `match_mode="word"` for merchant names to avoid false positives!

## ⚠️ Pagination warning

When using `search_transactions`, ALWAYS check `has_more` in the response.
If true, you MUST call again with page=2, 3, etc. until has_more=false.
The `total_count` field tells you how many total results exist.

## Pagination & sort

All list/search tools accept:
- `cursor` (opaque string) — preferred for paging through large result sets; pass
  `next_cursor` from the previous response.
- `sort_by`: one of `booked_at_desc` (default), `booked_at_asc`, `amount_desc`,
  `amount_asc`, `abs_amount_desc`.
- `account_id` — limit to a single account.

## Audit filters

- `list_transactions(uncategorized=True)` — only rows with no category at all.
- `list_transactions(category_type="expense"|"income"|"transfer")` — filter by type.
- `get_spending_by_category(include_uncategorized=True)` — include an
  "Uncategorized" bucket with `merchant_count`.
- `get_top_merchants(category_id=...)` or `get_top_merchants(uncategorized=True)` —
  audit miscategorized or unassigned merchants.

## Safe bulk updates

`bulk_update_transaction_categories(dry_run=True)` returns what *would* change
(`would_update_count`, `sample_changes`) without mutating. Hard cap: 2000 IDs
per call. Response also includes `invalid_ids`, `not_found_ids`, and
`skipped_already_in_category_ids` so the agent can narrate exactly what
happened.
""",
    auth=_auth,
)


# ============================================================================
# Account Tools
# ============================================================================

@mcp.tool
def list_accounts(
    user_id: str | None = None,
    include_inactive: bool = False,
    asset_class: str | None = None,
) -> list[dict]:
    """
    List all accounts for a user.

    Args:
        user_id: The user's ID (optional, defaults to configured user)
        include_inactive: Whether to include inactive accounts (default: False)
        asset_class: Optional asset-class filter, one of "cash", "savings",
            "investment", "crypto", "property", "vehicle", "other".

    Returns:
        List of account dictionaries with id, name, account_type, asset_class,
        institution, currency, balance, etc.
    """
    return accounts.list_accounts(get_mcp_user_id(user_id), include_inactive, asset_class)


@mcp.tool
def get_account(account_id: str, user_id: str | None = None) -> dict | None:
    """
    Get a single account by ID.

    Args:
        account_id: The account's ID
        user_id: The user's ID (optional, defaults to configured user)

    Returns:
        Account dictionary (with asset_class derived from account_type) or None if not found
    """
    return accounts.get_account(get_mcp_user_id(user_id), account_id)


@mcp.tool
def get_account_balance_history(
    account_id: str,
    from_date: str | None = None,
    to_date: str | None = None,
    user_id: str | None = None
) -> list[dict]:
    """
    Get daily balance history for an account.

    Args:
        account_id: The account's ID
        from_date: Start date (ISO format YYYY-MM-DD, optional)
        to_date: End date (ISO format YYYY-MM-DD, optional)
        user_id: The user's ID (optional, defaults to configured user)

    Returns:
        List of balance snapshots with date, balance in account currency, and functional currency
    """
    return accounts.get_account_balance_history(get_mcp_user_id(user_id), account_id, from_date, to_date)


# ============================================================================
# Category Tools
# ============================================================================

@mcp.tool
def list_categories(user_id: str | None = None, category_type: str | None = None) -> list[dict]:
    """
    List all categories for a user.

    Args:
        user_id: The user's ID (optional, defaults to configured user)
        category_type: Filter by type (expense, income, transfer) - optional

    Returns:
        List of category dictionaries with id, name, type, color, icon, parent info
    """
    return categories.list_categories(get_mcp_user_id(user_id), category_type)


@mcp.tool
def get_category(category_id: str, user_id: str | None = None) -> dict | None:
    """
    Get a single category by ID.

    Args:
        category_id: The category's ID
        user_id: The user's ID (optional, defaults to configured user)

    Returns:
        Category dictionary or None if not found
    """
    return categories.get_category(get_mcp_user_id(user_id), category_id)


@mcp.tool
def update_category(
    category_id: str,
    description: str | None = None,
    categorization_instructions: str | None = None,
    user_id: str | None = None,
) -> dict:
    """
    Update a category's description and/or categorization_instructions.

    Use this to persist categorization context you learn during a conversation
    (e.g. "transactions from <merchant> should be Groceries unless the amount
    is under €5") so that future AI categorization applies the same rules.

    Only provided fields are written. Pass an empty string ("") to explicitly
    clear a field. System categories (e.g. Internal Transfer, External
    Transfer) are editable via this tool — description and
    categorization_instructions are user-tailored context.

    Args:
        category_id: The category's ID
        description: New human-readable description for this category (optional)
        categorization_instructions: Instructions the AI should follow when
            deciding whether a transaction belongs in this category (optional)
        user_id: The user's ID (optional, defaults to configured user)

    Returns:
        Dict with success status and updated category, or error message
    """
    return categories.update_category(
        get_mcp_user_id(user_id),
        category_id,
        description,
        categorization_instructions,
    )


@mcp.tool
def get_category_tree(user_id: str | None = None) -> list[dict]:
    """
    Get categories in a hierarchical tree structure.

    Args:
        user_id: The user's ID (optional, defaults to configured user)

    Returns:
        List of root categories, each with nested 'children' list
    """
    return categories.get_category_tree(get_mcp_user_id(user_id))


# ============================================================================
# Transaction Tools
# ============================================================================

@mcp.tool
def list_transactions(
    account_id: str | None = None,
    category_id: str | None = None,
    from_date: str | None = None,
    to_date: str | None = None,
    search: str | None = None,
    limit: int = 50,
    page: int = 1,
    cursor: str | None = None,
    sort_by: str = "booked_at_desc",
    uncategorized: bool = False,
    category_type: str | None = None,
    user_id: str | None = None,
) -> dict:
    """
    List transactions with optional filtering, cursor pagination, and sort.

    Args:
        account_id: Filter by account ID (optional)
        category_id: Filter by category ID (optional)
        from_date: Start date in ISO format YYYY-MM-DD (optional)
        to_date: End date in ISO format YYYY-MM-DD (optional)
        search: Search in description/merchant (optional)
        limit: Max results per page (default: 50, max: 100)
        page: Page number (default: 1) - ignored when cursor is provided
        cursor: Opaque cursor from previous response for stable pagination
        sort_by: Sort order - booked_at_desc (default), booked_at_asc,
            amount_desc, amount_asc, abs_amount_desc
        uncategorized: If True, return only transactions with no category
        category_type: Filter by resolved category type (expense, income, transfer)
        user_id: The user's ID (optional, defaults to configured user)

    Returns:
        Dict with transactions list, limit, page (or None), and next_cursor
    """
    return transactions.list_transactions(
        get_mcp_user_id(user_id), account_id, category_id, from_date, to_date, search,
        limit, page, cursor, sort_by, uncategorized, category_type,
    )


@mcp.tool
def get_transaction(transaction_id: str, user_id: str | None = None) -> dict | None:
    """
    Get a single transaction by ID.

    Args:
        transaction_id: The transaction's ID
        user_id: The user's ID (optional, defaults to configured user)

    Returns:
        Transaction dictionary or None if not found
    """
    return transactions.get_transaction(get_mcp_user_id(user_id), transaction_id)


@mcp.tool
def search_transactions(
    query: str,
    exclude_category_id: str | None = None,
    match_mode: str = "contains",
    ids_only: bool = False,
    limit: int = 50,
    page: int = 1,
    cursor: str | None = None,
    sort_by: str = "booked_at_desc",
    account_id: str | None = None,
    user_id: str | None = None,
) -> dict:
    """
    Search transactions by description or merchant name.

    ⚠️ PAGINATION WARNING: Always check `has_more` in the response!
    If true, you MUST call again with page=2, page=3, etc. until has_more=false.
    Prefer `cursor`/`next_cursor` for stable pagination over large result sets.

    Args:
        query: Search query string (case-insensitive)
        exclude_category_id: Skip transactions already in this category (useful for recategorization)
        match_mode: How to match the query:
            - "contains" (default): Substring match - "Action" matches "Transaction"
            - "starts_with": Must start with query - "Action" won't match "Transaction"
            - "word": Word boundary match - "Action" matches "Action Store" but NOT "Transaction"
        ids_only: If True, return only transaction IDs (faster, less tokens for bulk ops)
        limit: Max results per page (default: 50, max: 100)
        page: Page number (default: 1) - ignored when cursor is provided
        cursor: Opaque cursor from previous response for stable pagination
        sort_by: Sort order - booked_at_desc (default), booked_at_asc,
            amount_desc, amount_asc, abs_amount_desc
        account_id: Filter results to a single account (optional)
        user_id: The user's ID (optional, defaults to configured user)

    Returns:
        Dict with:
        - transactions: List of matching transactions (or transaction_ids if ids_only=True)
        - page: Current page number (None when cursor-paginated)
        - limit: Results per page
        - has_more: Boolean - KEEP PAGINATING until this is false!
        - total_count: Total matches across all pages (use to plan pagination)
        - next_cursor: Opaque cursor for next page (None when exhausted)

    Example - find transactions to recategorize:
        search_transactions(
            query="Jumbo",
            exclude_category_id="<groceries-uuid>",  # Skip already-categorized
            match_mode="word",  # Avoid matching "Jumbo" in unrelated text
            ids_only=True  # Just need IDs for bulk update
        )
    """
    return transactions.search_transactions(
        get_mcp_user_id(user_id), query, exclude_category_id, match_mode, ids_only,
        limit, page, cursor, sort_by, account_id,
    )


@mcp.tool
def search_transactions_multi(
    queries: list[str],
    exclude_category_id: str | None = None,
    match_mode: str = "contains",
    ids_only: bool = False,
    max_results: int = 500,
    cursor: str | None = None,
    sort_by: str = "booked_at_desc",
    account_id: str | None = None,
    user_id: str | None = None,
) -> dict:
    """
    Search transactions matching ANY of multiple queries in a single call.

    Use this instead of multiple search_transactions calls when you need to find
    transactions from several merchants at once (e.g., for bulk recategorization).

    Pass `cursor=""` (or a real cursor from `next_cursor`) to enable cursor
    pagination. Without a cursor, all results up to `max_results` are returned
    in one shot.

    Args:
        queries: List of search terms (e.g., ["Jumbo", "Albert Heijn", "ALDI", "LIDL"])
        exclude_category_id: Skip transactions already in this category
        match_mode: How to match queries:
            - "contains" (default): Substring match
            - "starts_with": Must start with query
            - "word": Word boundary match (recommended for merchant names)
        ids_only: If True, return only transaction IDs (recommended for bulk updates)
        max_results: Maximum results to return (default: 500, max: 1000)
        cursor: Opaque cursor; pass "" or a real cursor to enable cursor pagination
        sort_by: Sort order - booked_at_desc (default), booked_at_asc,
            amount_desc, amount_asc, abs_amount_desc
        account_id: Filter results to a single account (optional)
        user_id: The user's ID (optional, defaults to configured user)

    Returns:
        Dict with:
        - transactions (or transaction_ids): All matching transactions
        - total_count: Total matches found
        - capped: True if results hit max_results limit
        - query_counts: Matches per query (e.g., {"Jumbo": 127, "ALDI": 45})
        - next_cursor: Opaque cursor for next page (only in cursor mode)

    Example - recategorize grocery store transactions:
        # Step 1: Find all grocery transactions not yet categorized
        result = search_transactions_multi(
            queries=["Jumbo", "Albert Heijn", "ALDI", "LIDL", "Action"],
            exclude_category_id="<groceries-uuid>",
            match_mode="word",
            ids_only=True
        )
        # Step 2: Bulk update
        bulk_update_transaction_categories(
            category_id="<groceries-uuid>",
            transaction_ids=result["transaction_ids"]
        )
    """
    return transactions.search_transactions_multi(
        get_mcp_user_id(user_id), queries, exclude_category_id, match_mode, ids_only,
        max_results, cursor, sort_by, account_id,
    )


@mcp.tool
def update_transaction_category(
    transaction_id: str,
    category_id: str,
    user_id: str | None = None
) -> dict:
    """
    Update the category of a transaction (user override).

    This sets the user-defined category (category_id), which takes precedence
    over the AI-assigned category (category_system_id).

    Args:
        transaction_id: The transaction's ID
        category_id: The new category ID to assign
        user_id: The user's ID (optional, defaults to configured user)

    Returns:
        Dict with success status and updated transaction, or error message
    """
    return transactions.update_transaction_category(get_mcp_user_id(user_id), transaction_id, category_id)


@mcp.tool
def bulk_update_transaction_categories(
    category_id: str,
    transaction_ids: list[str],
    dry_run: bool = False,
    user_id: str | None = None,
) -> dict:
    """
    Bulk update category for multiple transactions.

    Args:
        category_id: The category ID to assign to all transactions
        transaction_ids: List of transaction IDs to update (max 2000)
        dry_run: If True, preview what would change without committing (default: False)
        user_id: The user's ID (optional, defaults to configured user)

    Returns:
        Dict with success status and:
        - updated_count (or would_update_count if dry_run=True)
        - requested_count, invalid_ids, not_found_ids,
          skipped_already_in_category_ids, sample_changes (up to 10)

    Recommended workflow using search_transactions_multi:
        # Find all grocery store transactions not yet categorized
        result = search_transactions_multi(
            queries=["Jumbo", "Albert Heijn", "ALDI"],
            exclude_category_id="<groceries-id>",
            match_mode="word",
            ids_only=True
        )
        # Preview first
        bulk_update_transaction_categories(
            category_id="<groceries-id>",
            transaction_ids=result["transaction_ids"],
            dry_run=True,
        )
        # Then commit
        bulk_update_transaction_categories(
            category_id="<groceries-id>",
            transaction_ids=result["transaction_ids"]
        )
    """
    return transactions.bulk_update_transaction_categories(
        get_mcp_user_id(user_id), category_id, transaction_ids, dry_run
    )


# ============================================================================
# Analytics Tools
# ============================================================================

@mcp.tool
def get_spending_by_category(
    from_date: str | None = None,
    to_date: str | None = None,
    account_id: str | None = None,
    include_uncategorized: bool = False,
    user_id: str | None = None,
) -> list[dict]:
    """
    Get spending breakdown by category.

    Args:
        from_date: Start date in ISO format YYYY-MM-DD (optional)
        to_date: End date in ISO format YYYY-MM-DD (optional)
        account_id: Filter by account ID (optional)
        include_uncategorized: If True, include an "Uncategorized" bucket for
            transactions with no category assigned (default: False)
        user_id: The user's ID (optional, defaults to configured user)

    Returns:
        List of categories with total spending amount, transaction count, and
        merchant_count
    """
    return analytics.get_spending_by_category(
        get_mcp_user_id(user_id), from_date, to_date, account_id, include_uncategorized
    )


@mcp.tool
def get_income_by_category(
    from_date: str | None = None,
    to_date: str | None = None,
    account_id: str | None = None,
    user_id: str | None = None
) -> list[dict]:
    """
    Get income breakdown by category.

    Args:
        from_date: Start date in ISO format YYYY-MM-DD (optional)
        to_date: End date in ISO format YYYY-MM-DD (optional)
        account_id: Filter by account ID (optional)
        user_id: The user's ID (optional, defaults to configured user)

    Returns:
        List of categories with total income amount and transaction count
    """
    return analytics.get_income_by_category(get_mcp_user_id(user_id), from_date, to_date, account_id)


@mcp.tool
def get_monthly_cashflow(
    from_date: str | None = None,
    to_date: str | None = None,
    user_id: str | None = None
) -> list[dict]:
    """
    Get monthly income vs expenses breakdown.

    Args:
        from_date: Start date in ISO format YYYY-MM-DD (optional)
        to_date: End date in ISO format YYYY-MM-DD (optional)
        user_id: The user's ID (optional, defaults to configured user)

    Returns:
        List of monthly data with income, expenses, and net for each month
    """
    return analytics.get_monthly_cashflow(get_mcp_user_id(user_id), from_date, to_date)


@mcp.tool
def get_financial_summary(
    from_date: str | None = None,
    to_date: str | None = None,
    user_id: str | None = None
) -> dict:
    """
    Get a financial summary with totals and account balances.

    Args:
        from_date: Start date in ISO format YYYY-MM-DD (optional)
        to_date: End date in ISO format YYYY-MM-DD (optional)
        user_id: The user's ID (optional, defaults to configured user)

    Returns:
        Summary with total income, total expenses, net, savings rate, and account balances
    """
    return analytics.get_financial_summary(get_mcp_user_id(user_id), from_date, to_date)


@mcp.tool
def get_top_merchants(
    from_date: str | None = None,
    to_date: str | None = None,
    limit: int = 10,
    category_id: str | None = None,
    uncategorized: bool = False,
    user_id: str | None = None,
) -> list[dict]:
    """
    Get top merchants by total spending.

    Args:
        from_date: Start date in ISO format YYYY-MM-DD (optional)
        to_date: End date in ISO format YYYY-MM-DD (optional)
        limit: Max number of merchants (default: 10, max: 50)
        category_id: Filter to transactions in this category (optional).
            Mutually exclusive with uncategorized.
        uncategorized: If True, return only transactions with no category.
            Mutually exclusive with category_id.
        user_id: The user's ID (optional, defaults to configured user)

    Returns:
        List of merchants with total spending and transaction count
    """
    return analytics.get_top_merchants(
        get_mcp_user_id(user_id), from_date, to_date, limit, category_id, uncategorized
    )


# ============================================================================
# Recurring Transaction Tools
# ============================================================================

@mcp.tool
def list_recurring_transactions(
    is_active: bool | None = None,
    user_id: str | None = None
) -> list[dict]:
    """
    List recurring transactions (subscriptions/bills) for a user.

    Args:
        is_active: Filter by active status (optional, defaults to showing all)
        user_id: The user's ID (optional, defaults to configured user)

    Returns:
        List of recurring transactions with details
    """
    return recurring.list_recurring_transactions(get_mcp_user_id(user_id), is_active)


@mcp.tool
def get_recurring_transaction(recurring_id: str, user_id: str | None = None) -> dict | None:
    """
    Get a single recurring transaction by ID.

    Args:
        recurring_id: The recurring transaction's ID
        user_id: The user's ID (optional, defaults to configured user)

    Returns:
        Recurring transaction dictionary or None if not found
    """
    return recurring.get_recurring_transaction(get_mcp_user_id(user_id), recurring_id)


@mcp.tool
def get_recurring_summary(user_id: str | None = None) -> dict:
    """
    Get a summary of recurring transactions (subscriptions/bills).

    Args:
        user_id: The user's ID (optional, defaults to configured user)

    Returns:
        Summary with totals by frequency, importance groups, and monthly/yearly costs
    """
    return recurring.get_recurring_summary(get_mcp_user_id(user_id))


# ============================================================================
# Investment Tools
# ============================================================================

@mcp.tool
def list_holdings(
    account_id: str | None = None,
    user_id: str | None = None,
) -> list[dict]:
    """
    List investment holdings for a user, with the latest available valuation.

    Args:
        account_id: Filter to a single investment account (optional)
        user_id: The user's ID (optional, defaults to configured user)

    Returns:
        List of holdings with symbol, quantity, latest price, and current value
        in the user's functional currency.
    """
    return investments.list_holdings(get_mcp_user_id(user_id), account_id)


@mcp.tool
def get_portfolio_summary(user_id: str | None = None) -> dict:
    """
    Get a summary of the user's investment portfolio.

    Aggregates the latest holding valuations across all active investment
    accounts (manual + brokerage).

    Args:
        user_id: The user's ID (optional, defaults to configured user)

    Returns:
        Dict with currency, total_value, holdings_count, stale_valuations,
        and a per-account breakdown.
    """
    return investments.get_portfolio_summary(get_mcp_user_id(user_id))


@mcp.tool
def get_portfolio_history(
    from_date: str | None = None,
    to_date: str | None = None,
    user_id: str | None = None,
) -> list[dict]:
    """
    Get daily portfolio value history (sum across investment accounts) in
    the user's functional currency.

    Args:
        from_date: Start date (ISO YYYY-MM-DD, optional)
        to_date: End date (ISO YYYY-MM-DD, optional)
        user_id: The user's ID (optional, defaults to configured user)

    Returns:
        List of {date, value_user_currency} entries sorted by date.
    """
    return investments.get_portfolio_history(get_mcp_user_id(user_id), from_date, to_date)


@mcp.tool
def search_symbol(query: str, user_id: str | None = None) -> list[dict]:
    """
    Search the user's existing holdings by symbol or name (case-insensitive).

    Args:
        query: Substring to match against holding symbol or name
        user_id: The user's ID (optional, defaults to configured user)

    Returns:
        List of matching {symbol, name, currency, instrument_type} entries.
    """
    return investments.search_symbol(get_mcp_user_id(user_id), query)


@mcp.tool
def import_broker_trades(
    account_id: str,
    trades: list[dict],
    dry_run: bool = False,
    user_id: str | None = None,
) -> dict:
    """
    Import a batch of broker trades for an investment account.

    Use this after you (the LLM) have parsed a broker statement (CSV/PDF/XLSX)
    into a typed list of trades. The tool dedupes by stable external_id, so
    re-uploading the same statement is a no-op.

    Workflow:
        1. Call list_accounts(account_type="investment_brokerage") or
           list_accounts(account_type="investment_manual") to find the right account.
        2. Parse the user's statement file into the `trades` shape below.
        3. Call this with dry_run=True first to preview.
        4. Call again with dry_run=False to commit.

    Args:
        account_id: UUID of an investment-type account owned by the authenticated user.
        trades: List of trade dicts. Each dict must include:
            - symbol (str): ticker, e.g. "AAPL"
            - trade_date (str): ISO date "YYYY-MM-DD"
            - side (str): "buy" or "sell"
            - quantity (str|number): positive number of shares
            - price (str|number): per-share price in native currency
            - currency (str): 3-letter ISO code, e.g. "USD"
            - fees (str|number, optional): broker fees/commission in native
              currency; defaults to 0. On buys, fees increase cost basis;
              on sells, fees reduce proceeds.
            - external_id (str, optional): broker's confirmation/trade id; if
              omitted, the server generates a deterministic hash so re-uploads
              are idempotent.
            - broker_ref (str, optional): broker confirmation reference for traceability.
        dry_run: If True, runs the import in a transaction and rolls back; the
            return shape is the same. Use this to preview before committing.
        user_id: Optional, defaults to authenticated user.

    Returns:
        Dict with keys:
            - inserted (int): rows newly inserted
            - skipped_duplicate (int): rows skipped because external_id already existed
            - errors (list): per-trade validation errors with {index, trade, reason}
            - affected_symbols (list[str]): symbols touched (Holding rows recomputed)
    """
    return investments.import_broker_trades(
        get_mcp_user_id(user_id), account_id, trades, dry_run
    )


@mcp.tool
def get_realized_pnl(
    account_id: str | None = None,
    symbol: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    user_id: str | None = None,
) -> list[dict]:
    """
    Compute FIFO realized P&L from imported broker trades.

    Returns one row per symbol, with native-currency totals plus
    base-currency totals (using FX on each lot's close date).

    Args:
        account_id: Filter to a single investment account (optional).
        symbol: Filter to a single symbol (optional).
        start_date: ISO YYYY-MM-DD; only count trades on/after this date.
        end_date: ISO YYYY-MM-DD; only count trades on/before this date.
        user_id: Optional, defaults to authenticated user.

    Returns:
        List of {symbol, currency, realized_native, realized_base, lots_closed[]}.
    """
    return investments.get_realized_pnl(
        get_mcp_user_id(user_id), account_id, symbol, start_date, end_date
    )


@mcp.tool
def get_unrealized_pnl(
    account_id: str | None = None,
    symbol: str | None = None,
    user_id: str | None = None,
) -> list[dict]:
    """
    Compute unrealized P&L for currently-open FIFO lots.

    Uses the latest HoldingValuation price per symbol. Symbols without a
    valuation are omitted (run a price refresh first if needed).

    Args:
        account_id: Filter to a single investment account (optional).
        symbol: Filter to a single symbol (optional).
        user_id: Optional, defaults to authenticated user.

    Returns:
        List of {symbol, currency, quantity, cost_basis_native, cost_basis_base,
        market_value_native, market_value_base, unrealized_native, unrealized_base, fx_missing}.
    """
    return investments.get_unrealized_pnl(get_mcp_user_id(user_id), account_id, symbol)
