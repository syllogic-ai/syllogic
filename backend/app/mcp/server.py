"""
Main FastMCP server setup for the Personal Finance App.
Registers all tools from the tools modules.
"""
from fastmcp import FastMCP

from app.db_helpers import get_user_id
from app.mcp.tools import accounts, categories, transactions, analytics, recurring

# Initialize FastMCP server
mcp = FastMCP(
    name="Personal Finance MCP",
    instructions="""
Personal Finance MCP Server - Access financial data and manage transactions.

The `user_id` parameter is optional on all tools - it defaults to the configured user.
You can omit it for single-user setups.

Available functionality:
- Accounts: List, view, and check balance history
- Categories: List, view, and get category tree structure
- Transactions: List, search, view, and update categories
- Analytics: Spending/income by category, monthly cashflow, financial summary
- Recurring: List and view subscriptions/bills

The only write operation available is `update_transaction_category`.
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
def search_transactions(query: str, limit: int = 20, user_id: str | None = None) -> list[dict]:
    """
    Search transactions by description or merchant name.

    Args:
        query: Search query string
        limit: Max results (default: 20, max: 50)
        user_id: The user's ID (optional, defaults to configured user)

    Returns:
        List of matching transactions
    """
    return transactions.search_transactions(get_user_id(user_id), query, limit)


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
