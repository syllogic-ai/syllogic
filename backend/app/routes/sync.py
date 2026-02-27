"""
Sync routes for bank integrations.
"""
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.orm import Session
from typing import Optional
from datetime import datetime
from pydantic import BaseModel

from app.database import get_db
from app.models import Account
from app.db_helpers import get_user_id
from app.integrations.revolut_csv import RevolutCSVAdapter
from app.services.sync_service import SyncService
from app.security.data_encryption import decrypt_with_fallback
import os

router = APIRouter()


class SyncResponse(BaseModel):
    accounts_synced: int
    transactions_created: int
    transactions_updated: int
    subscriptions_detected: int = 0
    suggestions_count: int = 0
    message: str


@router.post("/revolut/csv", response_model=SyncResponse)
async def sync_revolut_csv(
    file: UploadFile = File(...),
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    user_id: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """
    Import Revolut transactions from CSV file.
    
    Upload a CSV file exported from Revolut app or web interface.
    The file will be parsed and transactions will be imported into the database.
    """
    user_id = get_user_id(user_id)
    if not file.filename.endswith('.csv'):
        raise HTTPException(status_code=400, detail="File must be a CSV file")
    
    # Read CSV content
    content = await file.read()
    csv_content = content.decode('utf-8')
    
    # Create adapter
    adapter = RevolutCSVAdapter(csv_content)
    
    # Create sync service
    sync_service = SyncService(db, user_id=user_id)
    
    # Perform sync
    try:
        # First, let's test parsing to see if we get any transactions
        test_transactions = adapter.fetch_transactions('default')
        print(f"DEBUG: Parsed {len(test_transactions)} transactions from CSV")
        if len(test_transactions) > 0:
            print(f"DEBUG: First transaction: {test_transactions[0]}")
        
        result = sync_service.sync_all(
            adapter,
            provider='revolut',
            start_date=start_date,
            end_date=end_date,
        )

        subscriptions_detected = result.get('subscriptions_detected', 0)
        message = (
            f"Successfully synced {result['accounts_synced']} account(s). "
            f"Created {result['transactions_created']} new transactions, "
            f"updated {result['transactions_updated']} existing transactions."
        )
        if subscriptions_detected > 0:
            message += f" Detected {subscriptions_detected} active monthly subscription(s)."

        return SyncResponse(
            accounts_synced=result['accounts_synced'],
            transactions_created=result['transactions_created'],
            transactions_updated=result['transactions_updated'],
            subscriptions_detected=subscriptions_detected,
            suggestions_count=0,
            message=message,
        )
    except Exception as e:
        import traceback
        error_detail = f"Error syncing transactions: {str(e)}\n{traceback.format_exc()}"
        print(f"ERROR: {error_detail}")
        raise HTTPException(
            status_code=500,
            detail=f"Error syncing transactions: {str(e)}"
        )


@router.post("/plaid/sync", response_model=SyncResponse)
def sync_plaid(
    access_token: str,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    user_id: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """
    Sync transactions from Plaid.
    
    Requires:
    - PLAID_CLIENT_ID environment variable
    - PLAID_SECRET environment variable
    - access_token: Plaid access token (obtained via Plaid Link OAuth flow)
    """
    user_id = get_user_id(user_id)
    try:
        from app.integrations.plaid_adapter import PlaidAdapter
        
        client_id = os.getenv("PLAID_CLIENT_ID")
        secret = os.getenv("PLAID_SECRET")
        environment = os.getenv("PLAID_ENVIRONMENT", "sandbox")
        
        if not client_id or not secret:
            raise HTTPException(
                status_code=500,
                detail="Plaid credentials not configured. Set PLAID_CLIENT_ID and PLAID_SECRET environment variables."
            )
        
        # Create adapter
        adapter = PlaidAdapter(
            access_token=access_token,
            client_id=client_id,
            secret=secret,
            environment=environment
        )
        
        # Create sync service
        sync_service = SyncService(db, user_id=user_id)
        
        # Perform sync
        result = sync_service.sync_all(
            adapter,
            provider='plaid',
            start_date=start_date,
            end_date=end_date,
        )

        subscriptions_detected = result.get('subscriptions_detected', 0)
        message = (
            f"Successfully synced {result['accounts_synced']} account(s). "
            f"Created {result['transactions_created']} new transactions, "
            f"updated {result['transactions_updated']} existing transactions."
        )
        if subscriptions_detected > 0:
            message += f" Detected {subscriptions_detected} active monthly subscription(s)."

        return SyncResponse(
            accounts_synced=result['accounts_synced'],
            transactions_created=result['transactions_created'],
            transactions_updated=result['transactions_updated'],
            subscriptions_detected=subscriptions_detected,
            suggestions_count=0,
            message=message,
        )
    except ImportError:
        raise HTTPException(
            status_code=500,
            detail="Plaid library not installed. Run: pip install plaid-python"
        )
    except Exception as e:
        import traceback
        error_detail = f"Error syncing Plaid transactions: {str(e)}\n{traceback.format_exc()}"
        print(f"ERROR: {error_detail}")
        raise HTTPException(
            status_code=500,
            detail=f"Error syncing transactions: {str(e)}"
        )


@router.get("/accounts/{account_id}")
def get_sync_status(
    account_id: str,
    user_id: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """Get sync status for an account."""
    user_id = get_user_id(user_id)
    account = db.query(Account).filter(
        Account.id == account_id,
        Account.user_id == user_id
    ).first()
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")
    
    from app.models import Transaction
    transaction_count = db.query(Transaction).filter(
        Transaction.user_id == user_id,
        Transaction.account_id == account.id
    ).count()
    
    return {
        "account_id": str(account.id),
        "name": account.name,
        "provider": account.provider,
        "external_id": decrypt_with_fallback(account.external_id_ciphertext, account.external_id),
        "last_synced": account.updated_at.isoformat() if account.updated_at else None,
        "transaction_count": transaction_count,
    }
