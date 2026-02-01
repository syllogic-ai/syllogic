"""
Transaction tools for the MCP server.
"""
from typing import Optional

from sqlalchemy import or_
from sqlalchemy.orm import joinedload

from app.mcp.dependencies import get_db, validate_uuid, validate_date
from app.models import Transaction, Account, Category


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


def search_transactions(
    user_id: str,
    query: str,
    limit: int = 20
) -> list[dict]:
    """
    Search transactions by description or merchant name.

    Args:
        user_id: The user's ID
        query: Search query string
        limit: Max results (default: 20, max: 50)

    Returns:
        List of matching transactions
    """
    limit = min(max(1, limit), 50)
    # Limit search string length to prevent excessive memory usage
    query = query[:500] if query else ""
    search_term = f"%{query}%"

    with get_db() as db:
        transactions = (
            db.query(Transaction)
            .filter(
                Transaction.user_id == user_id,
                or_(
                    Transaction.description.ilike(search_term),
                    Transaction.merchant.ilike(search_term),
                )
            )
            .options(joinedload(Transaction.account), joinedload(Transaction.category))
            .order_by(Transaction.booked_at.desc())
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
                "category_name": txn.category.name if txn.category else None,
                "booked_at": txn.booked_at.isoformat() if txn.booked_at else None,
            }
            for txn in transactions
        ]


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
