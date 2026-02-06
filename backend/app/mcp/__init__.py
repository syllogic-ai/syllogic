"""
MCP (Model Context Protocol) server for Syllogic.
Provides read-only access to financial data with one write operation (update transaction category).

Usage:
    from app.mcp.server import mcp

Tools available:
    Accounts:
        - list_accounts
        - get_account
        - get_account_balance_history

    Categories:
        - list_categories
        - get_category
        - get_category_tree

    Transactions:
        - list_transactions
        - get_transaction
        - search_transactions
        - update_transaction_category (WRITE)

    Analytics:
        - get_spending_by_category
        - get_income_by_category
        - get_monthly_cashflow
        - get_financial_summary
        - get_top_merchants

    Recurring:
        - list_recurring_transactions
        - get_recurring_transaction
        - get_recurring_summary
"""
