"""
Ponto Connect OAuth and sync routes.
"""
import os
import logging
from typing import Optional
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session
from pydantic import BaseModel
import redis

from app.database import get_db
from app.db_helpers import get_user_id
from app.models import BankConnection, Account
from app.integrations.ponto.client import PontoClient
from app.integrations.ponto.adapter import PontoAdapter
from app.services.token_service import TokenService
from app.services.sync_service import SyncService
from app.services.subscription_detector import SubscriptionDetector

logger = logging.getLogger(__name__)
router = APIRouter()


# Response models
class AuthorizeResponse(BaseModel):
    authorization_url: str
    state: str


class CallbackResponse(BaseModel):
    success: bool
    connection_id: str
    account_count: int
    message: str


class SyncResponse(BaseModel):
    success: bool
    transactions_created: int
    transactions_updated: int
    suggestions_count: int = 0
    message: str


class ConnectionResponse(BaseModel):
    id: str
    institution_name: Optional[str]
    status: Optional[str]
    provider: Optional[str]
    last_synced_at: Optional[str]
    sync_status: Optional[str]
    error_message: Optional[str]
    account_count: int
    created_at: Optional[str]


class DisconnectResponse(BaseModel):
    success: bool
    message: str


# Helper functions
def get_ponto_client() -> PontoClient:
    """Get configured Ponto client."""
    client_id = os.getenv("PONTO_CLIENT_ID")
    client_secret = os.getenv("PONTO_CLIENT_SECRET")
    sandbox = os.getenv("PONTO_SANDBOX", "true").lower() == "true"

    if not client_id or not client_secret:
        raise HTTPException(
            status_code=500,
            detail="Ponto credentials not configured. Set PONTO_CLIENT_ID and PONTO_CLIENT_SECRET."
        )

    return PontoClient(client_id, client_secret, sandbox=sandbox)


def get_redis_client() -> redis.Redis:
    """Get Redis client for storing OAuth state."""
    redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    return redis.from_url(redis_url, decode_responses=True)


def get_redirect_uri() -> str:
    """Get the OAuth redirect URI."""
    return os.getenv("PONTO_REDIRECT_URI", "http://localhost:3000/bank/callback")


def get_client_ip(request: Request) -> str:
    """
    Extract client IP address from request.
    Handles X-Forwarded-For header for proxied requests.
    """
    # Check for forwarded header (when behind proxy/load balancer)
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        # Take the first IP in the chain (original client)
        return forwarded_for.split(",")[0].strip()

    # Check for real IP header (nginx)
    real_ip = request.headers.get("X-Real-IP")
    if real_ip:
        return real_ip

    # Fall back to direct connection IP
    if request.client:
        return request.client.host

    # Default fallback
    return "127.0.0.1"


# Routes
@router.post("/authorize", response_model=AuthorizeResponse)
async def authorize(
    user_id: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """
    Generate Ponto authorization URL with PKCE.

    Returns the authorization URL to redirect the user to.
    Stores PKCE code verifier in Redis for later use.
    """
    user_id = get_user_id(user_id)
    client = get_ponto_client()
    redis_client = get_redis_client()

    # Generate PKCE codes
    code_verifier = PontoClient.generate_code_verifier()
    code_challenge = PontoClient.generate_code_challenge(code_verifier)
    state = PontoClient.generate_state()

    # Store PKCE data in Redis (expires in 10 minutes)
    redis_key = f"ponto_oauth:{state}"
    redis_client.hset(redis_key, mapping={
        "code_verifier": code_verifier,
        "user_id": user_id,
    })
    redis_client.expire(redis_key, 600)  # 10 minutes

    # Generate authorization URL
    authorization_url = client.get_authorization_url(
        redirect_uri=get_redirect_uri(),
        state=state,
        code_challenge=code_challenge,
    )

    logger.info(f"Generated Ponto authorization URL for user {user_id} (sandbox={client.sandbox})")
    logger.debug(f"Authorization URL: {authorization_url}")

    return AuthorizeResponse(
        authorization_url=authorization_url,
        state=state,
    )


@router.get("/callback", response_model=CallbackResponse)
async def callback(
    code: str = Query(...),
    state: str = Query(...),
    db: Session = Depends(get_db),
):
    """
    Handle OAuth callback from Ponto.

    Exchanges authorization code for tokens and fetches accounts.
    """
    redis_client = get_redis_client()

    # Retrieve PKCE data from Redis
    redis_key = f"ponto_oauth:{state}"
    oauth_data = redis_client.hgetall(redis_key)

    if not oauth_data:
        raise HTTPException(
            status_code=400,
            detail="Invalid or expired state parameter"
        )

    code_verifier = oauth_data.get("code_verifier")
    user_id = oauth_data.get("user_id")

    if not code_verifier or not user_id:
        raise HTTPException(
            status_code=400,
            detail="Missing OAuth data"
        )

    # Delete the Redis key (one-time use)
    redis_client.delete(redis_key)

    client = get_ponto_client()
    token_service = TokenService()

    async with client:
        try:
            # Exchange code for tokens
            token_response = await client.exchange_code_for_tokens(
                code=code,
                code_verifier=code_verifier,
                redirect_uri=get_redirect_uri(),
            )

            # Get user info to get organization ID
            user_info = await client.get_user_info(token_response.access_token)
            organization_id = user_info.get("sub")

            # Create bank connection record
            connection = BankConnection(
                user_id=user_id,
                institution_id="ponto",
                institution_name="Ponto Connect",
                provider="ponto",
                status="linked",
                organization_id=organization_id,
                access_token=token_service.encrypt_token(token_response.access_token),
                refresh_token=token_service.encrypt_token(token_response.refresh_token),
                access_token_expires_at=datetime.now(timezone.utc) +
                    __import__('datetime').timedelta(seconds=token_response.expires_in),
                sync_status="idle",
            )
            db.add(connection)
            db.commit()
            db.refresh(connection)

            # Fetch accounts
            adapter = PontoAdapter(
                access_token=token_response.access_token,
                refresh_token=token_response.refresh_token,
                client=client,
            )
            accounts_data = await adapter.fetch_accounts()

            # Create account records
            account_count = 0
            for account_data in accounts_data:
                account = Account(
                    user_id=user_id,
                    bank_connection_id=connection.id,
                    name=account_data.name,
                    account_type=account_data.account_type,
                    institution=account_data.institution,
                    currency=account_data.currency,
                    provider="ponto",
                    external_id=account_data.external_id,
                    balance_available=account_data.balance_available,
                    is_active=True,
                )
                db.add(account)
                account_count += 1

            db.commit()

            logger.info(
                f"Created connection {connection.id} with {account_count} accounts for user {user_id}"
            )

            return CallbackResponse(
                success=True,
                connection_id=str(connection.id),
                account_count=account_count,
                message=f"Successfully connected {account_count} account(s)",
            )

        except Exception as e:
            logger.error(f"Failed to complete Ponto OAuth: {e}")
            raise HTTPException(
                status_code=500,
                detail=f"Failed to connect bank: {str(e)}"
            )


@router.get("/connections", response_model=list[ConnectionResponse])
def get_connections(
    user_id: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """
    Get all Ponto bank connections for the user.
    """
    user_id = get_user_id(user_id)

    connections = db.query(BankConnection).filter(
        BankConnection.user_id == user_id,
        BankConnection.provider == "ponto",
    ).all()

    result = []
    for conn in connections:
        account_count = db.query(Account).filter(
            Account.bank_connection_id == conn.id
        ).count()

        result.append(ConnectionResponse(
            id=str(conn.id),
            institution_name=conn.institution_name,
            status=conn.status,
            provider=conn.provider,
            last_synced_at=conn.last_synced_at.isoformat() if conn.last_synced_at else None,
            sync_status=conn.sync_status,
            error_message=conn.error_message,
            account_count=account_count,
            created_at=conn.created_at.isoformat() if conn.created_at else None,
        ))

    return result


@router.post("/sync/{connection_id}", response_model=SyncResponse)
async def sync_connection(
    connection_id: str,
    request: Request,
    user_id: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """
    Trigger manual sync for a Ponto connection (API v2).

    Note: Ponto rate-limits manual syncs to 5 minutes between syncs.
    Maximum 50 synchronizations per day per account.
    """
    user_id = get_user_id(user_id)
    customer_ip = get_client_ip(request)

    # Get connection
    connection = db.query(BankConnection).filter(
        BankConnection.id == connection_id,
        BankConnection.user_id == user_id,
        BankConnection.provider == "ponto",
    ).first()

    if not connection:
        raise HTTPException(status_code=404, detail="Connection not found")

    if connection.status != "linked":
        raise HTTPException(
            status_code=400,
            detail=f"Connection is not active (status: {connection.status})"
        )

    # Update sync status
    connection.sync_status = "syncing"
    db.commit()

    client = get_ponto_client()
    token_service = TokenService()

    async with client:
        try:
            # Get valid access token (refresh if needed)
            access_token = await token_service.get_valid_access_token(
                db, connection, client
            )

            if not access_token:
                raise HTTPException(
                    status_code=401,
                    detail="Failed to get valid access token"
                )

            # Get accounts for this connection
            accounts = db.query(Account).filter(
                Account.bank_connection_id == connection.id
            ).all()

            adapter = PontoAdapter(
                access_token=access_token,
                refresh_token=token_service.decrypt_token(connection.refresh_token),
                client=client,
            )

            sync_service = SyncService(db, user_id=user_id)
            total_created = 0
            total_updated = 0
            all_created_ids: list[str] = []

            for account in accounts:
                if not account.external_id:
                    continue

                # Trigger Ponto sync (optional, as Ponto syncs automatically 4x daily)
                try:
                    await adapter.trigger_sync(account.external_id, customer_ip)
                except Exception as e:
                    logger.warning(f"Failed to trigger Ponto sync: {e}")

                # Fetch transactions
                start_date = account.last_synced_at
                transactions = await adapter.fetch_transactions(
                    account.external_id,
                    start_date=start_date,
                )

                # Import transactions
                for tx_data in transactions:
                    result = sync_service.upsert_transaction(
                        account_id=str(account.id),
                        transaction_data=tx_data,
                    )
                    if result.get("created"):
                        total_created += 1
                        all_created_ids.append(result.get("transaction_id"))
                    elif result.get("updated"):
                        total_updated += 1

                # Update account last synced
                account.last_synced_at = datetime.now(timezone.utc)

            # Detect subscription patterns from newly created transactions
            suggestions_count = 0
            if all_created_ids:
                detector = SubscriptionDetector(db, user_id=user_id)
                suggestions_count = detector.detect_and_save(all_created_ids)

            # Update connection
            connection.last_synced_at = datetime.now(timezone.utc)
            connection.sync_status = "idle"
            connection.error_message = None
            db.commit()

            logger.info(
                f"Synced connection {connection_id}: {total_created} created, {total_updated} updated, "
                f"{suggestions_count} suggestions"
            )

            return SyncResponse(
                success=True,
                transactions_created=total_created,
                transactions_updated=total_updated,
                suggestions_count=suggestions_count,
                message=f"Synced {total_created + total_updated} transaction(s)",
            )

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Sync failed for connection {connection_id}: {e}")
            connection.sync_status = "error"
            connection.error_message = str(e)
            db.commit()
            raise HTTPException(
                status_code=500,
                detail=f"Sync failed: {str(e)}"
            )


@router.post("/refresh/{connection_id}")
async def refresh_tokens(
    connection_id: str,
    user_id: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """
    Manually refresh tokens for a Ponto connection.
    """
    user_id = get_user_id(user_id)

    connection = db.query(BankConnection).filter(
        BankConnection.id == connection_id,
        BankConnection.user_id == user_id,
        BankConnection.provider == "ponto",
    ).first()

    if not connection:
        raise HTTPException(status_code=404, detail="Connection not found")

    client = get_ponto_client()
    token_service = TokenService()

    async with client:
        try:
            access_token = await token_service.get_valid_access_token(
                db, connection, client
            )

            if not access_token:
                raise HTTPException(
                    status_code=401,
                    detail="Failed to refresh tokens"
                )

            return {"success": True, "message": "Tokens refreshed successfully"}

        except Exception as e:
            logger.error(f"Token refresh failed: {e}")
            raise HTTPException(
                status_code=500,
                detail=f"Token refresh failed: {str(e)}"
            )


@router.delete("/disconnect/{connection_id}", response_model=DisconnectResponse)
async def disconnect(
    connection_id: str,
    user_id: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """
    Disconnect a Ponto connection.

    Revokes tokens and converts accounts to manual.
    """
    user_id = get_user_id(user_id)

    connection = db.query(BankConnection).filter(
        BankConnection.id == connection_id,
        BankConnection.user_id == user_id,
        BankConnection.provider == "ponto",
    ).first()

    if not connection:
        raise HTTPException(status_code=404, detail="Connection not found")

    client = get_ponto_client()
    token_service = TokenService()

    async with client:
        # Try to revoke tokens
        try:
            _, refresh_token = token_service.get_decrypted_tokens(connection)
            if refresh_token:
                await client.revoke_token(refresh_token)
        except Exception as e:
            logger.warning(f"Failed to revoke tokens: {e}")

    # Convert accounts to manual
    accounts = db.query(Account).filter(
        Account.bank_connection_id == connection.id
    ).all()

    for account in accounts:
        account.provider = "manual"
        account.bank_connection_id = None

    # Update connection status
    connection.status = "revoked"
    connection.access_token = None
    connection.refresh_token = None
    db.commit()

    logger.info(f"Disconnected connection {connection_id}, converted {len(accounts)} accounts to manual")

    return DisconnectResponse(
        success=True,
        message=f"Disconnected bank and converted {len(accounts)} account(s) to manual",
    )
