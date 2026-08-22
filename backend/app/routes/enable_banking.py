"""
API routes for Enable Banking integration.

Handles ASPSP listing, auth initiation, session exchange, sync triggers,
connection status, and disconnection.
"""

import os
import logging
import uuid as uuid_mod
from typing import Optional, List
from datetime import datetime, timedelta, timezone

import redis
import json
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.database import get_db
from app.db_helpers import get_user_id
from app.models import BankConnection, Account
from app.integrations.enable_banking_auth import EnableBankingClient
from app.integrations.enable_banking_adapter import EnableBankingAdapter, _ACCOUNT_TYPE_MAP, _extract_iban
from app.services.sync_service import SyncService
from app.security.data_encryption import encrypt_value, blind_index, blind_index_candidates

logger = logging.getLogger(__name__)

router = APIRouter()

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
ASPSP_CACHE_TTL = 86400  # 24 hours
AUTH_STATE_TTL = 1800  # 30 min — must outlast a slow bank login, see initiate_auth


# --- Request/Response models ---

class AuthRequest(BaseModel):
    aspsp_name: str
    aspsp_country: str
    # Set to re-authorize an existing connection in place (consent renewal)
    # instead of creating a second one. See initiate_auth.
    connection_id: Optional[str] = None

class AuthResponse(BaseModel):
    url: str

class SessionRequest(BaseModel):
    code: str
    state: Optional[str] = None

class SessionResponse(BaseModel):
    connection_id: str
    accounts_count: int
    # True when an existing connection was renewed: accounts stayed mapped, so
    # the caller must skip the account-mapping wizard.
    reconnected: bool = False

class SyncProgress(BaseModel):
    stage: str  # "syncing" | "done"
    accounts_done: int
    accounts_total: int
    transactions_created: int
    transactions_updated: int
    started_at: Optional[str] = None

class ConnectionStatusResponse(BaseModel):
    id: str
    aspsp_name: str
    aspsp_country: str
    status: str
    last_synced_at: Optional[str] = None
    consent_expires_at: Optional[str] = None
    last_sync_error: Optional[str] = None
    accounts_count: int
    sync_progress: Optional[SyncProgress] = None

class SyncTriggerResponse(BaseModel):
    message: str
    task_id: Optional[str] = None

class AccountMapping(BaseModel):
    bank_uid: str
    action: str  # "create" or "link"
    name: Optional[str] = None
    existing_account_id: Optional[str] = None

class MapAccountsRequest(BaseModel):
    mappings: List[AccountMapping]
    initial_sync_days: int = 90

class MapAccountsResponse(BaseModel):
    connection_id: str
    accounts_created: int
    accounts_linked: int

class SuggestedMapping(BaseModel):
    bank_uid: str
    bank_name: str
    suggested_action: str       # "link" or "create"
    suggested_account_id: Optional[str] = None
    suggested_account_name: Optional[str] = None


# --- Helper ---

def _get_eb_client() -> EnableBankingClient:
    return EnableBankingClient()

def _get_redis() -> redis.Redis:
    return redis.from_url(REDIS_URL, decode_responses=True)


def _read_auth_state(state: Optional[str], user_id: str) -> dict:
    """Consume the OAuth state nonce and return its payload.

    Raises 403 if the nonce was issued to a different user. A missing or
    unreadable nonce yields an empty payload, which the caller treats as a
    plain first-time connect.
    """
    if not state:
        return {}

    try:
        r = _get_redis()
        raw = r.get(f"eb:state:{state}")
        r.delete(f"eb:state:{state}")  # single use, even on mismatch
    except Exception:
        logger.warning("Failed to validate OAuth state from Redis")
        return {}

    if not raw:
        return {}

    try:
        payload = json.loads(raw)
    except (TypeError, ValueError):
        payload = {"user_id": raw}  # nonce written before the payload was JSON

    if payload.get("user_id") and payload["user_id"] != user_id:
        raise HTTPException(status_code=403, detail="OAuth state mismatch")

    return payload


def _repoint_account_uids(db: Session, connection: BankConnection, raw_accounts: list) -> int:
    """Re-point the connection's accounts at the account uids of a fresh consent.

    Enable Banking mints a new account uid on every re-authorization, and the
    connection sync reads each account's stored uid directly — it cannot call
    adapter.fetch_accounts(), because EB only returns rich account objects at
    OAuth time (see the note in tasks.enable_banking_tasks). So a renewed
    consent must rewrite the uids here, while those objects are in hand, or
    every subsequent sync requests accounts that no longer exist.

    Accounts are matched on their old uid first, then on IBAN, which survives
    re-consent. A raw account matching nothing is left alone: it is new at the
    bank and was never mapped to one of the user's accounts.

    The IBAN leg needs encryption configured, since IBAN is only ever stored as
    a ciphertext + blind index. The uid leg works either way.
    """
    linked = db.query(Account).filter(
        Account.bank_connection_id == connection.id,
    ).all()
    if not linked:
        return 0

    by_uid = {
        uid: a
        for a in linked
        if (uid := SyncService._resolve_account_external_id(a))
    }
    # IBAN maps to a list, not a single account: multi-currency accounts share
    # one IBAN, and collapsing them would leave all but one holding a dead uid —
    # which fails the whole connection sync, since a per-account failure re-raises
    # (tasks.enable_banking_tasks).
    by_iban_hash: dict = {}
    for a in linked:
        if a.iban_hash:
            by_iban_hash.setdefault(a.iban_hash, []).append(a)
    claimed: set = set()

    repointed = 0
    for raw in raw_accounts:
        uid = raw.get("uid") or raw.get("id")
        if not uid:
            continue

        account = by_uid.get(uid)
        if account is None:
            # Currency breaks the tie between accounts sharing an IBAN. Choosing
            # arbitrarily would file one currency's transactions under the other
            # currency's account.
            iban = _extract_iban(raw) or _extract_iban(raw.get("account_id"))
            currency = (raw.get("currency") or "").upper()
            candidates = [
                a
                for h in blind_index_candidates(iban)
                for a in by_iban_hash.get(h, ())
                if a.id not in claimed
            ]
            # With several candidates and no currency agreeing, guessing would file
            # one currency's transactions under another's account. Leave it
            # unmapped: its sync fails loudly, which beats silent misfiling.
            account = next(
                (a for a in candidates if (a.currency or "").upper() == currency),
                candidates[0] if len(candidates) == 1 else None,
            )
        if account is None:
            logger.info(
                "Reconnect: bank account %s on connection %s matched no mapped account, skipping",
                uid, connection.id,
            )
            continue

        SyncService._set_account_external_id_fields(account, uid)
        claimed.add(account.id)
        repointed += 1

    return repointed


# --- Routes ---

@router.get("/aspsps")
def list_aspsps(country: Optional[str] = None, user_id: str = Depends(get_user_id)):
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
    """Generate bank authorization URL for PSU redirect.

    With body.connection_id set, the resulting consent renews that connection
    instead of creating a new one — its accounts stay mapped and no wizard runs.
    """
    client = _get_eb_client()

    if body.connection_id:
        owned = db.query(BankConnection).filter(
            BankConnection.id == body.connection_id,
            BankConnection.user_id == user_id,
        ).first()
        if not owned:
            raise HTTPException(status_code=404, detail="Connection not found")

    # Generate a random state nonce (don't leak user_id in the redirect URL).
    # The connection being renewed rides along here, server-side, so a tampered
    # callback cannot re-point a connection the user did not choose.
    state_nonce = str(uuid_mod.uuid4())
    state_payload = json.dumps({"user_id": user_id, "connection_id": body.connection_id})
    try:
        r = _get_redis()
        # 30 min, not the previous 10: a PSU opening the bank app for 2FA can
        # easily take longer, and an expired nonce drops a renewal onto the
        # first-time-connect path, where the accounts are still held by the old
        # connection and the wizard can only offer "create new" — duplicates.
        r.setex(f"eb:state:{state_nonce}", AUTH_STATE_TTL, state_payload)
    except Exception:
        # Losing the state degrades a renewal into a second connection, and from
        # there into duplicate accounts, so a renewal fails before the redirect
        # rather than continuing.
        # ponytail: Redis dying mid-redirect still lands on the wizard; move the
        # intent to Postgres if that window ever bites.
        if body.connection_id:
            raise HTTPException(
                status_code=503,
                detail="Cannot start the reconnect right now. Please try again.",
            )
        logger.warning("Failed to store OAuth state in Redis")

    auth_payload = {
        "access": {
            "valid_until": (datetime.now(timezone.utc) + timedelta(days=90)).strftime("%Y-%m-%dT%H:%M:%S.000Z"),
        },
        "aspsp": {
            "name": body.aspsp_name,
            "country": body.aspsp_country.upper(),
        },
        "state": state_nonce,
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

    When the state nonce carries a connection_id, the consent renews that
    connection in place instead: its accounts keep their mapping, their uids are
    re-pointed at the new consent, and a sync is dispatched immediately.
    """
    state_payload = _read_auth_state(body.state, user_id)

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
            consent_expires_at = datetime.now(timezone.utc) + timedelta(days=90)
    else:
        consent_expires_at = datetime.now(timezone.utc) + timedelta(days=90)

    accounts_count = len(session_data.get("accounts", []))

    # A state that was supplied but could not be read — Redis unreachable, or a
    # nonce that outlived its TTL — leaves the renewal intent unknown. Falling
    # through would open a second connection to a bank the user already has, and
    # the wizard could then only offer "create new": duplicate accounts, the very
    # thing this flow exists to prevent. Refuse, and let them retry from Settings.
    # An unambiguous first-time connect still proceeds, as it always has.
    if body.state and not state_payload:
        # Normalized like the takeover check below: an exact comparison would miss
        # a stored name differing only by case or padding, fall through, and open
        # the second connection this guard exists to prevent.
        already_connected = db.query(BankConnection).filter(
            BankConnection.user_id == user_id,
            func.lower(func.trim(BankConnection.aspsp_name)) == aspsp_name.strip().lower(),
            BankConnection.status != "disconnected",
        ).first()
        if already_connected:
            raise HTTPException(
                status_code=409,
                detail=(
                    f"You are already connected to {aspsp_name}, and this "
                    "authorization could not be confirmed. Reconnect that bank from "
                    "Settings › Bank Connections instead of connecting it again."
                ),
            )

    reconnect_id = state_payload.get("connection_id")
    if reconnect_id:
        connection = db.query(BankConnection).filter(
            BankConnection.id == reconnect_id,
            BankConnection.user_id == user_id,
        ).first()
        if not connection:
            raise HTTPException(status_code=404, detail="Connection to reconnect not found")

        # Authorizing a different bank must never take over this connection: its
        # accounts would then be re-pointed at another institution's uids.
        if (connection.aspsp_name or "").strip().lower() != aspsp_name.strip().lower():
            raise HTTPException(
                status_code=400,
                detail=(
                    f"This authorization is for {aspsp_name}, but the connection "
                    f"being reconnected is with {connection.aspsp_name}."
                ),
            )

        connection.session_id = session_id
        connection.consent_expires_at = consent_expires_at
        connection.status = "active"
        connection.last_sync_error = None
        repointed = _repoint_account_uids(db, connection, session_data.get("accounts", []))
        db.commit()

        logger.info(
            "Reconnected connection %s (%s): re-pointed %d of %d accounts",
            connection.id, connection.aspsp_name, repointed, accounts_count,
        )

        # Each account resumes from its own last_synced_at, so the gap since the
        # consent lapsed is backfilled without asking for a lookback window.
        try:
            from tasks.enable_banking_tasks import sync_bank_connection
            sync_bank_connection.delay(str(connection.id))
        except Exception:
            logger.warning("Failed to dispatch sync task after reconnect", exc_info=True)

        return SessionResponse(
            connection_id=str(connection.id),
            accounts_count=accounts_count,
            reconnected=True,
        )

    # Create bank_connections row (status=pending_setup; accounts mapped in a separate step)
    connection = BankConnection(
        user_id=user_id,
        provider="enable_banking",
        session_id=session_id,
        aspsp_name=aspsp_name,
        aspsp_country=aspsp_country,
        consent_expires_at=consent_expires_at,
        status="pending_setup",
        raw_session_data=session_data,
    )
    db.add(connection)
    db.commit()
    db.refresh(connection)

    return SessionResponse(
        connection_id=str(connection.id),
        accounts_count=accounts_count,
    )


@router.post("/connections/{connection_id}/map-accounts", response_model=MapAccountsResponse)
def map_accounts(
    connection_id: str,
    request: MapAccountsRequest,
    db: Session = Depends(get_db),
    user_id: str = Depends(get_user_id),
):
    """
    Map bank accounts to new or existing accounts and activate the connection.
    Called after POST /session as the second step of the account mapping wizard.
    """
    VALID_SYNC_DAYS = {30, 60, 90, 180, 365, 730}
    if request.initial_sync_days not in VALID_SYNC_DAYS:
        raise HTTPException(
            status_code=400,
            detail=f"initial_sync_days must be one of {sorted(VALID_SYNC_DAYS)}",
        )

    # Validate connection exists, belongs to user, and is pending setup
    connection = db.query(BankConnection).filter(
        BankConnection.id == connection_id,
        BankConnection.user_id == user_id,
    ).first()
    if not connection:
        raise HTTPException(status_code=404, detail="Connection not found")
    if connection.status != "pending_setup":
        raise HTTPException(
            status_code=400,
            detail=f"Connection is not in pending_setup state (current: {connection.status})",
        )

    # One account per bank account, both ways. Without this, a repeated
    # existing_account_id would pass the link guard on its second use — the
    # first link already moved the account onto this very connection, which is
    # not "active" yet — and silently overwrite the uid written moments before,
    # leaving one bank account mapped to nothing.
    # existing_account_id is compared case-insensitively: Postgres parses a UUID
    # without regard to case, so two spellings of one id would slip past an exact
    # match and both resolve to the same account. bank_uid is an opaque token
    # from the bank and is compared as sent.
    for field, label, normalize in (
        ("existing_account_id", "account", lambda v: v.strip().lower()),
        ("bank_uid", "bank account", lambda v: v),
    ):
        seen = [normalize(getattr(m, field)) for m in request.mappings if getattr(m, field)]
        duplicate = next((v for v in seen if seen.count(v) > 1), None)
        if duplicate:
            raise HTTPException(
                status_code=400,
                detail=f"The same {label} '{duplicate}' appears in more than one mapping",
            )

    # Index raw bank accounts by UID for quick lookup
    raw_accounts = connection.raw_session_data.get("accounts", []) if connection.raw_session_data else []
    raw_by_uid = {acc["uid"]: acc for acc in raw_accounts}

    accounts_created = 0
    accounts_linked = 0

    for mapping in request.mappings:
        acc_data = raw_by_uid.get(mapping.bank_uid)
        if not acc_data:
            raise HTTPException(
                status_code=400,
                detail=f"No bank account found with uid '{mapping.bank_uid}' in session data",
            )

        if mapping.action == "create":
            name = (
                mapping.name
                or acc_data.get("account_name")
                or acc_data.get("iban")
                or "Unknown Account"
            )
            new_account = Account(
                user_id=user_id,
                name=name,
                account_type=_ACCOUNT_TYPE_MAP.get((acc_data.get("cash_account_type") or "").upper(), "checking"),
                currency=acc_data.get("currency", "EUR"),
                provider="enable_banking",
                institution=connection.aspsp_name,
                bank_connection_id=connection.id,
                external_id=mapping.bank_uid,
            )
            encrypted = encrypt_value(mapping.bank_uid)
            hashed = blind_index(mapping.bank_uid)
            new_account.external_id_hash = hashed
            if encrypted:
                new_account.external_id_ciphertext = encrypted
            db.add(new_account)
            accounts_created += 1

        elif mapping.action == "link":
            if not mapping.existing_account_id:
                raise HTTPException(
                    status_code=400,
                    detail=f"existing_account_id is required for action 'link' (uid: {mapping.bank_uid})",
                )
            existing = db.query(Account).filter(
                Account.id == mapping.existing_account_id,
                Account.user_id == user_id,
            ).first()
            if not existing:
                raise HTTPException(
                    status_code=404,
                    detail=f"Account '{mapping.existing_account_id}' not found",
                )
            # Only a live consent blocks re-linking. Refusing accounts held by an
            # expired one is what forced users to disconnect before reconnecting,
            # and that detour is where duplicate accounts came from.
            if _is_held_by_active_connection(db, existing):
                raise HTTPException(
                    status_code=400,
                    detail=(
                        f"Account '{mapping.existing_account_id}' is already linked to an "
                        "active bank connection"
                    ),
                )
            existing.bank_connection_id = connection.id
            existing.provider = "enable_banking"
            existing.external_id = mapping.bank_uid
            encrypted = encrypt_value(mapping.bank_uid)
            hashed = blind_index(mapping.bank_uid)
            existing.external_id_hash = hashed
            if encrypted:
                existing.external_id_ciphertext = encrypted
            accounts_linked += 1

        else:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid action '{mapping.action}'. Must be 'create' or 'link'",
            )

    connection.initial_sync_days = request.initial_sync_days
    connection.status = "active"
    connection.raw_session_data = None  # Clear sensitive data now that mapping is complete
    db.commit()

    # Trigger initial sync
    try:
        from tasks.enable_banking_tasks import sync_bank_connection
        sync_bank_connection.delay(str(connection.id))
    except Exception:
        logger.warning("Failed to dispatch sync task after map-accounts", exc_info=True)

    return MapAccountsResponse(
        connection_id=str(connection.id),
        accounts_created=accounts_created,
        accounts_linked=accounts_linked,
    )


@router.post("/connections/{connection_id}/recategorize", response_model=SyncTriggerResponse)
def recategorize_connection(
    connection_id: str,
    user_id: str = Depends(get_user_id),
    db: Session = Depends(get_db),
):
    """
    Re-run batch AI categorization for ALL transactions on a connection.

    Useful after a categorization bug — overwrites wrong system-assigned categories
    while preserving any user-assigned category_id overrides.
    """
    from app.models import Transaction

    connection = db.query(BankConnection).filter(
        BankConnection.id == connection_id,
        BankConnection.user_id == user_id,
    ).first()
    if not connection:
        raise HTTPException(status_code=404, detail="Connection not found")

    account_ids = [
        str(a.id)
        for a in db.query(Account).filter(Account.bank_connection_id == connection.id).all()
    ]
    if not account_ids:
        raise HTTPException(status_code=404, detail="No accounts found for this connection")

    transaction_ids = [
        str(t.id)
        for t in db.query(Transaction.id).filter(
            Transaction.user_id == user_id,
            Transaction.account_id.in_(account_ids),
        ).all()
    ]

    if not transaction_ids:
        return SyncTriggerResponse(message="No transactions to re-categorize")

    try:
        from tasks.post_import_pipeline import post_import_pipeline
        task = post_import_pipeline.delay(
            user_id=user_id,
            account_ids=account_ids,
            transaction_ids=transaction_ids,
            is_initial_sync=False,
        )
        return SyncTriggerResponse(
            message=f"Re-categorization started for {len(transaction_ids)} transactions",
            task_id=task.id,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to start re-categorization: {str(e)}")


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

    # Read live sync progress from Redis (set by Celery worker)
    sync_progress = None
    try:
        r = redis.from_url(REDIS_URL, decode_responses=True)
        raw = r.get(f"sync_progress:{connection_id}")
        if raw:
            data = json.loads(raw)
            sync_progress = SyncProgress(**data)
    except Exception:
        pass

    return ConnectionStatusResponse(
        id=str(connection.id),
        aspsp_name=connection.aspsp_name,
        aspsp_country=connection.aspsp_country,
        status=connection.status,
        last_synced_at=connection.last_synced_at.isoformat() if connection.last_synced_at else None,
        consent_expires_at=connection.consent_expires_at.isoformat() if connection.consent_expires_at else None,
        last_sync_error=connection.last_sync_error,
        accounts_count=accounts_count,
        sync_progress=sync_progress,
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


def _is_held_by_active_connection(db: Session, account: Account) -> bool:
    """True if another, still-live consent owns this account.

    Such an account cannot be re-linked: moving it would silently break the
    working connection. An account held by an expired or errored consent is fair
    game — re-linking it is exactly how a renewal is meant to work.

    A lapsed consent is treated as dead even while its row still says "active":
    check_consent_expiry only runs daily, and until it does, the status lags
    reality and would block exactly the relink the user came to do.
    """
    if account.bank_connection_id is None:
        return False
    holder = db.query(BankConnection).filter(
        BankConnection.id == account.bank_connection_id,
    ).first()
    if holder is None or holder.status != "active":
        return False
    if holder.consent_expires_at is None:
        return True
    expires_at = holder.consent_expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    return expires_at > datetime.now(timezone.utc)


def _find_account_for_bank_account(
    db: Session,
    user_id: str,
    uid: str,
    iban: Optional[str],
    currency: Optional[str] = None,
) -> Optional[Account]:
    """Locate the user's account for one bank account, by uid and then by IBAN.

    The IBAN leg is what makes re-connecting work at all: Enable Banking mints a
    new account uid on every authorization, so uid alone misses whenever the user
    reconnects, the wizard falls back to "create new", and the same real account
    is added a second time.

    Accounts held by a live connection are skipped — see
    _is_held_by_active_connection.
    """
    query = db.query(Account).filter(Account.user_id == user_id)

    # The uid identifies one account exactly, so it needs no tie-break.
    if uid:
        uid_hashes = blind_index_candidates(uid)
        by_uid = []
        if uid_hashes:
            by_uid = query.filter(Account.external_id_hash.in_(uid_hashes)).all()
        if not by_uid:
            # Deployments without encryption configured keep the uid in plaintext.
            by_uid = query.filter(Account.external_id == uid).all()
        for account in by_uid:
            if not _is_held_by_active_connection(db, account):
                return account

    if not iban:
        return None
    iban_hashes = blind_index_candidates(iban)
    if not iban_hashes:
        return None
    candidates = [
        account
        for account in query.filter(Account.iban_hash.in_(iban_hashes)).all()
        if not _is_held_by_active_connection(db, account)
    ]
    if not candidates:
        return None
    if len(candidates) == 1:
        return candidates[0]

    # Multi-currency accounts share one IBAN, and .all() gives no meaningful
    # order. Only currency can tell them apart; without it, auto-linking would
    # file one currency's transactions under another currency's account, so
    # leave it for the user to map by hand.
    wanted = (currency or "").upper()
    matches = [a for a in candidates if (a.currency or "").upper() == wanted]
    return matches[0] if len(matches) == 1 else None


def _build_suggested_mappings(
    db: Session,
    user_id: str,
    raw_accounts: list,
) -> list:
    """Suggest, for each bank account, the user's existing account to link to.

    Matching is by uid first and IBAN second, so an account the user already has
    is recognized after a re-consent rather than duplicated.
    """
    results = []
    for raw_acc in raw_accounts:
        uid = raw_acc.get("uid") or raw_acc.get("id") or ""
        bank_name = raw_acc.get("account_name") or raw_acc.get("name") or "Bank Account"
        iban = _extract_iban(raw_acc) or _extract_iban(raw_acc.get("account_id"))

        if not uid and not iban:
            results.append({
                "bank_uid": uid,
                "bank_name": bank_name,
                "suggested_action": "create",
                "suggested_account_id": None,
                "suggested_account_name": None,
            })
            continue

        existing = _find_account_for_bank_account(
            db, user_id, uid, iban, raw_acc.get("currency")
        )

        if existing:
            results.append({
                "bank_uid": uid,
                "bank_name": bank_name,
                "suggested_action": "link",
                "suggested_account_id": str(existing.id),
                "suggested_account_name": existing.name,
            })
        else:
            results.append({
                "bank_uid": uid,
                "bank_name": bank_name,
                "suggested_action": "create",
                "suggested_account_id": None,
                "suggested_account_name": None,
            })

    return results


@router.get("/connections/{connection_id}/suggested-mappings", response_model=List[SuggestedMapping])
def get_suggested_mappings(
    connection_id: str,
    user_id: str = Depends(get_user_id),
    db: Session = Depends(get_db),
):
    """
    Return suggested account mappings for the map-accounts wizard.

    For each bank account UID in the connection's raw session data, checks
    whether the user already has an account with that external_id_hash and
    suggests 'link' or 'create' accordingly. Requires connection in pending_setup status.
    """
    connection = db.query(BankConnection).filter(
        BankConnection.id == connection_id,
        BankConnection.user_id == user_id,
    ).first()
    if not connection:
        raise HTTPException(status_code=404, detail="Connection not found")
    if connection.status != "pending_setup":
        raise HTTPException(
            status_code=400,
            detail="Suggested mappings are only available for connections in pending_setup status",
        )

    raw_accounts = (connection.raw_session_data or {}).get("accounts", [])
    suggestions = _build_suggested_mappings(
        db=db,
        user_id=user_id,
        raw_accounts=raw_accounts,
    )
    return suggestions


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

    # Unlink accounts so they can be re-linked to a new connection later.
    # external_id, external_id_ciphertext, and external_id_hash are preserved
    # so that re-auth can auto-match accounts by their stable bank UIDs.
    db.query(Account).filter(
        Account.bank_connection_id == connection.id,
    ).update(
        {
            Account.bank_connection_id: None,
            Account.provider: None,
        },
        synchronize_session=False,
    )

    db.commit()

    return {"message": "Bank connection disconnected"}
