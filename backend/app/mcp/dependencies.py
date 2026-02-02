"""
Database session management for MCP tools.
"""
from contextlib import contextmanager
from datetime import datetime
from uuid import UUID

from app.database import SessionLocal


def validate_uuid(value: str) -> UUID | None:
    """
    Safely parse UUID, returning None if invalid.

    Args:
        value: String to parse as UUID

    Returns:
        UUID object or None if invalid
    """
    try:
        return UUID(value)
    except (ValueError, TypeError):
        return None


def validate_date(value: str | None) -> datetime | None:
    """
    Safely parse ISO date, returning None if invalid.

    Args:
        value: ISO format date string (optional)

    Returns:
        datetime object or None if invalid/empty
    """
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except (ValueError, TypeError):
        return None


@contextmanager
def get_db():
    """
    Context manager for database sessions.
    Ensures proper cleanup after each tool invocation.

    Usage:
        with get_db() as db:
            result = db.query(Model).all()
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
