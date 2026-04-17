"""
One-off admin endpoints for database cleanup operations.

All routes here are exempt from the internal HMAC middleware and instead
authenticate via a simple Bearer token (INTERNAL_AUTH_SECRET).

Remove this file once cleanup tasks are complete.
"""

import os
import logging
from fastapi import APIRouter, Header, HTTPException
from sqlalchemy.orm import Session
from fastapi import Depends
from pydantic import BaseModel
from typing import Optional

from app.database import get_db

logger = logging.getLogger(__name__)
router = APIRouter()


def _verify_admin_token(authorization: Optional[str] = Header(None)):
    """Verify Bearer token = INTERNAL_AUTH_SECRET."""
    secret = os.environ.get("INTERNAL_AUTH_SECRET", "").strip()
    if not secret:
        raise HTTPException(status_code=500, detail="INTERNAL_AUTH_SECRET not configured")
    expected = f"Bearer {secret}"
    if authorization != expected:
        raise HTTPException(status_code=401, detail="Unauthorized")


class CleanupRequest(BaseModel):
    email: str
    account_name_pattern: str = "Unknown Account%"
    delete_expired_connections: bool = True


@router.post("/cleanup-accounts")
def cleanup_accounts(
    body: CleanupRequest,
    db: Session = Depends(get_db),
    _auth: None = Depends(_verify_admin_token),
):
    """
    Delete accounts matching a name pattern for a specific user.
    Also deletes associated transactions, balances, and optionally expired bank connections.
    """
    from sqlalchemy import text
    from app.models import Account, BankConnection

    # Find user by email
    user_row = db.execute(
        text('SELECT id, email FROM "user" WHERE email = :email'),
        {"email": body.email},
    ).fetchone()

    if not user_row:
        raise HTTPException(status_code=404, detail=f"User {body.email!r} not found")

    user_id = str(user_row[0])

    # Find matching accounts using LIKE pattern
    matching_accounts = db.query(Account).filter(
        Account.user_id == user_id,
        Account.name.like(body.account_name_pattern),
    ).all()

    if not matching_accounts:
        return {
            "message": "No matching accounts found",
            "user_id": user_id,
            "pattern": body.account_name_pattern,
        }

    deleted_accounts = []
    total_txns = 0
    total_balances = 0

    for account in matching_accounts:
        account_id = str(account.id)

        # Delete account balances
        from app.models import AccountBalance
        balance_result = db.query(AccountBalance).filter(
            AccountBalance.account_id == account.id
        ).delete()
        total_balances += balance_result

        # Delete transactions
        from app.models import Transaction
        txn_result = db.query(Transaction).filter(
            Transaction.account_id == account.id,
            Transaction.user_id == user_id,
        ).delete()
        total_txns += txn_result

        # Delete the account
        db.delete(account)
        deleted_accounts.append({"id": account_id, "name": account.name})

    # Optionally delete expired bank connections
    deleted_connections = []
    if body.delete_expired_connections:
        expired = db.query(BankConnection).filter(
            BankConnection.user_id == user_id,
            BankConnection.status == "expired",
        ).all()
        for conn in expired:
            deleted_connections.append({"id": str(conn.id), "aspsp_name": conn.aspsp_name})
            db.delete(conn)

    db.commit()

    logger.info(
        f"Admin cleanup for {body.email}: deleted {len(deleted_accounts)} accounts, "
        f"{total_txns} transactions, {total_balances} balances, "
        f"{len(deleted_connections)} expired connections"
    )

    return {
        "success": True,
        "user_id": user_id,
        "deleted_accounts": deleted_accounts,
        "deleted_transactions_count": total_txns,
        "deleted_balances_count": total_balances,
        "deleted_expired_connections": deleted_connections,
    }
