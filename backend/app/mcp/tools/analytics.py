"""
Analytics tools for the MCP server.
"""
from typing import Optional

from sqlalchemy import func, extract, case, or_, and_, text
from sqlalchemy.orm import aliased

from app.mcp.dependencies import get_db, validate_uuid, validate_date
from app.models import Transaction, Category, Account, TransactionLink


def _get_link_group_nets_cte(user_id: str) -> str:
    """Generate SQL CTE for calculating net amounts per link group."""
    return f"""
    WITH link_group_nets AS (
        SELECT
            tl.group_id,
            SUM(t.amount) as net_amount
        FROM transactions t
        JOIN transaction_links tl ON t.id = tl.transaction_id
        WHERE t.user_id = '{user_id}'
        GROUP BY tl.group_id
    )
    """


def get_spending_by_category(
    user_id: str,
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    account_id: Optional[str] = None
) -> list[dict]:
    """
    Get spending breakdown by category.

    Uses net amounts for linked transactions (primary gets group net).

    Args:
        user_id: The user's ID
        from_date: Start date in ISO format (optional)
        to_date: End date in ISO format (optional)
        account_id: Filter by account ID (optional)

    Returns:
        List of categories with total spending amount and transaction count
    """
    # Validate parameters
    from_dt = validate_date(from_date)
    to_dt = validate_date(to_date)
    account_uuid = validate_uuid(account_id) if account_id else None

    # Build filters
    date_filter = ""
    if from_dt:
        date_filter += f" AND t.booked_at >= '{from_dt.isoformat()}'"
    if to_dt:
        date_filter += f" AND t.booked_at <= '{to_dt.isoformat()}'"

    account_filter = ""
    if account_uuid:
        account_filter = f" AND t.account_id = '{account_uuid}'"

    with get_db() as db:
        sql = text(f"""
            {_get_link_group_nets_cte(user_id)}
            SELECT
                COALESCE(t.category_id, t.category_system_id) as category_id,
                c.name as category_name,
                c.color as category_color,
                COALESCE(SUM(
                    CASE
                        WHEN tl.link_role = 'primary' THEN
                            CASE WHEN lgn.net_amount < 0 THEN ABS(lgn.net_amount) ELSE 0 END
                        WHEN tl.link_role IS NOT NULL THEN 0
                        ELSE ABS(t.amount)
                    END
                ), 0) as total,
                COUNT(t.id) as count
            FROM transactions t
            INNER JOIN categories c ON c.id = COALESCE(t.category_id, t.category_system_id)
            LEFT JOIN transaction_links tl ON t.id = tl.transaction_id
            LEFT JOIN link_group_nets lgn ON tl.group_id = lgn.group_id
            WHERE t.user_id = '{user_id}'
                AND t.transaction_type = 'debit'
                AND t.include_in_analytics = true
                AND c.category_type = 'expense'
                {date_filter}
                {account_filter}
            GROUP BY COALESCE(t.category_id, t.category_system_id), c.name, c.color
            ORDER BY total DESC
        """)

        results = db.execute(sql).fetchall()

        return [
            {
                "category_id": str(r.category_id) if r.category_id else None,
                "category_name": r.category_name or "Uncategorized",
                "category_color": r.category_color,
                "total": float(r.total) if r.total else 0,
                "count": r.count,
            }
            for r in results
        ]


def get_income_by_category(
    user_id: str,
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    account_id: Optional[str] = None
) -> list[dict]:
    """
    Get income breakdown by category.

    Uses net amounts for linked transactions (primary gets group net).

    Args:
        user_id: The user's ID
        from_date: Start date in ISO format (optional)
        to_date: End date in ISO format (optional)
        account_id: Filter by account ID (optional)

    Returns:
        List of categories with total income amount and transaction count
    """
    # Validate parameters
    from_dt = validate_date(from_date)
    to_dt = validate_date(to_date)
    account_uuid = validate_uuid(account_id) if account_id else None

    # Build filters
    date_filter = ""
    if from_dt:
        date_filter += f" AND t.booked_at >= '{from_dt.isoformat()}'"
    if to_dt:
        date_filter += f" AND t.booked_at <= '{to_dt.isoformat()}'"

    account_filter = ""
    if account_uuid:
        account_filter = f" AND t.account_id = '{account_uuid}'"

    with get_db() as db:
        sql = text(f"""
            {_get_link_group_nets_cte(user_id)}
            SELECT
                COALESCE(t.category_id, t.category_system_id) as category_id,
                c.name as category_name,
                c.color as category_color,
                COALESCE(SUM(
                    CASE
                        WHEN tl.link_role = 'primary' THEN
                            CASE WHEN lgn.net_amount > 0 THEN lgn.net_amount ELSE 0 END
                        WHEN tl.link_role IS NOT NULL THEN 0
                        ELSE t.amount
                    END
                ), 0) as total,
                COUNT(t.id) as count
            FROM transactions t
            INNER JOIN categories c ON c.id = COALESCE(t.category_id, t.category_system_id)
            LEFT JOIN transaction_links tl ON t.id = tl.transaction_id
            LEFT JOIN link_group_nets lgn ON tl.group_id = lgn.group_id
            WHERE t.user_id = '{user_id}'
                AND t.transaction_type = 'credit'
                AND t.include_in_analytics = true
                AND c.category_type = 'income'
                {date_filter}
                {account_filter}
            GROUP BY COALESCE(t.category_id, t.category_system_id), c.name, c.color
            ORDER BY total DESC
        """)

        results = db.execute(sql).fetchall()

        return [
            {
                "category_id": str(r.category_id) if r.category_id else None,
                "category_name": r.category_name or "Uncategorized",
                "category_color": r.category_color,
                "total": float(r.total) if r.total else 0,
                "count": r.count,
            }
            for r in results
        ]


def get_monthly_cashflow(
    user_id: str,
    from_date: Optional[str] = None,
    to_date: Optional[str] = None
) -> list[dict]:
    """
    Get monthly income vs expenses breakdown.

    Filters by category type to exclude transfers:
    - Income: Only transactions with category_type='income'
    - Expenses: Only transactions with category_type='expense'
    - Uses net amounts for linked transactions (primary gets group net)

    Args:
        user_id: The user's ID
        from_date: Start date in ISO format (optional)
        to_date: End date in ISO format (optional)

    Returns:
        List of monthly data with income, expenses, and net for each month
    """
    # Validate parameters
    from_dt = validate_date(from_date)
    to_dt = validate_date(to_date)

    # Build date filter
    date_filter = ""
    if from_dt:
        date_filter += f" AND t.booked_at >= '{from_dt.isoformat()}'"
    if to_dt:
        date_filter += f" AND t.booked_at <= '{to_dt.isoformat()}'"

    with get_db() as db:
        sql = text(f"""
            {_get_link_group_nets_cte(user_id)}
            SELECT
                EXTRACT(YEAR FROM t.booked_at)::int as year,
                EXTRACT(MONTH FROM t.booked_at)::int as month,
                COALESCE(SUM(
                    CASE
                        WHEN c.category_type = 'income' THEN
                            CASE
                                WHEN tl.link_role = 'primary' THEN
                                    CASE WHEN lgn.net_amount > 0 THEN lgn.net_amount ELSE 0 END
                                WHEN tl.link_role IS NOT NULL THEN 0
                                ELSE ABS(t.amount)
                            END
                        ELSE 0
                    END
                ), 0) as income,
                COALESCE(SUM(
                    CASE
                        WHEN c.category_type = 'expense' THEN
                            CASE
                                WHEN tl.link_role = 'primary' THEN
                                    CASE WHEN lgn.net_amount < 0 THEN ABS(lgn.net_amount) ELSE 0 END
                                WHEN tl.link_role IS NOT NULL THEN 0
                                ELSE ABS(t.amount)
                            END
                        ELSE 0
                    END
                ), 0) as expenses
            FROM transactions t
            INNER JOIN categories c ON c.id = COALESCE(t.category_id, t.category_system_id)
            LEFT JOIN transaction_links tl ON t.id = tl.transaction_id
            LEFT JOIN link_group_nets lgn ON tl.group_id = lgn.group_id
            WHERE t.user_id = '{user_id}'
                AND t.include_in_analytics = true
                {date_filter}
            GROUP BY EXTRACT(YEAR FROM t.booked_at), EXTRACT(MONTH FROM t.booked_at)
            ORDER BY EXTRACT(YEAR FROM t.booked_at), EXTRACT(MONTH FROM t.booked_at)
        """)

        results = db.execute(sql).fetchall()

        return [
            {
                "month": f"{int(r.year)}-{int(r.month):02d}",
                "income": float(r.income) if r.income else 0,
                "expenses": float(r.expenses) if r.expenses else 0,
                "net": float(r.income or 0) - float(r.expenses or 0),
            }
            for r in results
        ]


def get_financial_summary(
    user_id: str,
    from_date: Optional[str] = None,
    to_date: Optional[str] = None
) -> dict:
    """
    Get a financial summary with totals and net worth.

    Filters by category type to exclude transfers:
    - Income: Only transactions with category_type='income'
    - Expenses: Only transactions with category_type='expense'
    - Uses net amounts for linked transactions (primary gets group net)

    Args:
        user_id: The user's ID
        from_date: Start date in ISO format (optional)
        to_date: End date in ISO format (optional)

    Returns:
        Summary with total income, total expenses, net, and account balances
    """
    # Validate parameters
    from_dt = validate_date(from_date)
    to_dt = validate_date(to_date)

    # Build date filter
    date_filter = ""
    if from_dt:
        date_filter += f" AND t.booked_at >= '{from_dt.isoformat()}'"
    if to_dt:
        date_filter += f" AND t.booked_at <= '{to_dt.isoformat()}'"

    with get_db() as db:
        sql = text(f"""
            {_get_link_group_nets_cte(user_id)}
            SELECT
                COALESCE(SUM(
                    CASE
                        WHEN c.category_type = 'income' THEN
                            CASE
                                WHEN tl.link_role = 'primary' THEN
                                    CASE WHEN lgn.net_amount > 0 THEN lgn.net_amount ELSE 0 END
                                WHEN tl.link_role IS NOT NULL THEN 0
                                ELSE ABS(t.amount)
                            END
                        ELSE 0
                    END
                ), 0) as total_income,
                COALESCE(SUM(
                    CASE
                        WHEN c.category_type = 'expense' THEN
                            CASE
                                WHEN tl.link_role = 'primary' THEN
                                    CASE WHEN lgn.net_amount < 0 THEN ABS(lgn.net_amount) ELSE 0 END
                                WHEN tl.link_role IS NOT NULL THEN 0
                                ELSE ABS(t.amount)
                            END
                        ELSE 0
                    END
                ), 0) as total_expenses
            FROM transactions t
            INNER JOIN categories c ON c.id = COALESCE(t.category_id, t.category_system_id)
            LEFT JOIN transaction_links tl ON t.id = tl.transaction_id
            LEFT JOIN link_group_nets lgn ON tl.group_id = lgn.group_id
            WHERE t.user_id = '{user_id}'
                AND t.include_in_analytics = true
                {date_filter}
        """)

        result = db.execute(sql).fetchone()

        total_income = float(result.total_income or 0)
        total_expenses = float(result.total_expenses or 0)

        # Get account balances (current)
        accounts = db.query(Account).filter(
            Account.user_id == user_id,
            Account.is_active == True
        ).all()

        total_balance = sum(
            float(acc.functional_balance or acc.balance_available or 0)
            for acc in accounts
        )

        account_balances = [
            {
                "id": str(acc.id),
                "name": acc.name,
                "balance": float(acc.functional_balance or acc.balance_available or 0),
                "currency": acc.currency,
                "account_type": acc.account_type,
            }
            for acc in accounts
        ]

        return {
            "period": {
                "from_date": from_date,
                "to_date": to_date,
            },
            "total_income": total_income,
            "total_expenses": total_expenses,
            "net_cashflow": total_income - total_expenses,
            "savings_rate": round((total_income - total_expenses) / total_income * 100, 1) if total_income > 0 else 0,
            "total_balance": total_balance,
            "accounts": account_balances,
        }


def get_top_merchants(
    user_id: str,
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    limit: int = 10
) -> list[dict]:
    """
    Get top merchants by total spending.

    Args:
        user_id: The user's ID
        from_date: Start date in ISO format (optional)
        to_date: End date in ISO format (optional)
        limit: Max number of merchants (default: 10, max: 50)

    Returns:
        List of merchants with total spending and transaction count
    """
    limit = min(max(1, limit), 50)

    # Validate parameters
    from_dt = validate_date(from_date)
    to_dt = validate_date(to_date)

    with get_db() as db:
        query = db.query(
            Transaction.merchant,
            func.sum(func.abs(Transaction.amount)).label("total"),
            func.count(Transaction.id).label("count"),
        ).filter(
            Transaction.user_id == user_id,
            Transaction.amount < 0,  # Only expenses
            Transaction.merchant.isnot(None),
            Transaction.merchant != "",
            Transaction.include_in_analytics == True
        )

        if from_dt:
            query = query.filter(Transaction.booked_at >= from_dt)

        if to_dt:
            query = query.filter(Transaction.booked_at <= to_dt)

        results = (
            query.group_by(Transaction.merchant)
            .order_by(func.sum(func.abs(Transaction.amount)).desc())
            .limit(limit)
            .all()
        )

        return [
            {
                "merchant": r.merchant,
                "total": float(r.total) if r.total else 0,
                "count": r.count,
            }
            for r in results
        ]
