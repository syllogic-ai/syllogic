"""
API Key authentication for the MCP server.
Validates API keys and resolves them to user IDs.
"""
import os
import hashlib
from datetime import datetime
from typing import Optional

from app.database import SessionLocal
from app.models import ApiKey


def hash_api_key(key: str) -> str:
    """Hash an API key using SHA-256."""
    return hashlib.sha256(key.encode()).hexdigest()


def validate_api_key(api_key: str) -> Optional[str]:
    """
    Validate an API key and return the associated user_id.

    Args:
        api_key: The raw API key string (e.g., "pf_abc123...")

    Returns:
        The user_id if the key is valid, None otherwise.
    """
    if not api_key or not api_key.startswith("pf_"):
        return None

    key_hash = hash_api_key(api_key)
    db = SessionLocal()
    try:
        record = db.query(ApiKey).filter(ApiKey.key_hash == key_hash).first()
        if not record:
            return None

        # Check if expired
        if record.expires_at and record.expires_at < datetime.utcnow():
            return None

        # Update last_used_at timestamp
        record.last_used_at = datetime.utcnow()
        db.commit()

        return record.user_id
    finally:
        db.close()


def get_user_from_env() -> Optional[str]:
    """
    Get user ID from PERSONAL_FINANCE_API_KEY environment variable.
    Used for stdio mode (Claude Desktop configuration).

    Returns:
        The user_id if a valid API key is found in env, None otherwise.
    """
    api_key = os.environ.get("PERSONAL_FINANCE_API_KEY")
    if not api_key:
        return None
    return validate_api_key(api_key)
