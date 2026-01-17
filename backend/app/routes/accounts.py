from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from uuid import UUID

from app.database import get_db
from app.models import Account
from app.db_helpers import get_user_id
from app.schemas import AccountCreate, AccountResponse, AccountUpdate

router = APIRouter()


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
    
    # Always exclude "revolut_default" accounts (they should be deleted, not just hidden)
    # Also exclude accounts with external_id == 'default' (old format)
    # Use or_() to handle NULL values correctly - NULL != 'value' evaluates to NULL in SQL
    from sqlalchemy import or_
    query = query.filter(
        or_(
            Account.external_id.is_(None),  # Include accounts with no external_id
            Account.external_id.notin_(['revolut_default', 'default'])  # Exclude these specific values
        )
    )
    
    accounts = query.order_by(Account.created_at.desc()).all()
    return accounts


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
    return account


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
    return db_account


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
    return account


@router.delete("/{account_id}", status_code=204)
def delete_account(
    account_id: UUID,
    user_id: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """Delete (deactivate) an account."""
    user_id = get_user_id(user_id)
    account = db.query(Account).filter(
        Account.id == account_id,
        Account.user_id == user_id
    ).first()
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")

    account.is_active = False
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
    from app.models import Transaction
    user_id = get_user_id(user_id)
    
    # Find all revolut_default accounts for this user
    default_accounts = db.query(Account).filter(
        Account.user_id == user_id,
        Account.external_id == 'revolut_default'
    ).all()
    
    deleted_count = 0
    for account in default_accounts:
        # Delete associated transactions first (due to foreign key constraint)
        db.query(Transaction).filter(
            Transaction.user_id == user_id,
            Transaction.account_id == account.id
        ).delete()
        # Then delete the account
        db.delete(account)
        deleted_count += 1
    
    db.commit()
    
    return {
        "message": f"Deleted {deleted_count} 'Revolut default' account(s) and their transactions",
        "deleted_count": deleted_count
    }


@router.get("/debug/all", status_code=200)
def get_all_accounts_debug(
    user_id: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """
    Debug endpoint to see ALL accounts for the current user (including inactive ones).
    Returns detailed information about each account.
    """
    user_id = get_user_id(user_id)
    accounts = db.query(Account).filter(Account.user_id == user_id).all()
    
    result = []
    for account in accounts:
        # Count transactions for this account
        from app.models import Transaction
        transaction_count = db.query(Transaction).filter(
            Transaction.user_id == user_id,
            Transaction.account_id == account.id
        ).count()
        
        result.append({
            "id": str(account.id),
            "name": account.name,
            "account_type": account.account_type,
            "institution": account.institution,
            "currency": account.currency,
            "provider": account.provider,
            "external_id": account.external_id,
            "balance_available": float(account.balance_available) if account.balance_available else None,
            "is_active": account.is_active,
            "transaction_count": transaction_count,
            "created_at": account.created_at.isoformat() if account.created_at else None,
            "updated_at": account.updated_at.isoformat() if account.updated_at else None,
        })
    
    return {
        "total_accounts": len(result),
        "accounts": result
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
