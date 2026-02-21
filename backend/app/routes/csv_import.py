"""
API endpoints for background CSV import processing.
Handles enqueueing imports and checking status.
"""
import logging
from typing import List, Optional, Dict, Any
from uuid import UUID
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from celery.result import AsyncResult

from app.database import get_db
from app.db_helpers import get_user_id
from app.models import CsvImport, Account
from celery_app import celery_app

logger = logging.getLogger(__name__)

router = APIRouter()


class TransactionForImport(BaseModel):
    """Transaction data to be imported."""
    account_id: str
    amount: float
    description: Optional[str] = None
    merchant: Optional[str] = None
    booked_at: str  # ISO datetime string
    transaction_type: str  # "credit" or "debit"
    currency: str = "EUR"
    external_id: Optional[str] = None
    category_id: Optional[str] = None


class DailyBalanceForImport(BaseModel):
    """Daily balance data for import."""
    date: str  # YYYY-MM-DD
    balance: float


class EnqueueImportRequest(BaseModel):
    """Request to enqueue a CSV import for background processing."""
    csv_import_id: str
    user_id: Optional[str] = None
    transactions: List[TransactionForImport]
    daily_balances: Optional[List[DailyBalanceForImport]] = None
    starting_balance: Optional[float] = None


class EnqueueImportResponse(BaseModel):
    """Response from enqueueing an import."""
    success: bool
    import_id: str
    task_id: Optional[str] = None
    message: str


class ImportStatusResponse(BaseModel):
    """Response for import status check."""
    import_id: str
    status: str  # pending, mapping, previewing, importing, completed, failed
    total_rows: Optional[int] = None
    imported_rows: Optional[int] = None
    progress_count: Optional[int] = None
    error_message: Optional[str] = None
    celery_task_id: Optional[str] = None


def _reconcile_import_status(db: Session, csv_import: CsvImport) -> None:
    """
    Reconcile imports stuck in "importing" with the actual Celery task state.
    """
    if csv_import.status != "importing" or not csv_import.celery_task_id:
        return

    try:
        task_result = AsyncResult(csv_import.celery_task_id, app=celery_app)
        task_state = task_result.state

        if task_state == "SUCCESS":
            result_payload = task_result.result if isinstance(task_result.result, dict) else {}
            imported_count = result_payload.get("imported_count")

            csv_import.status = "completed"
            if isinstance(imported_count, int) and csv_import.imported_rows is None:
                csv_import.imported_rows = imported_count
            if csv_import.completed_at is None:
                csv_import.completed_at = datetime.utcnow()
            db.commit()
            return

        if task_state in {"FAILURE", "REVOKED"}:
            csv_import.status = "failed"
            error_message = task_result.result
            csv_import.error_message = str(error_message)[:2000] if error_message else f"Background task {task_state.lower()}"
            if csv_import.completed_at is None:
                csv_import.completed_at = datetime.utcnow()
            db.commit()
    except Exception as e:
        logger.warning("Failed to reconcile import %s from Celery task state: %s", csv_import.id, e)


@router.post("/enqueue", response_model=EnqueueImportResponse)
def enqueue_csv_import(
    request: EnqueueImportRequest,
    db: Session = Depends(get_db)
):
    """
    Enqueue a CSV import for background processing.

    This endpoint:
    1. Validates the CSV import record exists
    2. Stores selected indices and transactions
    3. Starts a Celery task for background processing
    4. Returns immediately so the frontend can redirect

    The frontend should then connect to the SSE endpoint to receive
    real-time progress updates.
    """
    from tasks.csv_import_tasks import process_csv_import

    try:
        user_id = get_user_id(request.user_id)

        # Validate CSV import exists and belongs to user
        csv_import = db.query(CsvImport).filter(
            CsvImport.id == request.csv_import_id,
            CsvImport.user_id == user_id
        ).first()

        if not csv_import:
            raise HTTPException(status_code=404, detail="CSV import not found")

        # Validate account exists
        # Get account_id from first transaction
        if request.transactions:
            account_id = request.transactions[0].account_id
            account = db.query(Account).filter(
                Account.id == account_id,
                Account.user_id == user_id
            ).first()

            if not account:
                raise HTTPException(status_code=404, detail="Account not found")

        # Update CSV import status
        csv_import.status = "importing"
        csv_import.total_rows = len(request.transactions)
        csv_import.progress_count = 0
        db.commit()

        # Convert transactions to dict format for Celery task
        transactions_data = [
            {
                "account_id": txn.account_id,
                "amount": txn.amount,
                "description": txn.description,
                "merchant": txn.merchant,
                "booked_at": txn.booked_at,
                "transaction_type": txn.transaction_type,
                "currency": txn.currency,
                "external_id": txn.external_id,
                "category_id": txn.category_id,
            }
            for txn in request.transactions
        ]

        # Convert daily balances if provided
        daily_balances_data = None
        if request.daily_balances:
            daily_balances_data = [
                {"date": bal.date, "balance": bal.balance}
                for bal in request.daily_balances
            ]

        # Start Celery task
        task = process_csv_import.delay(
            csv_import_id=str(request.csv_import_id),
            user_id=user_id,
            transactions_data=transactions_data,
            daily_balances=daily_balances_data,
            starting_balance=request.starting_balance,
        )

        # Store task ID
        csv_import.celery_task_id = task.id
        db.commit()

        logger.info(
            f"Enqueued CSV import {request.csv_import_id} as Celery task {task.id}"
        )

        return EnqueueImportResponse(
            success=True,
            import_id=str(csv_import.id),
            task_id=task.id,
            message=f"Import enqueued successfully. Processing {len(request.transactions)} transactions."
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error enqueueing CSV import: {e}")
        import traceback
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Failed to enqueue import: {str(e)}")


@router.get("/status/{import_id}", response_model=ImportStatusResponse)
def get_import_status(
    import_id: str,
    user_id: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """
    Get the current status of a CSV import.

    This is useful for checking status without maintaining an SSE connection.
    """
    try:
        resolved_user_id = get_user_id(user_id)

        csv_import = db.query(CsvImport).filter(
            CsvImport.id == import_id,
            CsvImport.user_id == resolved_user_id
        ).first()

        if not csv_import:
            raise HTTPException(status_code=404, detail="CSV import not found")

        _reconcile_import_status(db, csv_import)
        db.refresh(csv_import)

        return ImportStatusResponse(
            import_id=str(csv_import.id),
            status=csv_import.status or "pending",
            total_rows=csv_import.total_rows,
            imported_rows=csv_import.imported_rows,
            progress_count=csv_import.progress_count,
            error_message=csv_import.error_message,
            celery_task_id=csv_import.celery_task_id,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting import status: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get status: {str(e)}")
