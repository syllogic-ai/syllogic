"""
Recurring transaction tools for the MCP server.
"""
from typing import Optional

from sqlalchemy.orm import joinedload

from app.mcp.dependencies import get_db, validate_uuid
from app.models import RecurringTransaction


def list_recurring_transactions(
    user_id: str,
    is_active: Optional[bool] = None
) -> list[dict]:
    """
    List recurring transactions (subscriptions/bills) for a user.

    Args:
        user_id: The user's ID
        is_active: Filter by active status (optional, defaults to showing all)

    Returns:
        List of recurring transactions with details
    """
    with get_db() as db:
        query = db.query(RecurringTransaction).filter(
            RecurringTransaction.user_id == user_id
        ).options(joinedload(RecurringTransaction.category))

        if is_active is not None:
            query = query.filter(RecurringTransaction.is_active == is_active)

        recurring = query.order_by(RecurringTransaction.name).all()

        return [
            {
                "id": str(r.id),
                "name": r.name,
                "merchant": r.merchant,
                "amount": float(r.amount),
                "currency": r.currency,
                "frequency": r.frequency,
                "importance": r.importance,
                "is_active": r.is_active,
                "description": r.description,
                "category_id": str(r.category_id) if r.category_id else None,
                "category_name": r.category.name if r.category else None,
                "created_at": r.created_at.isoformat() if r.created_at else None,
                "updated_at": r.updated_at.isoformat() if r.updated_at else None,
            }
            for r in recurring
        ]


def get_recurring_transaction(
    user_id: str,
    recurring_id: str
) -> dict | None:
    """
    Get a single recurring transaction by ID.

    Args:
        user_id: The user's ID
        recurring_id: The recurring transaction's ID

    Returns:
        Recurring transaction dictionary or None if not found
    """
    recurring_uuid = validate_uuid(recurring_id)
    if not recurring_uuid:
        return None

    with get_db() as db:
        recurring = (
            db.query(RecurringTransaction)
            .filter(
                RecurringTransaction.id == recurring_uuid,
                RecurringTransaction.user_id == user_id
            )
            .options(joinedload(RecurringTransaction.category))
            .first()
        )

        if not recurring:
            return None

        return {
            "id": str(recurring.id),
            "name": recurring.name,
            "merchant": recurring.merchant,
            "amount": float(recurring.amount),
            "currency": recurring.currency,
            "frequency": recurring.frequency,
            "importance": recurring.importance,
            "is_active": recurring.is_active,
            "description": recurring.description,
            "category_id": str(recurring.category_id) if recurring.category_id else None,
            "category_name": recurring.category.name if recurring.category else None,
            "created_at": recurring.created_at.isoformat() if recurring.created_at else None,
            "updated_at": recurring.updated_at.isoformat() if recurring.updated_at else None,
        }


def get_recurring_summary(user_id: str) -> dict:
    """
    Get a summary of recurring transactions (subscriptions/bills).

    Args:
        user_id: The user's ID

    Returns:
        Summary with totals by frequency and overall statistics
    """
    with get_db() as db:
        recurring = db.query(RecurringTransaction).filter(
            RecurringTransaction.user_id == user_id,
            RecurringTransaction.is_active == True
        ).all()

        # Calculate monthly equivalent for each frequency
        frequency_multipliers = {
            "weekly": 4.33,      # ~4.33 weeks per month
            "biweekly": 2.17,   # ~2.17 biweeks per month
            "monthly": 1,
            "quarterly": 0.33,   # 1/3 of a quarter
            "yearly": 0.083,     # 1/12 of a year
        }

        total_monthly = 0
        by_frequency = {}
        by_importance = {1: [], 2: [], 3: [], 4: [], 5: []}

        for r in recurring:
            multiplier = frequency_multipliers.get(r.frequency, 1)
            monthly_amount = float(r.amount) * multiplier
            total_monthly += monthly_amount

            # Group by frequency
            if r.frequency not in by_frequency:
                by_frequency[r.frequency] = {"count": 0, "total": 0, "monthly_equivalent": 0}
            by_frequency[r.frequency]["count"] += 1
            by_frequency[r.frequency]["total"] += float(r.amount)
            by_frequency[r.frequency]["monthly_equivalent"] += monthly_amount

            # Group by importance
            importance = r.importance or 3
            if importance in by_importance:
                by_importance[importance].append({
                    "name": r.name,
                    "amount": float(r.amount),
                    "frequency": r.frequency,
                })

        return {
            "total_active": len(recurring),
            "total_monthly_cost": round(total_monthly, 2),
            "total_yearly_cost": round(total_monthly * 12, 2),
            "by_frequency": by_frequency,
            "by_importance": {
                k: v for k, v in by_importance.items() if v
            },
        }
