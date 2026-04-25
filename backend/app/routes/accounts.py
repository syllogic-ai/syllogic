import re
from decimal import Decimal
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session
from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError
from typing import List, Optional
from uuid import UUID

from app.database import get_db
from app.models import Account, Transaction
from app.db_helpers import get_user_id
from app.schemas import AccountCreate, AccountResponse, AccountUpdate
from app.security.data_encryption import (
    blind_index,
    blind_index_candidates,
    decrypt_with_fallback,
    encrypt_value,
)
from app.services.internal_transfer_service import InternalTransferService

router = APIRouter()


# ---------------------------------------------------------------------------
# Pocket account registration
# ---------------------------------------------------------------------------

_IBAN_RE = re.compile(r"^[A-Z]{2}\d{2}[A-Z0-9]{10,30}$")


class CreatePocketRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    account_type: str = "savings"
    currency: str = "EUR"
    starting_balance: Decimal = Decimal("0")
    iban: str

    @field_validator("iban")
    @classmethod
    def _normalize_iban(cls, v: str) -> str:
        norm = v.replace(" ", "").upper()
        if not (15 <= len(norm) <= 34) or not _IBAN_RE.match(norm):
            raise ValueError("Invalid IBAN format")
        return norm


class CreatePocketResponse(BaseModel):
    account_id: UUID
    backfilled_count: int


@router.post("/pocket", response_model=CreatePocketResponse)
def create_pocket_account(
    payload: CreatePocketRequest,
    user_id: str = Depends(get_user_id),
    db: Session = Depends(get_db),
):
    """
    Create a manual pocket account identified by IBAN and immediately backfill
    any pre-existing transactions whose counterparty IBAN matches.

    Pockets are user-owned, manually-registered accounts (provider="manual")
    used to represent money parked in a non-synced account the user transfers
    to/from from a synced account. Matching is done via blind-indexed IBAN
    hash so the plaintext IBAN is never compared directly.
    """
    iban_hash = blind_index(payload.iban)
    if iban_hash is None:
        raise HTTPException(
            status_code=500,
            detail="Encryption not configured — cannot register pocket",
        )

    # Scope the duplicate check to manual pockets only. If the user's synced
    # bank accounts ever gain an iban_hash (not today), we still want this
    # endpoint to refuse only pocket-vs-pocket collisions — not block a
    # pocket from sharing an IBAN with a synced account.
    existing = (
        db.query(Account)
        .filter(
            Account.user_id == user_id,
            Account.iban_hash == iban_hash,
            Account.provider == "manual",
        )
        .first()
    )
    if existing is not None:
        raise HTTPException(
            status_code=400,
            detail="A pocket account with this IBAN is already registered",
        )

    account = Account(
        user_id=user_id,
        name=payload.name,
        account_type=payload.account_type,
        currency=payload.currency,
        provider="manual",
        starting_balance=payload.starting_balance,
        functional_balance=payload.starting_balance,
        iban_ciphertext=encrypt_value(payload.iban),
        iban_hash=iban_hash,
        is_active=True,
    )
    db.add(account)
    try:
        db.flush()
    except IntegrityError:
        # Race condition: two concurrent pocket-create requests slipped past the
        # application-level SELECT check. The partial unique index
        # `accounts_user_iban_hash_manual_uq` catches this at the DB layer.
        db.rollback()
        raise HTTPException(
            status_code=400,
            detail="A pocket account with this IBAN is already registered",
        )

    # Backfill: find existing transactions whose counterparty matches this IBAN
    candidate_ids = [
        row[0]
        for row in db.query(Transaction.id)
        .filter(
            Transaction.user_id == user_id,
            Transaction.counterparty_iban_hash == iban_hash,
            Transaction.internal_transfer_id.is_(None),
        )
        .all()
    ]
    # Commit semantics: InternalTransferService.detect_for_transactions commits
    # internally when it actually persists matches (detected > 0). We still
    # commit here unconditionally so the new Account row is persisted even on
    # the zero-match path. A redundant commit on a clean session is a no-op.
    if candidate_ids:
        result = InternalTransferService(db, user_id=user_id).detect_for_transactions(candidate_ids)
        backfilled_count = result["detected"]
    else:
        backfilled_count = 0
    db.commit()

    return CreatePocketResponse(account_id=account.id, backfilled_count=backfilled_count)


# ---------------------------------------------------------------------------
# Internal transfer unlink
# ---------------------------------------------------------------------------


@router.delete(
    "/internal-transfers/{transfer_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def unlink_internal_transfer(
    transfer_id: UUID,
    user_id: str = Depends(get_user_id),
    db: Session = Depends(get_db),
):
    """Unlink a detected internal transfer.

    Deletes the mirror transaction, clears the source's ``internal_transfer_id``
    and sets ``include_in_analytics=True``, then deletes the ``internal_transfers``
    row. The ``InternalTransferService.unlink`` method silently no-ops if the id
    is unknown or belongs to a different user, so we return 204 unconditionally
    — this is intentional and does not leak info (users can't learn whether a
    link exists for another user).
    """
    InternalTransferService(db, user_id=user_id).unlink(transfer_id)
    return None


def _serialize_account(account: Account) -> AccountResponse:
    return AccountResponse(
        id=account.id,
        name=account.name,
        account_type=account.account_type,
        institution=account.institution,
        currency=account.currency,
        is_active=account.is_active,
        alias_patterns=account.alias_patterns or [],
        provider=account.provider,
        external_id=decrypt_with_fallback(account.external_id_ciphertext, account.external_id),
        created_at=account.created_at,
        updated_at=account.updated_at,
    )


@router.get("/", response_model=List[AccountResponse])
def list_accounts(
    include_inactive: bool = Query(True, description="Include inactive accounts"),
    user_id: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """
    List all accounts for the current user.
    
    Args:
        include_inactive: If True, includes inactive accounts. Default: True (show all accounts).
        user_id: User ID (optional, defaults to system user)
    """
    user_id = get_user_id(user_id)
    query = db.query(Account).filter(Account.user_id == user_id)
    
    if not include_inactive:
        # Only show active accounts if explicitly requested
        query = query.filter(Account.is_active == True)
    
    excluded_external_ids = ["revolut_default", "default"]
    excluded_hashes: list[str] = []
    for external_id in excluded_external_ids:
        excluded_hashes.extend(blind_index_candidates(external_id))
    excluded_hashes = list(dict.fromkeys(excluded_hashes))

    query = query.filter(
        or_(
            Account.external_id.is_(None),
            Account.external_id.notin_(excluded_external_ids),
        )
    )
    if excluded_hashes:
        query = query.filter(
            or_(
                Account.external_id_hash.is_(None),
                Account.external_id_hash.notin_(excluded_hashes),
            )
        )

    accounts = query.order_by(Account.created_at.desc()).all()
    return [_serialize_account(account) for account in accounts]


@router.get("/{account_id}", response_model=AccountResponse)
def get_account(
    account_id: UUID,
    user_id: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """Get a specific account by ID."""
    user_id = get_user_id(user_id)
    account = db.query(Account).filter(
        Account.id == account_id,
        Account.user_id == user_id
    ).first()
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")
    return _serialize_account(account)


@router.post("/", response_model=AccountResponse, status_code=201)
def create_account(
    account: AccountCreate,
    user_id: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """Create a new account."""
    user_id = get_user_id(user_id)
    account_data = account.model_dump()
    account_data["user_id"] = user_id
    db_account = Account(**account_data)
    db.add(db_account)
    db.commit()
    db.refresh(db_account)
    return _serialize_account(db_account)


@router.patch("/{account_id}", response_model=AccountResponse)
def update_account(
    account_id: UUID,
    updates: AccountUpdate,
    user_id: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """Update an account."""
    user_id = get_user_id(user_id)
    account = db.query(Account).filter(
        Account.id == account_id,
        Account.user_id == user_id
    ).first()
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")

    update_data = updates.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(account, field, value)

    db.commit()
    db.refresh(account)
    return _serialize_account(account)


@router.delete("/{account_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_account(
    account_id: UUID,
    user_id: str = Depends(get_user_id),
    db: Session = Depends(get_db),
):
    """Hard-delete an account.

    For pocket accounts (``provider="manual"``) with linked internal transfers,
    unlink the source transactions first (restoring ``include_in_analytics=True``
    and clearing ``internal_transfer_id``) so the cascade that follows doesn't
    leave orphan sources with stale analytics flags. Child transactions are
    removed by the ``ON DELETE CASCADE`` on ``transactions.account_id``;
    ``Account.transactions`` uses ``passive_deletes=True`` so SQLAlchemy defers
    to the DB cascade instead of trying to NULL the children.

    For non-pocket accounts ``unlink_all_for_pocket`` is a no-op (no links point
    at them by definition).
    """
    account = (
        db.query(Account)
        .filter(Account.id == account_id, Account.user_id == user_id)
        .one_or_none()
    )
    if account is None:
        raise HTTPException(status_code=404, detail="Account not found")

    InternalTransferService(db, user_id=user_id).unlink_all_for_pocket(account_id)

    db.delete(account)
    db.commit()
    return None


@router.delete("/cleanup/revolut-default", status_code=200)
def delete_revolut_default_accounts(
    user_id: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """
    Permanently delete all "Revolut default" accounts for the current user.
    This is a hard delete - use with caution.
    """
    user_id = get_user_id(user_id)

    # Find all revolut_default accounts for this user
    default_accounts = db.query(Account).filter(
        Account.user_id == user_id,
        or_(
            Account.external_id == "revolut_default",
            Account.external_id_hash.in_(blind_index_candidates("revolut_default")),
        )
    ).all()

    deleted_count = 0
    for account in default_accounts:
        db.delete(account)
        deleted_count += 1

    db.commit()
    
    return {
        "message": f"Deleted {deleted_count} 'Revolut default' account(s) and their transactions",
        "deleted_count": deleted_count
    }




@router.post("/{account_id}/recalculate-balance", status_code=200)
def recalculate_account_balance(
    account_id: UUID,
    user_id: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """
    Recalculate account balance from sum of all transactions.
    """
    from app.models import Transaction
    from sqlalchemy import func
    user_id = get_user_id(user_id)

    account = db.query(Account).filter(
        Account.id == account_id,
        Account.user_id == user_id
    ).first()
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")

    # Calculate balance from sum of all transactions
    balance_sum = db.query(func.sum(Transaction.amount)).filter(
        Transaction.user_id == user_id,
        Transaction.account_id == account.id
    ).scalar() or 0

    account.balance_current = balance_sum
    db.commit()
    db.refresh(account)

    return {
        "message": f"Recalculated balance for '{account.name}'",
        "account_id": str(account.id),
        "account_name": account.name,
        "new_balance": float(account.balance_current),
        "currency": account.currency
    }


@router.post("/{account_id}/recalculate-starting-balance", status_code=200)
def recalculate_starting_balance(
    account_id: UUID,
    known_balance: float = Query(..., description="The known current balance to use for recalculation"),
    user_id: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """
    Recalculate starting balance based on a known current balance.

    This is useful when importing historical transactions - the starting_balance
    should represent the balance BEFORE the first transaction, calculated as:
    starting_balance = known_current_balance - sum(all_transactions)
    """
    from app.models import Transaction
    from sqlalchemy import func
    from decimal import Decimal
    user_id = get_user_id(user_id)

    account = db.query(Account).filter(
        Account.id == account_id,
        Account.user_id == user_id
    ).first()
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")

    # Calculate sum of all transactions for this account
    transaction_sum = db.query(func.sum(Transaction.amount)).filter(
        Transaction.user_id == user_id,
        Transaction.account_id == account.id
    ).scalar() or Decimal("0")

    # Calculate new starting balance
    # known_current_balance = starting_balance + transaction_sum
    # Therefore: starting_balance = known_current_balance - transaction_sum
    new_starting_balance = Decimal(str(known_balance)) - transaction_sum

    # Update account
    account.starting_balance = new_starting_balance
    account.functional_balance = Decimal(str(known_balance))
    db.commit()
    db.refresh(account)

    return {
        "message": f"Recalculated starting balance for '{account.name}'",
        "account_id": str(account.id),
        "account_name": account.name,
        "known_current_balance": known_balance,
        "transaction_sum": float(transaction_sum),
        "new_starting_balance": float(new_starting_balance),
        "new_functional_balance": float(account.functional_balance) if account.functional_balance else None,
        "currency": account.currency
    }


@router.post("/{account_id}/recalculate-timeseries", status_code=200)
def recalculate_account_timeseries(
    account_id: UUID,
    user_id: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """
    Recalculate daily balance timeseries for a specific account.

    This endpoint:
    - Calculates balance for each day from the first transaction to today
    - Stores daily snapshots in the account_balances table
    - Converts to functional currency using date-specific exchange rates
    - Updates existing records or creates new ones
    """
    from app.services.account_balance_service import AccountBalanceService
    user_id = get_user_id(user_id)

    # Verify account exists and belongs to user
    account = db.query(Account).filter(
        Account.id == account_id,
        Account.user_id == user_id
    ).first()
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")

    # Calculate timeseries for this specific account
    balance_service = AccountBalanceService(db)
    result = balance_service.calculate_account_timeseries(user_id, account_ids=[account_id])

    if "error" in result:
        raise HTTPException(status_code=500, detail=result["error"])

    return {
        "message": f"Recalculated timeseries for '{account.name}'",
        "account_id": str(account.id),
        "account_name": account.name,
        "days_processed": result.get("total_days_processed", 0),
        "records_stored": result.get("total_records_stored", 0),
        "currency": account.currency
    }


@router.delete("/cleanup/empty-accounts", status_code=200)
def delete_empty_accounts(
    user_id: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """
    Automatically delete all accounts that have 0 transactions for the current user.
    This is useful for cleaning up accounts that were created but never used.
    """
    from app.models import Transaction
    from sqlalchemy import func
    user_id = get_user_id(user_id)
    
    # Find all accounts for this user
    all_accounts = db.query(Account).filter(Account.user_id == user_id).all()
    deleted_count = 0
    deleted_accounts = []
    
    for account in all_accounts:
        # Count transactions for this account
        transaction_count = db.query(Transaction).filter(
            Transaction.user_id == user_id,
            Transaction.account_id == account.id
        ).count()
        
        if transaction_count == 0:
            # Delete the account (transactions are already 0, so no need to delete them)
            deleted_accounts.append(account.name)
            db.delete(account)
            deleted_count += 1
    
    if deleted_count > 0:
        db.commit()
    
    return {
        "message": f"Deleted {deleted_count} account(s) with 0 transactions",
        "deleted_count": deleted_count,
        "deleted_accounts": deleted_accounts
    }


@router.post("/restore-seed", status_code=200)
def restore_seed_accounts(
    user_id: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """
    Restore seed accounts (Main Checking, Savings, Credit Card) if they don't exist.
    Only creates accounts that don't already exist for the current user.
    """
    from decimal import Decimal
    user_id = get_user_id(user_id)
    
    seed_accounts_data = [
        {
            "name": "Main Checking",
            "account_type": "checking",
            "institution": "Revolut",
            "currency": "EUR",
            "balance_current": Decimal("3245.67"),
        },
        {
            "name": "Savings",
            "account_type": "savings",
            "institution": "Revolut",
            "currency": "EUR",
        },
        {
            "name": "Credit Card",
            "account_type": "credit",
            "institution": "Visa",
            "currency": "EUR",
        },
    ]
    
    created_count = 0
    for account_data in seed_accounts_data:
        # Check if account with this name already exists
        existing = db.query(Account).filter(
            Account.name == account_data["name"],
            Account.is_active == True
        ).first()
        
        if not existing:
            account_data["user_id"] = user_id
            new_account = Account(**account_data)
            db.add(new_account)
            created_count += 1
    
    db.commit()
    
    return {
        "message": f"Restored {created_count} seed account(s)",
        "created_count": created_count
    }
