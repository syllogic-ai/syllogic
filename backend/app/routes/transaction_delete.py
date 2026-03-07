"""
Routes for transaction deletion with balance impact preview.
Handles single, bulk, and import-revert deletion flows.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func, and_
from typing import List, Optional, Dict, Any
from uuid import UUID
from pydantic import BaseModel
from decimal import Decimal
import logging

from app.database import get_db
from app.models import Transaction, Account, AccountBalance, CsvImport
from app.db_helpers import get_user_id

logger = logging.getLogger(__name__)

router = APIRouter()


class DeletePreviewRequest(BaseModel):
    transaction_ids: Optional[List[str]] = None
    import_id: Optional[str] = None


class DeletePreviewAccountImpact(BaseModel):
    account_id: str
    account_name: str
    currency: str
    current_balance: Optional[float] = None
    balance_change: float
    projected_balance: Optional[float] = None
    has_anchored_balances: bool = False
    anchored_balance_count: int = 0


class DeletePreviewResponse(BaseModel):
    transaction_count: int
    total_amount: float
    affected_accounts: List[DeletePreviewAccountImpact]
    has_modified_transactions: bool = False
    modified_transaction_count: int = 0
    category_impacts: List[Dict[str, Any]] = []


class DeleteTransactionsRequest(BaseModel):
    transaction_ids: List[str]
    confirmation: str


class ImportRevertRequest(BaseModel):
    import_id: str
    confirmation: str


@router.post("/delete-preview", response_model=DeletePreviewResponse)
def get_delete_preview(
    request: DeletePreviewRequest,
    user_id: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """Preview the impact of deleting transactions before confirmation."""
    user_id = get_user_id(user_id)

    if not request.transaction_ids and not request.import_id:
        raise HTTPException(status_code=400, detail="Provide transaction_ids or import_id")

    if request.import_id:
        import_uuid = UUID(request.import_id)
        transactions = (
            db.query(Transaction)
            .filter(
                Transaction.import_id == import_uuid,
                Transaction.user_id == user_id,
            )
            .all()
        )
    else:
        txn_uuids = [UUID(tid) for tid in request.transaction_ids]
        transactions = (
            db.query(Transaction)
            .filter(
                Transaction.id.in_(txn_uuids),
                Transaction.user_id == user_id,
            )
            .all()
        )

    if not transactions:
        raise HTTPException(status_code=404, detail="No matching transactions found")

    total_amount = float(sum(t.amount for t in transactions))

    account_impacts: Dict[str, DeletePreviewAccountImpact] = {}
    for txn in transactions:
        aid = str(txn.account_id)
        if aid not in account_impacts:
            account = (
                db.query(Account)
                .filter(Account.id == txn.account_id)
                .first()
            )
            current_bal = float(account.functional_balance) if account and account.functional_balance else None
            account_impacts[aid] = DeletePreviewAccountImpact(
                account_id=aid,
                account_name=account.name if account else "Unknown",
                currency=account.currency or "EUR" if account else "EUR",
                current_balance=current_bal,
                balance_change=0.0,
                projected_balance=current_bal,
                has_anchored_balances=False,
                anchored_balance_count=0,
            )
        account_impacts[aid].balance_change -= float(txn.amount)

    for aid, impact in account_impacts.items():
        if impact.current_balance is not None:
            impact.projected_balance = impact.current_balance + impact.balance_change

        anchored_count = (
            db.query(func.count(AccountBalance.id))
            .filter(
                AccountBalance.account_id == UUID(aid),
                AccountBalance.is_anchored == True,
            )
            .scalar()
            or 0
        )
        if anchored_count > 0:
            impact.has_anchored_balances = True
            impact.anchored_balance_count = anchored_count

    modified_count = sum(
        1
        for t in transactions
        if t.category_id is not None
        and t.category_system_id is not None
        and t.category_id != t.category_system_id
    )

    category_impacts: List[Dict[str, Any]] = []
    cat_sums: Dict[Optional[str], Dict[str, Any]] = {}
    for txn in transactions:
        cid = str(txn.category_id) if txn.category_id else str(txn.category_system_id) if txn.category_system_id else None
        if cid not in cat_sums:
            cat_sums[cid] = {"category_id": cid, "amount": 0.0, "count": 0}
        cat_sums[cid]["amount"] += float(txn.amount)
        cat_sums[cid]["count"] += 1
    category_impacts = list(cat_sums.values())

    return DeletePreviewResponse(
        transaction_count=len(transactions),
        total_amount=total_amount,
        affected_accounts=list(account_impacts.values()),
        has_modified_transactions=modified_count > 0,
        modified_transaction_count=modified_count,
        category_impacts=category_impacts,
    )


@router.post("/delete")
def delete_transactions_bulk(
    request: DeleteTransactionsRequest,
    user_id: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """Delete transactions atomically and trigger async balance recalculation."""
    user_id = get_user_id(user_id)

    if request.confirmation.strip().lower() != "delete transactions":
        raise HTTPException(status_code=400, detail="Invalid confirmation text")

    if not request.transaction_ids:
        raise HTTPException(status_code=400, detail="No transaction IDs provided")

    txn_uuids = [UUID(tid) for tid in request.transaction_ids]

    transactions = (
        db.query(Transaction)
        .filter(
            Transaction.id.in_(txn_uuids),
            Transaction.user_id == user_id,
        )
        .all()
    )

    if not transactions:
        raise HTTPException(status_code=404, detail="No matching transactions found")

    affected_account_ids = list(set(str(t.account_id) for t in transactions))
    deleted_count = len(transactions)

    for txn in transactions:
        db.delete(txn)

    db.commit()

    try:
        from tasks.balance_recalc_tasks import recalculate_balances_after_deletion
        recalculate_balances_after_deletion.delay(user_id, affected_account_ids)
    except Exception as e:
        logger.warning(f"Failed to enqueue balance recalculation task: {e}")

    return {
        "success": True,
        "deleted_count": deleted_count,
        "affected_account_ids": affected_account_ids,
        "balance_recalculation": "pending",
    }


@router.post("/revert-import")
def revert_import(
    request: ImportRevertRequest,
    user_id: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """Revert an entire CSV import, deleting all associated transactions atomically."""
    user_id = get_user_id(user_id)

    if request.confirmation.strip().lower() != "delete transactions":
        raise HTTPException(status_code=400, detail="Invalid confirmation text")

    import_uuid = UUID(request.import_id)
    csv_import = (
        db.query(CsvImport)
        .filter(CsvImport.id == import_uuid, CsvImport.user_id == user_id)
        .first()
    )
    if not csv_import:
        raise HTTPException(status_code=404, detail="Import not found")

    transactions = (
        db.query(Transaction)
        .filter(
            Transaction.import_id == import_uuid,
            Transaction.user_id == user_id,
        )
        .all()
    )

    affected_account_ids = list(set(str(t.account_id) for t in transactions))
    deleted_count = len(transactions)

    for txn in transactions:
        db.delete(txn)

    csv_import.status = "reverted"
    db.commit()

    if affected_account_ids:
        try:
            from tasks.balance_recalc_tasks import recalculate_balances_after_deletion
            recalculate_balances_after_deletion.delay(user_id, affected_account_ids)
        except Exception as e:
            logger.warning(f"Failed to enqueue balance recalculation task: {e}")

    return {
        "success": True,
        "deleted_count": deleted_count,
        "import_id": str(csv_import.id),
        "affected_account_ids": affected_account_ids,
        "balance_recalculation": "pending" if affected_account_ids else "not_needed",
    }
