"""
Analytics tools for the MCP server.
"""
from typing import Optional

from sqlalchemy import func, extract, case, or_

from app.mcp.dependencies import get_db, validate_uuid, validate_date
from app.models import Transaction, Category, Account


def get_spending_by_category(
    user_id: str,
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    account_id: Optional[str] = None
) -> list[dict]:
    """
    Get spending breakdown by category.

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

    with get_db() as db:
        query = db.query(
            func.coalesce(Transaction.category_id, Transaction.category_system_id).label("category_id"),
            Category.name.label("category_name"),
            Category.color.label("category_color"),
            func.sum(func.abs(Transaction.amount)).label("total"),
            func.count(Transaction.id).label("count"),
        ).outerjoin(
            Category,
            (Transaction.category_id == Category.id) | (Transaction.category_system_id == Category.id)
        ).filter(
            Transaction.user_id == user_id,
            Transaction.amount < 0,  # Only expenses
            Transaction.include_in_analytics == True,
            # Exclude transfers but handle NULL category_type
            or_(Category.category_type != "transfer", Category.category_type.is_(None))
        )

        if from_dt:
            query = query.filter(Transaction.booked_at >= from_dt)

        if to_dt:
            query = query.filter(Transaction.booked_at <= to_dt)

        if account_id and account_uuid:
            query = query.filter(Transaction.account_id == account_uuid)

        results = query.group_by(
            func.coalesce(Transaction.category_id, Transaction.category_system_id),
            Category.name,
            Category.color
        ).order_by(func.sum(func.abs(Transaction.amount)).desc()).all()

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

    with get_db() as db:
        query = db.query(
            func.coalesce(Transaction.category_id, Transaction.category_system_id).label("category_id"),
            Category.name.label("category_name"),
            Category.color.label("category_color"),
            func.sum(Transaction.amount).label("total"),
            func.count(Transaction.id).label("count"),
        ).outerjoin(
            Category,
            (Transaction.category_id == Category.id) | (Transaction.category_system_id == Category.id)
        ).filter(
            Transaction.user_id == user_id,
            Transaction.amount > 0,  # Only income
            Transaction.include_in_analytics == True,
            # Exclude transfers but handle NULL category_type
            or_(Category.category_type != "transfer", Category.category_type.is_(None))
        )

        if from_dt:
            query = query.filter(Transaction.booked_at >= from_dt)

        if to_dt:
            query = query.filter(Transaction.booked_at <= to_dt)

        if account_id and account_uuid:
            query = query.filter(Transaction.account_id == account_uuid)

        results = query.group_by(
            func.coalesce(Transaction.category_id, Transaction.category_system_id),
            Category.name,
            Category.color
        ).order_by(func.sum(Transaction.amount).desc()).all()

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

    with get_db() as db:
        query = db.query(
            extract("year", Transaction.booked_at).label("year"),
            extract("month", Transaction.booked_at).label("month"),
            func.sum(case((Transaction.amount > 0, Transaction.amount), else_=0)).label("income"),
            func.sum(case((Transaction.amount < 0, func.abs(Transaction.amount)), else_=0)).label("expenses"),
        ).filter(
            Transaction.user_id == user_id,
            Transaction.include_in_analytics == True
        )

        if from_dt:
            query = query.filter(Transaction.booked_at >= from_dt)

        if to_dt:
            query = query.filter(Transaction.booked_at <= to_dt)

        results = (
            query.group_by(
                extract("year", Transaction.booked_at),
                extract("month", Transaction.booked_at),
            )
            .order_by(
                extract("year", Transaction.booked_at),
                extract("month", Transaction.booked_at),
            )
            .all()
        )

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

    with get_db() as db:
        # Get income/expense totals
        txn_query = db.query(
            func.sum(case((Transaction.amount > 0, Transaction.amount), else_=0)).label("total_income"),
            func.sum(case((Transaction.amount < 0, func.abs(Transaction.amount)), else_=0)).label("total_expenses"),
        ).filter(
            Transaction.user_id == user_id,
            Transaction.include_in_analytics == True
        )

        if from_dt:
            txn_query = txn_query.filter(Transaction.booked_at >= from_dt)

        if to_dt:
            txn_query = txn_query.filter(Transaction.booked_at <= to_dt)

        txn_result = txn_query.first()

        total_income = float(txn_result.total_income or 0)
        total_expenses = float(txn_result.total_expenses or 0)

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
