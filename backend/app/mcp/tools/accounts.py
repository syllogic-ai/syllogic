"""
Account tools for the MCP server.
"""
from typing import Optional

from app.mcp.dependencies import get_db, validate_uuid, validate_date
from app.mcp.tools._asset_class import account_type_to_asset_class
from app.models import Account, AccountBalance
from app.security.data_encryption import decrypt_with_fallback
from app.services.ownership_service import attribute_amount, entity_ids_for_people, get_owners


def list_accounts(
    user_id: str,
    include_inactive: bool = False,
    asset_class: Optional[str] = None,
    person_ids: Optional[list[str]] = None,
) -> list[dict]:
    """
    List all accounts for a user.

    Args:
        user_id: The user's ID
        include_inactive: Whether to include inactive accounts (default: False)
        asset_class: Optional asset-class filter, e.g. "cash", "savings",
            "investment", "crypto", "property", "vehicle", "other".
        person_ids: Optional list of person UUIDs. When provided, only returns
            accounts owned by any of the specified people. When exactly one
            person_id is given, also adds an `attributed_balance` field
            share-weighted to that person's ownership fraction.

    Returns:
        List of account dictionaries with id, name, type, institution, currency,
        balance, asset_class, etc.
    """
    with get_db() as db:
        query = db.query(Account).filter(Account.user_id == user_id)

        if not include_inactive:
            query = query.filter(Account.is_active == True)

        # Apply person_ids ownership filter
        filter_by_person = person_ids is not None and len(person_ids) > 0
        single_person = filter_by_person and len(person_ids) == 1
        allowed_account_ids = None
        if filter_by_person:
            allowed_account_ids = set(
                str(uid) for uid in entity_ids_for_people(db, "account", person_ids)
            )
            if not allowed_account_ids:
                return []
            query = query.filter(Account.id.in_(allowed_account_ids))

        accounts = query.order_by(Account.name).all()

        # Cache owners per account when we need share-weighting (single batch query)
        owners_cache: dict = {}
        if single_person:
            from app.models import AccountOwner
            account_ids = [a.id for a in accounts]
            if account_ids:
                rows = db.query(AccountOwner).filter(AccountOwner.account_id.in_(account_ids)).all()
                for row in rows:
                    owners_cache.setdefault(str(row.account_id), []).append({
                        "person_id": str(row.person_id),
                        "share": float(row.share) if row.share is not None else None,
                    })
            # Ensure every account has an entry (even if empty)
            for a in accounts:
                owners_cache.setdefault(str(a.id), [])

        results = []
        for account in accounts:
            row = {
                "id": str(account.id),
                "name": account.name,
                "account_type": account.account_type,
                "asset_class": account_type_to_asset_class(account.account_type),
                "institution": account.institution,
                "currency": account.currency,
                "provider": account.provider,
                "balance_available": float(account.balance_available) if account.balance_available else None,
                "starting_balance": float(account.starting_balance) if account.starting_balance else 0,
                "functional_balance": float(account.functional_balance) if account.functional_balance else None,
                "is_active": account.is_active,
                "alias_patterns": account.alias_patterns or [],
                "last_synced_at": account.last_synced_at.isoformat() if account.last_synced_at else None,
                "created_at": account.created_at.isoformat() if account.created_at else None,
            }
            if single_person:
                owners = owners_cache[str(account.id)]
                row["owners"] = owners
                if account.functional_balance is not None:
                    full_balance = float(account.functional_balance)
                elif account.balance_available is not None:
                    full_balance = float(account.balance_available)
                else:
                    full_balance = 0.0
                row["attributed_balance"] = attribute_amount(
                    full_balance, owners, person_ids[0]
                )
            results.append(row)

        if asset_class is not None:
            normalized = asset_class.lower()
            results = [r for r in results if r["asset_class"] == normalized]

        return results


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
            "asset_class": account_type_to_asset_class(account.account_type),
            "institution": account.institution,
            "currency": account.currency,
            "provider": account.provider,
            "external_id": decrypt_with_fallback(account.external_id_ciphertext, account.external_id),
            "balance_available": float(account.balance_available) if account.balance_available else None,
            "starting_balance": float(account.starting_balance) if account.starting_balance else 0,
            "functional_balance": float(account.functional_balance) if account.functional_balance else None,
            "is_active": account.is_active,
            "alias_patterns": account.alias_patterns or [],
            "last_synced_at": account.last_synced_at.isoformat() if account.last_synced_at else None,
            "created_at": account.created_at.isoformat() if account.created_at else None,
            "updated_at": account.updated_at.isoformat() if account.updated_at else None,
        }


def get_account_balance_history(
    user_id: str,
    account_id: str,
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    person_ids: Optional[list[str]] = None,
) -> list[dict]:
    """
    Get daily balance history for an account.

    Args:
        user_id: The user's ID
        account_id: The account's ID
        from_date: Start date (ISO format, optional)
        to_date: End date (ISO format, optional)
        person_ids: Optional list of person UUIDs. When provided, returns an
            empty list if the account is not owned by any of those people.

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

        # Apply person_ids ownership filter (filter-only; no attribution on history)
        if person_ids is not None and len(person_ids) > 0:
            allowed_ids = set(
                str(uid) for uid in entity_ids_for_people(db, "account", person_ids)
            )
            if str(account_uuid) not in allowed_ids:
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
