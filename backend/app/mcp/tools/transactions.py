"""
Transaction tools for the MCP server.
"""
from typing import Optional, Literal

from sqlalchemy import or_, and_, func
from sqlalchemy.orm import joinedload

from app.mcp.dependencies import get_db, validate_uuid, validate_date
from app.models import Transaction, Account, Category


# Type alias for match modes
MatchMode = Literal["contains", "starts_with", "word"]


def list_transactions(
    user_id: str,
    account_id: Optional[str] = None,
    category_id: Optional[str] = None,
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    search: Optional[str] = None,
    limit: int = 50,
    page: int = 1
) -> list[dict]:
    """
    List transactions with optional filtering.

    Args:
        user_id: The user's ID
        account_id: Filter by account ID (optional)
        category_id: Filter by category ID (optional)
        from_date: Start date in ISO format (optional)
        to_date: End date in ISO format (optional)
        search: Search in description/merchant (optional)
        limit: Max results per page (default: 50, max: 100)
        page: Page number (default: 1)

    Returns:
        List of transaction dictionaries with account and category info
    """
    # Validate pagination parameters
    page = max(1, page)
    limit = min(max(1, limit), 100)
    offset = (page - 1) * limit

    # Validate UUID parameters
    account_uuid = validate_uuid(account_id) if account_id else None
    category_uuid = validate_uuid(category_id) if category_id else None

    # Validate date parameters
    from_dt = validate_date(from_date)
    to_dt = validate_date(to_date)

    with get_db() as db:
        query = (
            db.query(Transaction)
            .filter(Transaction.user_id == user_id)
            .options(joinedload(Transaction.account), joinedload(Transaction.category))
        )

        if account_id and account_uuid:
            query = query.filter(Transaction.account_id == account_uuid)

        if category_id and category_uuid:
            query = query.filter(
                (Transaction.category_id == category_uuid) |
                (Transaction.category_system_id == category_uuid)
            )

        if from_dt:
            query = query.filter(Transaction.booked_at >= from_dt)

        if to_dt:
            query = query.filter(Transaction.booked_at <= to_dt)

        if search:
            # Limit search string length to prevent excessive memory usage
            search = search[:500]
            search_term = f"%{search}%"
            query = query.filter(
                or_(
                    Transaction.description.ilike(search_term),
                    Transaction.merchant.ilike(search_term),
                )
            )

        transactions = (
            query.order_by(Transaction.booked_at.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )

        return [
            {
                "id": str(txn.id),
                "account_id": str(txn.account_id),
                "account_name": txn.account.name if txn.account else None,
                "amount": float(txn.amount),
                "currency": txn.currency,
                "description": txn.description,
                "merchant": txn.merchant,
                "category_id": str(txn.category_id) if txn.category_id else None,
                "category_system_id": str(txn.category_system_id) if txn.category_system_id else None,
                "category_name": txn.category.name if txn.category else None,
                "booked_at": txn.booked_at.isoformat() if txn.booked_at else None,
                "pending": txn.pending,
                "transaction_type": txn.transaction_type,
                "include_in_analytics": txn.include_in_analytics,
                "recurring_transaction_id": str(txn.recurring_transaction_id) if txn.recurring_transaction_id else None,
            }
            for txn in transactions
        ]


def get_transaction(user_id: str, transaction_id: str) -> dict | None:
    """
    Get a single transaction by ID.

    Args:
        user_id: The user's ID
        transaction_id: The transaction's ID

    Returns:
        Transaction dictionary or None if not found
    """
    txn_uuid = validate_uuid(transaction_id)
    if not txn_uuid:
        return None

    with get_db() as db:
        txn = (
            db.query(Transaction)
            .filter(
                Transaction.id == txn_uuid,
                Transaction.user_id == user_id
            )
            .options(joinedload(Transaction.account), joinedload(Transaction.category))
            .first()
        )

        if not txn:
            return None

        return {
            "id": str(txn.id),
            "account_id": str(txn.account_id),
            "account_name": txn.account.name if txn.account else None,
            "external_id": txn.external_id,
            "transaction_type": txn.transaction_type,
            "amount": float(txn.amount),
            "currency": txn.currency,
            "functional_amount": float(txn.functional_amount) if txn.functional_amount else None,
            "description": txn.description,
            "merchant": txn.merchant,
            "category_id": str(txn.category_id) if txn.category_id else None,
            "category_system_id": str(txn.category_system_id) if txn.category_system_id else None,
            "category_name": txn.category.name if txn.category else None,
            "booked_at": txn.booked_at.isoformat() if txn.booked_at else None,
            "pending": txn.pending,
            "categorization_instructions": txn.categorization_instructions,
            "enrichment_data": txn.enrichment_data,
            "include_in_analytics": txn.include_in_analytics,
            "recurring_transaction_id": str(txn.recurring_transaction_id) if txn.recurring_transaction_id else None,
            "created_at": txn.created_at.isoformat() if txn.created_at else None,
            "updated_at": txn.updated_at.isoformat() if txn.updated_at else None,
        }


def _build_search_filter(query_str: str, match_mode: MatchMode):
    """
    Build SQLAlchemy filter based on match mode.

    Args:
        query_str: The search query string
        match_mode: How to match - "contains", "starts_with", or "word"

    Returns:
        SQLAlchemy filter expression
    """
    if match_mode == "starts_with":
        pattern = f"{query_str}%"
        return or_(
            Transaction.description.ilike(pattern),
            Transaction.merchant.ilike(pattern),
        )
    elif match_mode == "word":
        # Word boundary matching - match whole words only
        # We use regex-like patterns: look for word at start, end, or surrounded by non-word chars
        # PostgreSQL ILIKE doesn't support regex, so we approximate with multiple conditions
        patterns = [
            f"{query_str}",           # Exact match
            f"{query_str} %",         # Word at start
            f"% {query_str}",         # Word at end
            f"% {query_str} %",       # Word in middle
            f"{query_str},%",         # Word before comma
            f"%,{query_str}",         # Word after comma
            f"{query_str}.%",         # Word before period
            f"%.{query_str}",         # Word after period
        ]
        description_conditions = [Transaction.description.ilike(p) for p in patterns]
        merchant_conditions = [Transaction.merchant.ilike(p) for p in patterns]
        return or_(*description_conditions, *merchant_conditions)
    else:  # contains (default)
        pattern = f"%{query_str}%"
        return or_(
            Transaction.description.ilike(pattern),
            Transaction.merchant.ilike(pattern),
        )


def search_transactions(
    user_id: str,
    query: str,
    exclude_category_id: Optional[str] = None,
    match_mode: MatchMode = "contains",
    ids_only: bool = False,
    limit: int = 50,
    page: int = 1
) -> dict:
    """
    Search transactions by description or merchant name.

    ⚠️ PAGINATION: Check `has_more` in the response! If true, call again with
    page=2, page=3, etc. until has_more=false to get all results.

    Args:
        user_id: The user's ID
        query: Search query string (case-insensitive)
        exclude_category_id: Exclude transactions already in this category (optional)
        match_mode: How to match the query:
            - "contains": Substring match (default) - "Action" matches "Transaction"
            - "starts_with": Must start with query - "Action" won't match "Transaction"
            - "word": Word boundary match - "Action" matches "Action Store" but not "Transaction"
        ids_only: If True, return only transaction IDs (faster for bulk operations)
        limit: Max results per page (default: 50, max: 100)
        page: Page number (default: 1)

    Returns:
        Dict with:
        - transactions: List of matching transactions (or transaction_ids if ids_only=True)
        - page: Current page number
        - limit: Results per page
        - has_more: Boolean - if true, call again with next page!
        - total_count: Total number of matching transactions across all pages
    """
    page = max(1, page)
    limit = min(max(1, limit), 100)
    offset = (page - 1) * limit

    # Limit search string length to prevent excessive memory usage
    query_str = query[:500] if query else ""

    # Validate exclude_category_id if provided
    exclude_cat_uuid = validate_uuid(exclude_category_id) if exclude_category_id else None

    with get_db() as db:
        # Build base query with user filter
        base_filter = and_(
            Transaction.user_id == user_id,
            _build_search_filter(query_str, match_mode)
        )

        # Add category exclusion if specified
        if exclude_cat_uuid:
            base_filter = and_(
                base_filter,
                or_(
                    Transaction.category_id != exclude_cat_uuid,
                    Transaction.category_id.is_(None)
                )
            )

        # Get total count first
        total_count = db.query(func.count(Transaction.id)).filter(base_filter).scalar()

        # Fetch transactions
        query_obj = (
            db.query(Transaction)
            .filter(base_filter)
            .order_by(Transaction.booked_at.desc())
            .offset(offset)
            .limit(limit)
        )

        # Only load relationships if we need full data
        if not ids_only:
            query_obj = query_obj.options(
                joinedload(Transaction.account),
                joinedload(Transaction.category)
            )

        transactions = query_obj.all()

        # Check if there are more results beyond this page
        has_more = (offset + len(transactions)) < total_count

        if ids_only:
            return {
                "transaction_ids": [str(txn.id) for txn in transactions],
                "page": page,
                "limit": limit,
                "has_more": has_more,
                "total_count": total_count,
            }

        return {
            "transactions": [
                {
                    "id": str(txn.id),
                    "account_id": str(txn.account_id),
                    "account_name": txn.account.name if txn.account else None,
                    "amount": float(txn.amount),
                    "currency": txn.currency,
                    "description": txn.description,
                    "merchant": txn.merchant,
                    "category_id": str(txn.category_id) if txn.category_id else None,
                    "category_name": txn.category.name if txn.category else None,
                    "booked_at": txn.booked_at.isoformat() if txn.booked_at else None,
                }
                for txn in transactions
            ],
            "page": page,
            "limit": limit,
            "has_more": has_more,
            "total_count": total_count,
        }


def search_transactions_multi(
    user_id: str,
    queries: list[str],
    exclude_category_id: Optional[str] = None,
    match_mode: MatchMode = "contains",
    ids_only: bool = False,
    max_results: int = 500
) -> dict:
    """
    Search transactions matching ANY of the given queries.

    Returns all matching transactions in a single call (no pagination needed).
    Useful for bulk recategorization workflows where you need to find transactions
    from multiple merchants at once.

    Args:
        user_id: The user's ID
        queries: List of search queries (e.g., ["Jumbo", "Albert Heijn", "ALDI"])
        exclude_category_id: Exclude transactions already in this category (optional)
        match_mode: How to match queries:
            - "contains": Substring match (default)
            - "starts_with": Must start with query
            - "word": Word boundary match
        ids_only: If True, return only transaction IDs (faster for bulk operations)
        max_results: Maximum results to return (default: 500, max: 1000)

    Returns:
        Dict with:
        - transactions (or transaction_ids if ids_only): All matching transactions
        - total_count: Total matches found
        - capped: True if results were limited by max_results
        - query_counts: Dict mapping each query to its match count
    """
    if not queries:
        return {"error": "Must provide at least one query", "success": False}

    max_results = min(max(1, max_results), 1000)

    # Validate exclude_category_id if provided
    exclude_cat_uuid = validate_uuid(exclude_category_id) if exclude_category_id else None

    with get_db() as db:
        # Build combined filter for all queries
        query_filters = []
        for q in queries:
            q_str = q[:500] if q else ""
            if q_str:
                query_filters.append(_build_search_filter(q_str, match_mode))

        if not query_filters:
            return {"error": "No valid queries provided", "success": False}

        # Combine all query filters with OR
        combined_filter = and_(
            Transaction.user_id == user_id,
            or_(*query_filters)
        )

        # Add category exclusion if specified
        if exclude_cat_uuid:
            combined_filter = and_(
                combined_filter,
                or_(
                    Transaction.category_id != exclude_cat_uuid,
                    Transaction.category_id.is_(None)
                )
            )

        # Get total count
        total_count = db.query(func.count(Transaction.id)).filter(combined_filter).scalar()

        # Fetch transactions
        query_obj = (
            db.query(Transaction)
            .filter(combined_filter)
            .order_by(Transaction.booked_at.desc())
            .limit(max_results)
        )

        if not ids_only:
            query_obj = query_obj.options(
                joinedload(Transaction.account),
                joinedload(Transaction.category)
            )

        transactions = query_obj.all()

        # Count matches per query (for transparency)
        query_counts = {}
        for q in queries:
            q_str = q[:500] if q else ""
            if q_str:
                q_filter = and_(
                    Transaction.user_id == user_id,
                    _build_search_filter(q_str, match_mode)
                )
                if exclude_cat_uuid:
                    q_filter = and_(
                        q_filter,
                        or_(
                            Transaction.category_id != exclude_cat_uuid,
                            Transaction.category_id.is_(None)
                        )
                    )
                query_counts[q] = db.query(func.count(Transaction.id)).filter(q_filter).scalar()

        result = {
            "total_count": total_count,
            "capped": len(transactions) < total_count,
            "query_counts": query_counts,
        }

        if ids_only:
            result["transaction_ids"] = [str(txn.id) for txn in transactions]
        else:
            result["transactions"] = [
                {
                    "id": str(txn.id),
                    "account_id": str(txn.account_id),
                    "account_name": txn.account.name if txn.account else None,
                    "amount": float(txn.amount),
                    "currency": txn.currency,
                    "description": txn.description,
                    "merchant": txn.merchant,
                    "category_id": str(txn.category_id) if txn.category_id else None,
                    "category_name": txn.category.name if txn.category else None,
                    "booked_at": txn.booked_at.isoformat() if txn.booked_at else None,
                }
                for txn in transactions
            ]

        return result


def update_transaction_category(
    user_id: str,
    transaction_id: str,
    category_id: str
) -> dict:
    """
    Update the category of a transaction (user override).

    This sets the user-defined category (category_id), which takes precedence
    over the AI-assigned category (category_system_id).

    Args:
        user_id: The user's ID
        transaction_id: The transaction's ID
        category_id: The new category ID to assign

    Returns:
        Dict with success status and updated transaction, or error message
    """
    # Validate UUIDs upfront
    txn_uuid = validate_uuid(transaction_id)
    if not txn_uuid:
        return {"success": False, "error": "Invalid transaction ID format"}

    cat_uuid = validate_uuid(category_id)
    if not cat_uuid:
        return {"success": False, "error": "Invalid category ID format"}

    with get_db() as db:
        # Verify transaction belongs to user
        txn = db.query(Transaction).filter(
            Transaction.id == txn_uuid,
            Transaction.user_id == user_id
        ).first()

        if not txn:
            return {"success": False, "error": "Transaction not found"}

        # Verify category belongs to user
        category = db.query(Category).filter(
            Category.id == cat_uuid,
            Category.user_id == user_id
        ).first()

        if not category:
            return {"success": False, "error": "Category not found"}

        # Update the transaction's category with error handling
        try:
            txn.category_id = cat_uuid
            db.commit()
            db.refresh(txn)
        except Exception as e:
            db.rollback()
            return {"success": False, "error": f"Database error: {str(e)}"}

        return {
            "success": True,
            "transaction": {
                "id": str(txn.id),
                "category_id": str(txn.category_id),
                "category_name": category.name,
                "description": txn.description,
                "merchant": txn.merchant,
                "amount": float(txn.amount),
            }
        }


def bulk_update_transaction_categories(
    user_id: str,
    category_id: str,
    transaction_ids: list[str]
) -> dict:
    """
    Bulk update category for multiple transactions.

    Args:
        user_id: The user's ID
        category_id: The category ID to assign
        transaction_ids: List of transaction IDs to update

    Returns:
        Dict with success, updated_count, and any errors
    """
    if not transaction_ids:
        return {"success": False, "error": "Must provide transaction_ids"}

    cat_uuid = validate_uuid(category_id)
    if not cat_uuid:
        return {"success": False, "error": "Invalid category ID format"}

    with get_db() as db:
        # Verify category belongs to user
        category = db.query(Category).filter(
            Category.id == cat_uuid,
            Category.user_id == user_id
        ).first()

        if not category:
            return {"success": False, "error": "Category not found"}

        try:
            valid_uuids = []
            invalid_ids = []
            for tid in transaction_ids:
                uuid = validate_uuid(tid)
                if uuid:
                    valid_uuids.append(uuid)
                else:
                    invalid_ids.append(tid)

            if not valid_uuids:
                return {"success": False, "error": "No valid transaction IDs provided"}

            result = db.query(Transaction).filter(
                Transaction.user_id == user_id,
                Transaction.id.in_(valid_uuids)
            ).update(
                {Transaction.category_id: cat_uuid},
                synchronize_session=False
            )
            db.commit()

            response = {
                "success": True,
                "updated_count": result,
                "category_name": category.name,
                "requested_count": len(transaction_ids)
            }
            if invalid_ids:
                response["invalid_ids"] = invalid_ids
            return response

        except Exception as e:
            db.rollback()
            return {"success": False, "error": f"Database error: {str(e)}"}
