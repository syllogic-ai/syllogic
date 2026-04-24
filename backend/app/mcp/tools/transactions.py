"""
Transaction tools for the MCP server.
"""
from __future__ import annotations

import base64
import json
from datetime import datetime
from decimal import Decimal
from typing import Optional, Literal

from sqlalchemy import or_, and_, func
from sqlalchemy.orm import joinedload

from app.mcp.dependencies import get_db, validate_uuid, validate_date
from app.models import Transaction, Account, Category


# Type alias for match modes
MatchMode = Literal["contains", "starts_with", "word"]

# Type alias for sort modes
SortBy = Literal[
    "booked_at_desc",
    "booked_at_asc",
    "amount_desc",
    "amount_asc",
    "abs_amount_desc",
]


def _sort_expr(sort_by: SortBy):
    """Return (primary_col, direction_func) for the given sort mode."""
    if sort_by == "booked_at_asc":
        return Transaction.booked_at, lambda c: c.asc()
    if sort_by == "amount_desc":
        return Transaction.amount, lambda c: c.desc()
    if sort_by == "amount_asc":
        return Transaction.amount, lambda c: c.asc()
    if sort_by == "abs_amount_desc":
        return func.abs(Transaction.amount), lambda c: c.desc()
    return Transaction.booked_at, lambda c: c.desc()  # booked_at_desc default


def _encode_cursor(primary_value, txn_id: str) -> str:
    payload = {"v": str(primary_value), "id": txn_id}
    return base64.urlsafe_b64encode(json.dumps(payload).encode()).decode()


def _decode_cursor(cursor: str) -> tuple[str, str]:
    payload = json.loads(base64.urlsafe_b64decode(cursor.encode()).decode())
    return payload["v"], payload["id"]


def _paginate_query(query, cursor: Optional[str], sort_by: SortBy, limit: int):
    """Apply sort and (optionally) cursor filter. Returns ordered, limited query."""
    primary_col, direction = _sort_expr(sort_by)
    if cursor:
        try:
            v, last_id = _decode_cursor(cursor)
        except Exception:
            raise ValueError("Invalid cursor")
        # Coerce the primary value to a type Postgres can compare against the
        # primary column: timestamps must not be compared as strings, and
        # numeric columns are safer as Decimal/float.
        if sort_by in ("booked_at_desc", "booked_at_asc"):
            v = datetime.fromisoformat(v)
        else:
            v = Decimal(v)
        # Sort-aware cursor filter: rows "after" (primary, id) tuple
        is_desc = sort_by in ("booked_at_desc", "amount_desc", "abs_amount_desc")
        if is_desc:
            query = query.filter(
                or_(primary_col < v, and_(primary_col == v, Transaction.id < last_id))
            )
        else:
            query = query.filter(
                or_(primary_col > v, and_(primary_col == v, Transaction.id > last_id))
            )
    return query.order_by(direction(primary_col), direction(Transaction.id)).limit(limit)


def _build_next_cursor(rows: list, sort_by: SortBy, limit: int) -> Optional[str]:
    if len(rows) < limit:
        return None
    last = rows[-1]
    # Extract raw primary value for the sort mode
    if sort_by in ("booked_at_desc", "booked_at_asc"):
        v = last.booked_at.isoformat()
    elif sort_by == "abs_amount_desc":
        v = str(abs(float(last.amount)))
    else:
        v = str(float(last.amount))
    return _encode_cursor(v, str(last.id))


def list_transactions(
    user_id: str,
    account_id: Optional[str] = None,
    category_id: Optional[str] = None,
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    search: Optional[str] = None,
    limit: int = 50,
    page: int = 1,
    cursor: Optional[str] = None,
    sort_by: SortBy = "booked_at_desc",
    uncategorized: bool = False,
    category_type: Optional[Literal["expense", "income", "transfer"]] = None,
) -> dict:
    """
    List transactions with optional filtering, cursor pagination, and sort.

    Args:
        user_id: The user's ID
        account_id: Filter by account ID (optional)
        category_id: Filter by category ID (optional)
        from_date: Start date in ISO format (optional)
        to_date: End date in ISO format (optional)
        search: Search in description/merchant (optional)
        limit: Max results per page (default: 50, max: 100)
        page: Page number (default: 1) - ignored when cursor is provided
        cursor: Opaque pagination cursor (preferred over page)
        sort_by: Sort order - one of booked_at_desc (default),
            booked_at_asc, amount_desc, amount_asc, abs_amount_desc
        uncategorized: If True, return only transactions with no category
        category_type: Filter by resolved category type
            (expense, income, transfer)

    Returns:
        Dict with:
        - transactions: list of transaction dicts
        - page: current page (None when cursor-paginated)
        - limit: effective page size
        - next_cursor: opaque cursor for the next page (None when exhausted)
    """
    page = max(1, page)
    limit = min(max(1, limit), 100)
    account_uuid = validate_uuid(account_id) if account_id else None
    category_uuid = validate_uuid(category_id) if category_id else None
    from_dt = validate_date(from_date)
    to_dt = validate_date(to_date)

    with get_db() as db:
        query = (
            db.query(Transaction)
            .filter(Transaction.user_id == user_id)
            .options(joinedload(Transaction.account), joinedload(Transaction.category))
        )
        if account_uuid:
            query = query.filter(Transaction.account_id == account_uuid)
        if category_uuid:
            query = query.filter(
                (Transaction.category_id == category_uuid) |
                and_(
                    Transaction.category_id.is_(None),
                    Transaction.category_system_id == category_uuid
                )
            )
        if uncategorized:
            query = query.filter(
                Transaction.category_id.is_(None),
                Transaction.category_system_id.is_(None),
            )
        if category_type:
            query = query.join(
                Category,
                Category.id == func.coalesce(
                    Transaction.category_id, Transaction.category_system_id
                ),
            ).filter(Category.category_type == category_type)
        if from_dt:
            query = query.filter(Transaction.booked_at >= from_dt)
        if to_dt:
            query = query.filter(Transaction.booked_at <= to_dt)
        if search:
            search_term = f"%{search[:500]}%"
            query = query.filter(
                or_(
                    Transaction.description.ilike(search_term),
                    Transaction.merchant.ilike(search_term),
                )
            )

        if cursor:
            paginated = _paginate_query(query, cursor, sort_by, limit)
        else:
            offset = (page - 1) * limit
            primary_col, direction = _sort_expr(sort_by)
            paginated = (
                query.order_by(direction(primary_col), direction(Transaction.id))
                .offset(offset)
                .limit(limit)
            )
        transactions_rows = paginated.all()
        next_cursor = _build_next_cursor(transactions_rows, sort_by, limit)

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
                    "category_system_id": str(txn.category_system_id) if txn.category_system_id else None,
                    "category_name": txn.category.name if txn.category else None,
                    "booked_at": txn.booked_at.isoformat() if txn.booked_at else None,
                    "pending": txn.pending,
                    "transaction_type": txn.transaction_type,
                    "include_in_analytics": txn.include_in_analytics,
                    "recurring_transaction_id": str(txn.recurring_transaction_id) if txn.recurring_transaction_id else None,
                }
                for txn in transactions_rows
            ],
            "page": page if not cursor else None,
            "limit": limit,
            "next_cursor": next_cursor,
        }


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
    page: int = 1,
    cursor: Optional[str] = None,
    sort_by: SortBy = "booked_at_desc",
    account_id: Optional[str] = None,
) -> dict:
    """
    Search transactions by description or merchant name.

    ⚠️ PAGINATION: Check `has_more` in the response! If true, call again with
    page=2, page=3, etc. until has_more=false to get all results.
    Prefer `cursor`/`next_cursor` for stable pagination over large result sets.

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
        page: Page number (default: 1) - ignored when cursor is provided
        cursor: Opaque pagination cursor (preferred over page)
        sort_by: Sort order - one of booked_at_desc (default),
            booked_at_asc, amount_desc, amount_asc, abs_amount_desc
        account_id: Filter results to a single account (optional)

    Returns:
        Dict with:
        - transactions: List of matching transactions (or transaction_ids if ids_only=True)
        - page: Current page number (None when cursor-paginated)
        - limit: Results per page
        - has_more: Boolean - if true, more results exist
        - total_count: Total number of matching transactions across all pages
        - next_cursor: Opaque cursor for the next page (None when exhausted)
    """
    page = max(1, page)
    limit = min(max(1, limit), 100)

    # Limit search string length to prevent excessive memory usage
    query_str = query[:500] if query else ""

    # Validate IDs if provided
    exclude_cat_uuid = validate_uuid(exclude_category_id) if exclude_category_id else None
    account_uuid = validate_uuid(account_id) if account_id else None

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

        # Add account filter if specified
        if account_uuid:
            base_filter = and_(base_filter, Transaction.account_id == account_uuid)

        # Get total count first
        total_count = db.query(func.count(Transaction.id)).filter(base_filter).scalar()

        # Build base query object
        query_obj = db.query(Transaction).filter(base_filter)

        # Only load relationships if we need full data
        if not ids_only:
            query_obj = query_obj.options(
                joinedload(Transaction.account),
                joinedload(Transaction.category)
            )

        # Apply cursor or offset pagination
        if cursor:
            paginated = _paginate_query(query_obj, cursor, sort_by, limit)
        else:
            offset = (page - 1) * limit
            primary_col, direction = _sort_expr(sort_by)
            paginated = (
                query_obj.order_by(direction(primary_col), direction(Transaction.id))
                .offset(offset)
                .limit(limit)
            )

        rows = paginated.all()
        next_cursor = _build_next_cursor(rows, sort_by, limit)
        has_more = next_cursor is not None if cursor else ((page - 1) * limit + len(rows) < total_count)

        if ids_only:
            return {
                "transaction_ids": [str(t.id) for t in rows],
                "page": page if not cursor else None,
                "limit": limit,
                "has_more": has_more,
                "total_count": total_count,
                "next_cursor": next_cursor,
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
                for txn in rows
            ],
            "page": page if not cursor else None,
            "limit": limit,
            "has_more": has_more,
            "total_count": total_count,
            "next_cursor": next_cursor,
        }


def search_transactions_multi(
    user_id: str,
    queries: list[str],
    exclude_category_id: Optional[str] = None,
    match_mode: MatchMode = "contains",
    ids_only: bool = False,
    max_results: int = 500,
    cursor: Optional[str] = None,
    sort_by: SortBy = "booked_at_desc",
    account_id: Optional[str] = None,
) -> dict:
    """
    Search transactions matching ANY of the given queries.

    Returns all matching transactions in a single call (no pagination needed).
    Useful for bulk recategorization workflows where you need to find transactions
    from multiple merchants at once.

    Pass `cursor=""` (or a real cursor from `next_cursor`) to enable cursor
    pagination. Without a cursor, all results up to `max_results` are returned
    in one shot (original behavior).

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
        cursor: Opaque pagination cursor; pass "" or a real cursor to enable
            cursor mode (opt-in). Omit entirely for legacy all-at-once behavior.
        sort_by: Sort order - one of booked_at_desc (default),
            booked_at_asc, amount_desc, amount_asc, abs_amount_desc
        account_id: Filter results to a single account (optional)

    Returns:
        Dict with:
        - transactions (or transaction_ids if ids_only): All matching transactions
        - total_count: Total matches found
        - capped: True if results were limited by max_results
        - query_counts: Dict mapping each query to its match count
        - next_cursor: Opaque cursor for next page (only present in cursor mode)
    """
    if not queries:
        return {"error": "Must provide at least one query", "success": False}

    max_results = min(max(1, max_results), 1000)

    # Validate IDs if provided
    exclude_cat_uuid = validate_uuid(exclude_category_id) if exclude_category_id else None
    account_uuid = validate_uuid(account_id) if account_id else None

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

        # Add account filter if specified
        if account_uuid:
            combined_filter = and_(combined_filter, Transaction.account_id == account_uuid)

        # Get total count
        total_count = db.query(func.count(Transaction.id)).filter(combined_filter).scalar()

        # Build query object
        query_obj = db.query(Transaction).filter(combined_filter)

        if not ids_only:
            query_obj = query_obj.options(
                joinedload(Transaction.account),
                joinedload(Transaction.category)
            )

        # cursor is not None means cursor mode is opted-in (even empty string)
        cursor_mode = cursor is not None
        if cursor_mode:
            paginated = _paginate_query(query_obj, cursor or None, sort_by, max_results)
        else:
            primary_col, direction = _sort_expr(sort_by)
            paginated = query_obj.order_by(direction(primary_col), direction(Transaction.id)).limit(max_results)

        transactions_rows = paginated.all()
        next_cursor = _build_next_cursor(transactions_rows, sort_by, max_results) if cursor_mode else None

        # Count matches per query (for transparency)
        query_counts = {}
        for q in queries:
            q_str = q[:500] if q else ""
            if q_str:
                q_filter = and_(
                    Transaction.user_id == user_id,
                    _build_search_filter(q_str, match_mode)
                )
                if account_uuid:
                    q_filter = and_(q_filter, Transaction.account_id == account_uuid)
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
            "capped": (not cursor_mode) and (len(transactions_rows) >= max_results) and (total_count > max_results),
            "query_counts": query_counts,
            "next_cursor": next_cursor,
        }

        if ids_only:
            result["transaction_ids"] = [str(txn.id) for txn in transactions_rows]
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
                for txn in transactions_rows
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
    transaction_ids: list[str],
    dry_run: bool = False,
) -> dict:
    """
    Bulk update category for multiple transactions.

    Args:
        user_id: The user's ID
        category_id: The category ID to assign
        transaction_ids: List of transaction IDs to update (max 2000)
        dry_run: If True, preview the change without committing

    Returns:
        Dict with success flag and:
        - updated_count (or would_update_count if dry_run)
        - requested_count, invalid_ids, not_found_ids,
          skipped_already_in_category_ids, sample_changes
    """
    MAX_IDS = 2000
    if not transaction_ids:
        return {"success": False, "error": "Must provide transaction_ids"}
    if len(transaction_ids) > MAX_IDS:
        return {
            "success": False,
            "error": f"Too many transaction_ids ({len(transaction_ids)}). Max {MAX_IDS} per call.",
        }

    cat_uuid = validate_uuid(category_id)
    if not cat_uuid:
        return {"success": False, "error": "Invalid category ID format"}

    with get_db() as db:
        # Verify category belongs to user
        category = db.query(Category).filter(
            Category.id == cat_uuid,
            Category.user_id == user_id,
        ).first()

        if not category:
            return {"success": False, "error": "Category not found"}

        valid_uuids = []
        invalid_ids = []
        for tid in transaction_ids:
            u = validate_uuid(tid)
            if u:
                valid_uuids.append(u)
            else:
                invalid_ids.append(tid)

        found = (
            db.query(Transaction)
            .filter(
                Transaction.user_id == user_id,
                Transaction.id.in_(valid_uuids),
            )
            .options(joinedload(Transaction.category))
            .all()
        ) if valid_uuids else []

        found_by_id = {str(t.id): t for t in found}
        not_found_ids = [str(u) for u in valid_uuids if str(u) not in found_by_id]

        to_change = []
        skipped_already = []
        for t in found:
            if t.category_id == cat_uuid:
                skipped_already.append(str(t.id))
            else:
                to_change.append(t)

        sample_changes = [
            {
                "id": str(t.id),
                "description": t.description,
                "merchant": t.merchant,
                "amount": float(t.amount),
                "previous_category_name": t.category.name if t.category else None,
            }
            for t in sorted(to_change, key=lambda t: (t.booked_at, t.id))[:10]
        ]

        base_response = {
            "success": True,
            "category_name": category.name,
            "requested_count": len(transaction_ids),
            "invalid_ids": invalid_ids,
            "not_found_ids": not_found_ids,
            "skipped_already_in_category_ids": skipped_already,
            "sample_changes": sample_changes,
        }

        if dry_run:
            base_response["would_update_count"] = len(to_change)
            return base_response

        try:
            change_uuids = [t.id for t in to_change]
            updated = 0
            if change_uuids:
                updated = db.query(Transaction).filter(
                    Transaction.user_id == user_id,
                    Transaction.id.in_(change_uuids),
                ).update({Transaction.category_id: cat_uuid}, synchronize_session=False)
                db.commit()
        except Exception as e:
            db.rollback()
            return {"success": False, "error": f"Database error: {str(e)}"}

        base_response["updated_count"] = updated
        return base_response
