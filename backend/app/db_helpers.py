"""
Database helper utilities for handling user context and authentication.
"""
import contextvars
import hashlib
import hmac
import os
import time
from typing import Mapping, Optional
from fastapi import HTTPException, status
from sqlalchemy.orm import Session
from mcp.server.auth.middleware.auth_context import get_access_token

from app.models import User
from app.mcp.auth import validate_api_key

INTERNAL_AUTH_USER_HEADER = "x-syllogic-user-id"
INTERNAL_AUTH_TIMESTAMP_HEADER = "x-syllogic-timestamp"
INTERNAL_AUTH_SIGNATURE_HEADER = "x-syllogic-signature"
DEFAULT_INTERNAL_AUTH_MAX_AGE_SECONDS = 60

_request_user_id: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "request_user_id",
    default=None,
)


def set_request_user_id(user_id: str) -> contextvars.Token:
    return _request_user_id.set(user_id)


def clear_request_user_id(token: contextvars.Token) -> None:
    _request_user_id.reset(token)


def get_request_user_id() -> Optional[str]:
    return _request_user_id.get()


def _get_internal_auth_secret() -> str:
    secret = os.getenv("INTERNAL_AUTH_SECRET", "").strip()
    if not secret:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal authentication secret is not configured.",
        )
    return secret


def _get_max_signature_age_seconds() -> int:
    raw_value = os.getenv(
        "INTERNAL_AUTH_MAX_AGE_SECONDS",
        str(DEFAULT_INTERNAL_AUTH_MAX_AGE_SECONDS),
    )
    try:
        parsed = int(raw_value)
        if parsed <= 0:
            return DEFAULT_INTERNAL_AUTH_MAX_AGE_SECONDS
        return parsed
    except ValueError:
        return DEFAULT_INTERNAL_AUTH_MAX_AGE_SECONDS


def _build_signature_payload(
    method: str,
    path_with_query: str,
    user_id: str,
    timestamp: str,
) -> str:
    return "\n".join(
        [
            method.upper(),
            path_with_query,
            user_id,
            timestamp,
        ]
    )


def authenticate_internal_request_from_headers(
    method: str,
    path_with_query: str,
    headers: Mapping[str, str],
) -> str:
    user_id = headers.get(INTERNAL_AUTH_USER_HEADER, "").strip()
    timestamp = headers.get(INTERNAL_AUTH_TIMESTAMP_HEADER, "").strip()
    signature = headers.get(INTERNAL_AUTH_SIGNATURE_HEADER, "").strip()

    if not user_id or not timestamp or not signature:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing internal authentication headers.",
        )

    try:
        timestamp_int = int(timestamp)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid internal authentication timestamp.",
        ) from exc

    now = int(time.time())
    max_age = _get_max_signature_age_seconds()
    if abs(now - timestamp_int) > max_age:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Expired internal authentication signature.",
        )

    secret = _get_internal_auth_secret()
    payload = _build_signature_payload(method, path_with_query, user_id, timestamp)
    expected_signature = hmac.new(
        secret.encode("utf-8"),
        payload.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()

    if not hmac.compare_digest(expected_signature, signature):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid internal authentication signature.",
        )

    return user_id


def get_or_create_system_user(db: Session) -> User:
    """
    Get or create a system user for backward compatibility.
    This allows the backend to work without authentication initially.

    Args:
        db: Database session

    Returns:
        User object for the system user
    """
    # This is kept for backward compatibility but should not be used
    # in production. All operations should require API key authentication.
    system_user_id = "test-user"
    user = db.query(User).filter(User.id == system_user_id).first()
    if not user:
        user = User(
            id=system_user_id,
            email="system@localhost",
            name="System User",
            email_verified=True
        )
        db.add(user)
        db.commit()
        db.refresh(user)
    return user


def _get_authenticated_user_id(api_key: Optional[str] = None) -> Optional[str]:
    """
    Resolve user_id from MCP auth context or an explicit API key.
    """
    token = get_access_token()
    if token is not None:
        # Prefer explicit claim if provided; fallback to client_id.
        claims = getattr(token, "claims", None) or {}
        return claims.get("user_id") or token.client_id

    if api_key:
        return validate_api_key(api_key)

    return None


def get_mcp_user_id(user_id: Optional[str] = None, api_key: Optional[str] = None) -> str:
    """
    Resolve user_id for MCP tool calls.
    Requires a valid bearer token or api_key parameter.
    """
    resolved = _get_authenticated_user_id(api_key)
    if not resolved:
        raise ValueError(
            "Authentication required. Provide a Bearer API key in the Authorization header."
        )

    if user_id and user_id != resolved:
        raise ValueError("Provided user_id does not match authenticated user.")

    return resolved


def get_user_id(user_id: Optional[str] = None, api_key: Optional[str] = None) -> str:
    """
    Get user ID with authentication priority:
    1. MCP auth context (Bearer token) or API key parameter
    2. Signed internal request identity

    Args:
        user_id: Optional explicit user ID (pre-validated)
        api_key: Optional API key to validate

    Returns:
        User ID string

    Raises:
        ValueError: If no valid authentication is found
    """
    # Priority 1: MCP auth context or API key parameter (if present)
    resolved = _get_authenticated_user_id(api_key)
    if resolved:
        return resolved

    request_user_id = get_request_user_id()
    if not request_user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required.",
        )

    if user_id and user_id != request_user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Provided user_id does not match authenticated user.",
        )

    return request_user_id
