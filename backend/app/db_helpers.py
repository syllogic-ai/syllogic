"""
Database helper utilities for handling user context and authentication.
"""
from typing import Optional
from sqlalchemy.orm import Session
from app.models import User
from app.mcp.auth import validate_api_key, get_user_from_env


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


def get_user_id(user_id: Optional[str] = None, api_key: Optional[str] = None) -> str:
    """
    Get user ID with authentication priority:
    1. Explicit user_id (HTTP mode with validated auth)
    2. API key parameter
    3. Environment variable API key (stdio mode)

    Args:
        user_id: Optional explicit user ID (pre-validated)
        api_key: Optional API key to validate

    Returns:
        User ID string

    Raises:
        ValueError: If no valid authentication is found
    """
    # Priority 1: Explicit user_id (already validated upstream)
    if user_id:
        return user_id

    # Priority 2: API key parameter
    if api_key:
        resolved = validate_api_key(api_key)
        if resolved:
            return resolved

    # Priority 3: Environment variable (stdio mode)
    env_user = get_user_from_env()
    if env_user:
        return env_user

    raise ValueError(
        "No valid authentication. Provide an API key via the "
        "PERSONAL_FINANCE_API_KEY environment variable."
    )
