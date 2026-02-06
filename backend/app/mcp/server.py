"""
Main FastMCP server setup for Syllogic.
Registers all tools from the tools modules.
"""
from fastmcp import FastMCP

from app.db_helpers import get_user_id
from app.mcp.tools import accounts, categories, transactions, analytics, recurring

# Initialize FastMCP server
mcp = FastMCP(
    name="Syllogic MCP",
    instructions="""
Syllogic MCP Server - Access financial data and manage transactions.

The `user_id` parameter is optional on all tools - it defaults to the configured user.
You can omit it for single-user setups.

## Available functionality
- **Accounts**: List, view, and check balance history
- **Categories**: List, view, and get category tree structure
- **Transactions**: List, search, view, and update categories
- **Analytics**: Spending/income by category, monthly cashflow, financial summary
- **Recurring**: List and view subscriptions/bills

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
"""
)


# ============================================================================
# Account Tools
# ============================================================================

@mcp.tool
def list_accounts(user_id: str | None = None, include_inactive: bool = False) -> list[dict]:
    """
    List all accounts for a user.

    Args:
        user_id: The user's ID (optional, defaults to configured user)
        include_inactive: Whether to include inactive accounts (default: False)

    Returns:
        List of account dictionaries with id, name, type, institution, currency, balance, etc.
    """
    return accounts.list_accounts(get_user_id(user_id), include_inactive)


@mcp.tool
def get_account(account_id: str, user_id: str | None = None) -> dict | None:
    """
    Get a single account by ID.

    Args:
        account_id: The account's ID
        user_id: The user's ID (optional, defaults to configured user)

    Returns:
        Account dictionary or None if not found
    """
    return accounts.get_account(get_user_id(user_id), account_id)


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
    return accounts.get_account_balance_history(get_user_id(user_id), account_id, from_date, to_date)


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
    return categories.list_categories(get_user_id(user_id), category_type)


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
    return categories.get_category(get_user_id(user_id), category_id)


@mcp.tool
def get_category_tree(user_id: str | None = None) -> list[dict]:
    """
    Get categories in a hierarchical tree structure.

    Args:
        user_id: The user's ID (optional, defaults to configured user)

    Returns:
        List of root categories, each with nested 'children' list
    """
    return categories.get_category_tree(get_user_id(user_id))


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
    user_id: str | None = None
) -> list[dict]:
    """
    List transactions with optional filtering.

    Args:
        account_id: Filter by account ID (optional)
        category_id: Filter by category ID (optional)
        from_date: Start date in ISO format YYYY-MM-DD (optional)
        to_date: End date in ISO format YYYY-MM-DD (optional)
        search: Search in description/merchant (optional)
        limit: Max results per page (default: 50, max: 100)
        page: Page number (default: 1)
        user_id: The user's ID (optional, defaults to configured user)

    Returns:
        List of transaction dictionaries with account and category info
    """
    return transactions.list_transactions(
        get_user_id(user_id), account_id, category_id, from_date, to_date, search, limit, page
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
    return transactions.get_transaction(get_user_id(user_id), transaction_id)


@mcp.tool
def search_transactions(
    query: str,
    exclude_category_id: str | None = None,
    match_mode: str = "contains",
    ids_only: bool = False,
    limit: int = 50,
    page: int = 1,
    user_id: str | None = None
) -> dict:
    """
    Search transactions by description or merchant name.

    ⚠️ PAGINATION WARNING: Always check `has_more` in the response!
    If true, you MUST call again with page=2, page=3, etc. until has_more=false.

    Args:
        query: Search query string (case-insensitive)
        exclude_category_id: Skip transactions already in this category (useful for recategorization)
        match_mode: How to match the query:
            - "contains" (default): Substring match - "Action" matches "Transaction"
            - "starts_with": Must start with query - "Action" won't match "Transaction"
            - "word": Word boundary match - "Action" matches "Action Store" but NOT "Transaction"
        ids_only: If True, return only transaction IDs (faster, less tokens for bulk ops)
        limit: Max results per page (default: 50, max: 100)
        page: Page number (default: 1)
        user_id: The user's ID (optional, defaults to configured user)

    Returns:
        Dict with:
        - transactions: List of matching transactions (or transaction_ids if ids_only=True)
        - page: Current page number
        - limit: Results per page
        - has_more: Boolean - KEEP PAGINATING until this is false!
        - total_count: Total matches across all pages (use to plan pagination)

    Example - find transactions to recategorize:
        search_transactions(
            query="Jumbo",
            exclude_category_id="<groceries-uuid>",  # Skip already-categorized
            match_mode="word",  # Avoid matching "Jumbo" in unrelated text
            ids_only=True  # Just need IDs for bulk update
        )
    """
    return transactions.search_transactions(
        get_user_id(user_id), query, exclude_category_id, match_mode, ids_only, limit, page
    )


@mcp.tool
def search_transactions_multi(
    queries: list[str],
    exclude_category_id: str | None = None,
    match_mode: str = "contains",
    ids_only: bool = False,
    max_results: int = 500,
    user_id: str | None = None
) -> dict:
    """
    Search transactions matching ANY of multiple queries in a single call.

    Use this instead of multiple search_transactions calls when you need to find
    transactions from several merchants at once (e.g., for bulk recategorization).

    Args:
        queries: List of search terms (e.g., ["Jumbo", "Albert Heijn", "ALDI", "LIDL"])
        exclude_category_id: Skip transactions already in this category
        match_mode: How to match queries:
            - "contains" (default): Substring match
            - "starts_with": Must start with query
            - "word": Word boundary match (recommended for merchant names)
        ids_only: If True, return only transaction IDs (recommended for bulk updates)
        max_results: Maximum results to return (default: 500, max: 1000)
        user_id: The user's ID (optional, defaults to configured user)

    Returns:
        Dict with:
        - transactions (or transaction_ids): All matching transactions
        - total_count: Total matches found
        - capped: True if results hit max_results limit
        - query_counts: Matches per query (e.g., {"Jumbo": 127, "ALDI": 45})

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
        get_user_id(user_id), queries, exclude_category_id, match_mode, ids_only, max_results
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
    return transactions.update_transaction_category(get_user_id(user_id), transaction_id, category_id)


@mcp.tool
def bulk_update_transaction_categories(
    category_id: str,
    transaction_ids: list[str],
    user_id: str | None = None
) -> dict:
    """
    Bulk update category for multiple transactions.

    Args:
        category_id: The category ID to assign to all transactions
        transaction_ids: List of transaction IDs to update
        user_id: The user's ID (optional, defaults to configured user)

    Returns:
        Dict with success status, updated_count, and any errors

    Recommended workflow using search_transactions_multi:
        # Find all grocery store transactions not yet categorized
        result = search_transactions_multi(
            queries=["Jumbo", "Albert Heijn", "ALDI"],
            exclude_category_id="<groceries-id>",
            match_mode="word",
            ids_only=True
        )
        # Update them all at once
        bulk_update_transaction_categories(
            category_id="<groceries-id>",
            transaction_ids=result["transaction_ids"]
        )
    """
    return transactions.bulk_update_transaction_categories(
        get_user_id(user_id), category_id, transaction_ids
    )


# ============================================================================
# Analytics Tools
# ============================================================================

@mcp.tool
def get_spending_by_category(
    from_date: str | None = None,
    to_date: str | None = None,
    account_id: str | None = None,
    user_id: str | None = None
) -> list[dict]:
    """
    Get spending breakdown by category.

    Args:
        from_date: Start date in ISO format YYYY-MM-DD (optional)
        to_date: End date in ISO format YYYY-MM-DD (optional)
        account_id: Filter by account ID (optional)
        user_id: The user's ID (optional, defaults to configured user)

    Returns:
        List of categories with total spending amount and transaction count
    """
    return analytics.get_spending_by_category(get_user_id(user_id), from_date, to_date, account_id)


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
    return analytics.get_income_by_category(get_user_id(user_id), from_date, to_date, account_id)


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
    return analytics.get_monthly_cashflow(get_user_id(user_id), from_date, to_date)


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
    return analytics.get_financial_summary(get_user_id(user_id), from_date, to_date)


@mcp.tool
def get_top_merchants(
    from_date: str | None = None,
    to_date: str | None = None,
    limit: int = 10,
    user_id: str | None = None
) -> list[dict]:
    """
    Get top merchants by total spending.

    Args:
        from_date: Start date in ISO format YYYY-MM-DD (optional)
        to_date: End date in ISO format YYYY-MM-DD (optional)
        limit: Max number of merchants (default: 10, max: 50)
        user_id: The user's ID (optional, defaults to configured user)

    Returns:
        List of merchants with total spending and transaction count
    """
    return analytics.get_top_merchants(get_user_id(user_id), from_date, to_date, limit)


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
    return recurring.list_recurring_transactions(get_user_id(user_id), is_active)


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
    return recurring.get_recurring_transaction(get_user_id(user_id), recurring_id)


@mcp.tool
def get_recurring_summary(user_id: str | None = None) -> dict:
    """
    Get a summary of recurring transactions (subscriptions/bills).

    Args:
        user_id: The user's ID (optional, defaults to configured user)

    Returns:
        Summary with totals by frequency, importance groups, and monthly/yearly costs
    """
    return recurring.get_recurring_summary(get_user_id(user_id))
