"""
API routes for Enable Banking integration.

Handles ASPSP listing, auth initiation, session exchange, sync triggers,
connection status, and disconnection.
"""

import os
import logging
from typing import Optional
from datetime import datetime, timedelta

import redis
import json
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.database import get_db
from app.db_helpers import get_user_id
from app.models import BankConnection, Account
from app.integrations.enable_banking_auth import EnableBankingClient
from app.integrations.enable_banking_adapter import EnableBankingAdapter
from app.services.sync_service import SyncService
from app.security.data_encryption import encrypt_value, blind_index

logger = logging.getLogger(__name__)

router = APIRouter()

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
ASPSP_CACHE_TTL = 86400  # 24 hours


# --- Request/Response models ---

class AuthRequest(BaseModel):
    aspsp_name: str
    aspsp_country: str

class AuthResponse(BaseModel):
    url: str

class SessionRequest(BaseModel):
    code: str

class SessionResponse(BaseModel):
    connection_id: str
    accounts_count: int

class ConnectionStatusResponse(BaseModel):
    id: str
    aspsp_name: str
    aspsp_country: str
    status: str
    last_synced_at: Optional[str] = None
    consent_expires_at: Optional[str] = None
    last_sync_error: Optional[str] = None
    accounts_count: int

class SyncTriggerResponse(BaseModel):
    message: str
    task_id: Optional[str] = None


# --- Helper ---

def _get_eb_client() -> EnableBankingClient:
    return EnableBankingClient()

def _get_redis() -> redis.Redis:
    return redis.from_url(REDIS_URL, decode_responses=True)


# --- Routes ---

@router.get("/aspsps")
def list_aspsps(country: Optional[str] = None):
    """
    List available banks (ASPSPs), optionally filtered by country.
    Results are cached in Redis for 24 hours.
    """
    cache_key = f"eb:aspsps:{country or 'all'}"

    try:
        r = _get_redis()
        cached = r.get(cache_key)
        if cached:
            return json.loads(cached)
    except Exception:
        logger.warning("Redis unavailable for ASPSP cache, fetching from API")

    client = _get_eb_client()
    params = {}
    if country:
        params["country"] = country.upper()

    try:
        resp = client.get("/aspsps", params=params)
        data = resp.json()
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Enable Banking API error: {str(e)}")

    # Cache the response
    try:
        r = _get_redis()
        r.setex(cache_key, ASPSP_CACHE_TTL, json.dumps(data))
    except Exception:
        logger.warning("Failed to cache ASPSP list in Redis")

    return data


@router.post("/auth", response_model=AuthResponse)
def initiate_auth(
    body: AuthRequest,
    user_id: str = Depends(get_user_id),
    db: Session = Depends(get_db),
):
    """Generate bank authorization URL for PSU redirect."""
    client = _get_eb_client()

    auth_payload = {
        "access": {
            "valid_until": (datetime.utcnow() + timedelta(days=90)).strftime("%Y-%m-%dT%H:%M:%S.000Z"),
        },
        "aspsp": {
            "name": body.aspsp_name,
            "country": body.aspsp_country.upper(),
        },
        "state": user_id,  # Pass user_id as state for callback validation
        "redirect_url": client.redirect_uri,
        "psu_type": "personal",
    }

    try:
        resp = client.post("/auth", json_data=auth_payload)
        data = resp.json()
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Failed to initiate auth: {str(e)}")

    return AuthResponse(url=data["url"])


@router.post("/session", response_model=SessionResponse)
def create_session(
    body: SessionRequest,
    user_id: str = Depends(get_user_id),
    db: Session = Depends(get_db),
):
    """
    Exchange authorization code for an Enable Banking session.
    Creates a bank_connections row and upserts accounts.
    """
    client = _get_eb_client()

    # Exchange code for session
    try:
        resp = client.post("/sessions", json_data={"code": body.code})
        session_data = resp.json()
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Session exchange failed: {str(e)}")

    session_id = session_data.get("session_id")
    if not session_id:
        raise HTTPException(status_code=502, detail="No session_id in response")

    aspsp_info = session_data.get("aspsp", {})
    aspsp_name = aspsp_info.get("name", "Unknown Bank")
    aspsp_country = aspsp_info.get("country", "XX")

    # Calculate consent expiry (EB returns valid_until or we default to 90 days)
    consent_valid_until = session_data.get("access", {}).get("valid_until")
    consent_expires_at = None
    if consent_valid_until:
        try:
            consent_expires_at = datetime.fromisoformat(consent_valid_until.replace("Z", "+00:00"))
        except (ValueError, TypeError):
            consent_expires_at = datetime.utcnow() + timedelta(days=90)
    else:
        consent_expires_at = datetime.utcnow() + timedelta(days=90)

    # Create bank_connections row
    connection = BankConnection(
        user_id=user_id,
        provider="enable_banking",
        session_id=session_id,
        aspsp_name=aspsp_name,
        aspsp_country=aspsp_country,
        consent_expires_at=consent_expires_at,
        status="active",
        raw_session_data=session_data,
    )
    db.add(connection)
    db.flush()  # Get the ID

    # Upsert accounts from session response
    accounts_data = session_data.get("accounts", [])
    for acc_data in accounts_data:
        account_uid = acc_data["uid"]

        # Check for existing account by external_id
        existing = db.query(Account).filter(
            Account.user_id == user_id,
            Account.provider == "enable_banking",
            Account.external_id == account_uid,
        ).first()

        if existing:
            existing.bank_connection_id = connection.id
            existing.name = acc_data.get("account_name") or acc_data.get("iban") or existing.name
            existing.is_active = True
        else:
            new_account = Account(
                user_id=user_id,
                name=acc_data.get("account_name") or acc_data.get("iban") or "Unknown Account",
                account_type=_map_account_type(acc_data.get("cash_account_type")),
                institution=aspsp_name,
                currency=acc_data.get("currency", "EUR"),
                provider="enable_banking",
                external_id=account_uid,
                bank_connection_id=connection.id,
            )
            encrypted = encrypt_value(account_uid)
            hashed = blind_index(account_uid)
            new_account.external_id_hash = hashed
            if encrypted:
                new_account.external_id_ciphertext = encrypted
            db.add(new_account)

    db.commit()
    db.refresh(connection)

    # Dispatch initial sync task
    try:
        from tasks.enable_banking_tasks import sync_bank_connection
        sync_bank_connection.delay(str(connection.id))
    except Exception:
        logger.warning("Failed to dispatch initial sync task", exc_info=True)

    return SessionResponse(
        connection_id=str(connection.id),
        accounts_count=len(accounts_data),
    )


@router.post("/sync/{connection_id}", response_model=SyncTriggerResponse)
def trigger_sync(
    connection_id: str,
    user_id: str = Depends(get_user_id),
    db: Session = Depends(get_db),
):
    """Trigger on-demand sync for a bank connection."""
    connection = db.query(BankConnection).filter(
        BankConnection.id == connection_id,
        BankConnection.user_id == user_id,
    ).first()
    if not connection:
        raise HTTPException(status_code=404, detail="Connection not found")

    if connection.status not in ("active",):
        raise HTTPException(
            status_code=400,
            detail=f"Cannot sync connection with status '{connection.status}'. Reconnect the bank first.",
        )

    try:
        from tasks.enable_banking_tasks import sync_bank_connection
        task = sync_bank_connection.delay(str(connection.id))
        return SyncTriggerResponse(message="Sync started", task_id=task.id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to start sync: {str(e)}")


@router.get("/status/{connection_id}", response_model=ConnectionStatusResponse)
def connection_status(
    connection_id: str,
    user_id: str = Depends(get_user_id),
    db: Session = Depends(get_db),
):
    """Get connection status, last sync time, consent expiry."""
    connection = db.query(BankConnection).filter(
        BankConnection.id == connection_id,
        BankConnection.user_id == user_id,
    ).first()
    if not connection:
        raise HTTPException(status_code=404, detail="Connection not found")

    accounts_count = db.query(Account).filter(
        Account.bank_connection_id == connection.id,
    ).count()

    return ConnectionStatusResponse(
        id=str(connection.id),
        aspsp_name=connection.aspsp_name,
        aspsp_country=connection.aspsp_country,
        status=connection.status,
        last_synced_at=connection.last_synced_at.isoformat() if connection.last_synced_at else None,
        consent_expires_at=connection.consent_expires_at.isoformat() if connection.consent_expires_at else None,
        last_sync_error=connection.last_sync_error,
        accounts_count=accounts_count,
    )


@router.get("/connections")
def list_connections(
    user_id: str = Depends(get_user_id),
    db: Session = Depends(get_db),
):
    """List all bank connections for the current user."""
    connections = db.query(BankConnection).filter(
        BankConnection.user_id == user_id,
    ).order_by(BankConnection.created_at.desc()).all()

    results = []
    for conn in connections:
        accounts_count = db.query(Account).filter(
            Account.bank_connection_id == conn.id,
        ).count()
        results.append({
            "id": str(conn.id),
            "aspsp_name": conn.aspsp_name,
            "aspsp_country": conn.aspsp_country,
            "status": conn.status,
            "last_synced_at": conn.last_synced_at.isoformat() if conn.last_synced_at else None,
            "consent_expires_at": conn.consent_expires_at.isoformat() if conn.consent_expires_at else None,
            "last_sync_error": conn.last_sync_error,
            "accounts_count": accounts_count,
            "created_at": conn.created_at.isoformat() if conn.created_at else None,
        })

    return results


@router.delete("/{connection_id}")
def disconnect(
    connection_id: str,
    user_id: str = Depends(get_user_id),
    db: Session = Depends(get_db),
):
    """Disconnect bank: revoke EB session, mark connection as disconnected."""
    connection = db.query(BankConnection).filter(
        BankConnection.id == connection_id,
        BankConnection.user_id == user_id,
    ).first()
    if not connection:
        raise HTTPException(status_code=404, detail="Connection not found")

    # Revoke session at Enable Banking (best-effort)
    try:
        client = _get_eb_client()
        client.delete(f"/sessions/{connection.session_id}")
    except Exception:
        logger.warning(f"Failed to revoke EB session {connection.session_id}", exc_info=True)

    connection.status = "disconnected"
    db.commit()

    return {"message": "Bank connection disconnected"}


# --- Helpers ---

def _map_account_type(cash_account_type: Optional[str]) -> str:
    """Map EB cash account type to our canonical type."""
    if not cash_account_type:
        return "checking"
    mapping = {
        "CACC": "checking",
        "SVGS": "savings",
        "TRAN": "checking",
        "CASH": "checking",
        "CARD": "credit",
        "LOAN": "credit",
        "MGLD": "savings",
        "MOMA": "savings",
    }
    return mapping.get(cash_account_type.upper(), "checking")
