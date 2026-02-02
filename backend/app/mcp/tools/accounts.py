"""
Account tools for the MCP server.
"""
from typing import Optional

from app.mcp.dependencies import get_db, validate_uuid, validate_date
from app.models import Account, AccountBalance


def list_accounts(user_id: str, include_inactive: bool = False) -> list[dict]:
    """
    List all accounts for a user.

    Args:
        user_id: The user's ID
        include_inactive: Whether to include inactive accounts (default: False)

    Returns:
        List of account dictionaries with id, name, type, institution, currency, balance, etc.
    """
    with get_db() as db:
        query = db.query(Account).filter(Account.user_id == user_id)

        if not include_inactive:
            query = query.filter(Account.is_active == True)

        accounts = query.order_by(Account.name).all()

        return [
            {
                "id": str(account.id),
                "name": account.name,
                "account_type": account.account_type,
                "institution": account.institution,
                "currency": account.currency,
                "provider": account.provider,
                "balance_available": float(account.balance_available) if account.balance_available else None,
                "starting_balance": float(account.starting_balance) if account.starting_balance else 0,
                "functional_balance": float(account.functional_balance) if account.functional_balance else None,
                "is_active": account.is_active,
                "last_synced_at": account.last_synced_at.isoformat() if account.last_synced_at else None,
                "created_at": account.created_at.isoformat() if account.created_at else None,
            }
            for account in accounts
        ]


def get_account(user_id: str, account_id: str) -> dict | None:
    """
    Get a single account by ID.

    Args:
        user_id: The user's ID
        account_id: The account's ID

    Returns:
        Account dictionary or None if not found
    """
    account_uuid = validate_uuid(account_id)
    if not account_uuid:
        return None

    with get_db() as db:
        account = db.query(Account).filter(
            Account.id == account_uuid,
            Account.user_id == user_id
        ).first()

        if not account:
            return None

        return {
            "id": str(account.id),
            "name": account.name,
            "account_type": account.account_type,
            "institution": account.institution,
            "currency": account.currency,
            "provider": account.provider,
            "external_id": account.external_id,
            "balance_available": float(account.balance_available) if account.balance_available else None,
            "starting_balance": float(account.starting_balance) if account.starting_balance else 0,
            "functional_balance": float(account.functional_balance) if account.functional_balance else None,
            "is_active": account.is_active,
            "last_synced_at": account.last_synced_at.isoformat() if account.last_synced_at else None,
            "created_at": account.created_at.isoformat() if account.created_at else None,
            "updated_at": account.updated_at.isoformat() if account.updated_at else None,
        }


def get_account_balance_history(
    user_id: str,
    account_id: str,
    from_date: Optional[str] = None,
    to_date: Optional[str] = None
) -> list[dict]:
    """
    Get daily balance history for an account.

    Args:
        user_id: The user's ID
        account_id: The account's ID
        from_date: Start date (ISO format, optional)
        to_date: End date (ISO format, optional)

    Returns:
        List of balance snapshots with date, balance in account currency, and functional currency
    """
    account_uuid = validate_uuid(account_id)
    if not account_uuid:
        return []

    from_dt = validate_date(from_date)
    to_dt = validate_date(to_date)

    with get_db() as db:
        # First verify the account belongs to the user
        account = db.query(Account).filter(
            Account.id == account_uuid,
            Account.user_id == user_id
        ).first()

        if not account:
            return []

        query = db.query(AccountBalance).filter(
            AccountBalance.account_id == account_uuid
        )

        if from_dt:
            query = query.filter(AccountBalance.date >= from_dt)

        if to_dt:
            query = query.filter(AccountBalance.date <= to_dt)

        balances = query.order_by(AccountBalance.date).all()

        return [
            {
                "date": balance.date.isoformat() if balance.date else None,
                "balance_in_account_currency": float(balance.balance_in_account_currency) if balance.balance_in_account_currency else 0,
                "balance_in_functional_currency": float(balance.balance_in_functional_currency) if balance.balance_in_functional_currency else 0,
            }
            for balance in balances
        ]
