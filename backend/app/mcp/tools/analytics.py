"""
Analytics tools for the MCP server.
"""
from typing import Optional

from sqlalchemy import func, extract, case, or_, and_, text
from sqlalchemy.orm import aliased

from app.mcp.dependencies import get_db, validate_uuid, validate_date
from app.models import Transaction, Category, Account, TransactionLink
from app.services.ownership_service import attribute_amount, entity_ids_for_people, get_owners


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
    account_id: Optional[str] = None,
    include_uncategorized: bool = False,
    person_ids: Optional[list[str]] = None,
) -> list[dict]:
    """
    Get spending breakdown by category.

    Uses net amounts for linked transactions (primary gets group net).

    Args:
        user_id: The user's ID
        from_date: Start date in ISO format (optional)
        to_date: End date in ISO format (optional)
        account_id: Filter by account ID (optional)
        include_uncategorized: If True, include an "Uncategorized" bucket for
            transactions with no category assigned (default: False)
        person_ids: Optional list of person UUIDs. When provided, only includes
            transactions from accounts owned by any of the specified people.

    Returns:
        List of categories with total spending amount, transaction count, and
        merchant_count
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

    # person_ids ownership filter — builds an IN clause over allowed account ids
    _person_ids_filter_spending = ""
    if person_ids is not None and len(person_ids) > 0:
        with get_db() as _db:
            _allowed = [str(uid) for uid in entity_ids_for_people(_db, "account", person_ids)]
        if not _allowed:
            return []
        _ids_literal = ", ".join(f"'{a}'" for a in _allowed)
        _person_ids_filter_spending = f" AND t.account_id IN ({_ids_literal})"

    join_type = "LEFT JOIN" if include_uncategorized else "INNER JOIN"
    # With INNER JOIN we already exclude null-category rows, so restrict to
    # expense categories only. With LEFT JOIN we keep all debit rows but still
    # require categorised rows to be expenses — null-category rows are allowed
    # via the OR arm so they appear as the "Uncategorized" bucket.
    uncategorized_filter = (
        "AND (c.category_type = 'expense' OR c.id IS NULL)"
        if include_uncategorized
        else "AND c.category_type = 'expense'"
    )

    with get_db() as db:
        sql = text(f"""
            {_get_link_group_nets_cte(user_id)}
            SELECT
                COALESCE(t.category_id, t.category_system_id) as category_id,
                COALESCE(c.name, 'Uncategorized') as category_name,
                c.color as category_color,
                COALESCE(SUM(
                    CASE
                        WHEN tl.link_role = 'primary' THEN
                            CASE WHEN lgn.net_amount < 0 THEN ABS(lgn.net_amount) ELSE 0 END
                        WHEN tl.link_role IS NOT NULL THEN 0
                        ELSE ABS(t.amount)
                    END
                ), 0) as total,
                COUNT(t.id) as count,
                COUNT(DISTINCT t.merchant) FILTER (WHERE t.merchant IS NOT NULL AND t.merchant <> '') as merchant_count
            FROM transactions t
            {join_type} categories c ON c.id = COALESCE(t.category_id, t.category_system_id)
            LEFT JOIN transaction_links tl ON t.id = tl.transaction_id
            LEFT JOIN link_group_nets lgn ON tl.group_id = lgn.group_id
            WHERE t.user_id = '{user_id}'
                AND t.transaction_type = 'debit'
                AND t.include_in_analytics = true
                {uncategorized_filter}
                {date_filter}
                {account_filter}
                {_person_ids_filter_spending}
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
                "merchant_count": r.merchant_count,
            }
            for r in results
        ]


def get_income_by_category(
    user_id: str,
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    account_id: Optional[str] = None,
    person_ids: Optional[list[str]] = None,
) -> list[dict]:
    """
    Get income breakdown by category.

    Uses net amounts for linked transactions (primary gets group net).

    Args:
        user_id: The user's ID
        from_date: Start date in ISO format (optional)
        to_date: End date in ISO format (optional)
        account_id: Filter by account ID (optional)
        person_ids: Optional list of person UUIDs. When provided, only includes
            transactions from accounts owned by any of the specified people.

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

    # person_ids ownership filter
    _person_ids_filter_income = ""
    if person_ids is not None and len(person_ids) > 0:
        with get_db() as _db:
            _allowed = [str(uid) for uid in entity_ids_for_people(_db, "account", person_ids)]
        if not _allowed:
            return []
        _ids_literal = ", ".join(f"'{a}'" for a in _allowed)
        _person_ids_filter_income = f" AND t.account_id IN ({_ids_literal})"

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
                {_person_ids_filter_income}
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
    to_date: Optional[str] = None,
    person_ids: Optional[list[str]] = None,
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
        person_ids: Optional list of person UUIDs. When provided, only includes
            transactions from accounts owned by any of the specified people.

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

    # person_ids ownership filter
    _person_ids_filter_cashflow = ""
    if person_ids is not None and len(person_ids) > 0:
        with get_db() as _db:
            _allowed = [str(uid) for uid in entity_ids_for_people(_db, "account", person_ids)]
        if not _allowed:
            return []
        _ids_literal = ", ".join(f"'{a}'" for a in _allowed)
        _person_ids_filter_cashflow = f" AND t.account_id IN ({_ids_literal})"

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
                {_person_ids_filter_cashflow}
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
    to_date: Optional[str] = None,
    person_ids: Optional[list[str]] = None,
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
        person_ids: Optional list of person UUIDs. When provided, only includes
            transactions and balances from accounts owned by any of the specified
            people. When exactly one person_id is given, account balances are
            share-weighted to that person's ownership fraction.

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

    # person_ids ownership filter
    filter_by_person = person_ids is not None and len(person_ids) > 0
    single_person = filter_by_person and len(person_ids) == 1
    _allowed_account_ids: list[str] = []
    _person_ids_filter_summary = ""
    if filter_by_person:
        with get_db() as _db:
            _allowed_account_ids = [str(uid) for uid in entity_ids_for_people(_db, "account", person_ids)]
        if not _allowed_account_ids:
            return {
                "period": {"from_date": from_date, "to_date": to_date},
                "total_income": 0,
                "total_expenses": 0,
                "net_cashflow": 0,
                "savings_rate": 0,
                "total_balance": 0,
                "accounts": [],
            }
        _ids_literal = ", ".join(f"'{a}'" for a in _allowed_account_ids)
        _person_ids_filter_summary = f" AND t.account_id IN ({_ids_literal})"

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
                {_person_ids_filter_summary}
        """)

        result = db.execute(sql).fetchone()

        total_income = float(result.total_income or 0)
        total_expenses = float(result.total_expenses or 0)

        # Get account balances (current)
        accounts_query = db.query(Account).filter(
            Account.user_id == user_id,
            Account.is_active == True
        )
        if filter_by_person and _allowed_account_ids:
            accounts_query = accounts_query.filter(Account.id.in_(_allowed_account_ids))
        accounts = accounts_query.all()

        # Cache owners for share-weighted attribution
        owners_cache: dict = {}
        if single_person:
            for acc in accounts:
                owners_cache[str(acc.id)] = get_owners(db, "account", acc.id)

        def _acc_balance(acc) -> float:
            full = float(acc.functional_balance or acc.balance_available or 0)
            if single_person:
                return attribute_amount(full, owners_cache[str(acc.id)], person_ids[0])
            return full

        total_balance = sum(_acc_balance(acc) for acc in accounts)

        account_balances = [
            {
                "id": str(acc.id),
                "name": acc.name,
                "balance": _acc_balance(acc),
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
    limit: int = 10,
    category_id: Optional[str] = None,
    uncategorized: bool = False,
) -> list[dict]:
    """
    Get top merchants by total spending.

    Args:
        user_id: The user's ID
        from_date: Start date in ISO format (optional)
        to_date: End date in ISO format (optional)
        limit: Max number of merchants (default: 10, max: 50)
        category_id: Filter to transactions in this category (optional).
            Mutually exclusive with uncategorized.
        uncategorized: If True, return only transactions with no category.
            Mutually exclusive with category_id.

    Returns:
        List of merchants with total spending and transaction count
    """
    if category_id and uncategorized:
        raise ValueError("category_id and uncategorized are mutually exclusive")

    cat_uuid = validate_uuid(category_id) if category_id else None
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

        if cat_uuid:
            query = query.filter(
                or_(
                    Transaction.category_id == cat_uuid,
                    and_(
                        Transaction.category_id.is_(None),
                        Transaction.category_system_id == cat_uuid,
                    ),
                )
            )

        if uncategorized:
            query = query.filter(
                Transaction.category_id.is_(None),
                Transaction.category_system_id.is_(None),
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
