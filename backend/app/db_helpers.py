"""
Database helper utilities for handling user context and authentication.
"""
from typing import Optional
from sqlalchemy.orm import Session
from mcp.server.auth.middleware.auth_context import get_access_token

from app.models import User
from app.mcp.auth import validate_api_key


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
    2. Explicit user_id (legacy / non-authenticated paths)

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

    # Priority 2: Explicit user_id (legacy / non-authenticated paths)
    if user_id:
        return user_id

    raise ValueError(
        "No valid authentication. Provide a Bearer API key in the Authorization header."
    )
