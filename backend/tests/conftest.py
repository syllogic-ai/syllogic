"""
Shared pytest fixtures for the backend test suite.

Provides a `db_session` fixture that yields a SQLAlchemy session connected
to the development/test database defined by `app.database.SessionLocal`.
Each test gets a fresh session; the session is rolled back on teardown so
test data does not persist between runs.

Tests that need to query the database via the MCP tools (which call
`app.mcp.dependencies.get_db`) should use this fixture to seed data, then
rely on the tools to open their own short-lived sessions.
"""
from __future__ import annotations

import base64
import os
import sys

# Ensure the backend/ directory is importable when pytest is run from anywhere.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _set_test_env() -> None:
    """Deterministic encryption keys so blind_index/encrypted fields work in tests."""
    key = base64.urlsafe_b64encode(b"p" * 32).decode("utf-8").rstrip("=")
    os.environ.setdefault("DATA_ENCRYPTION_KEY_CURRENT", key)
    os.environ.setdefault("DATA_ENCRYPTION_KEY_ID", "k-test-conftest")
    os.environ.pop("DATA_ENCRYPTION_KEY_PREVIOUS", None)
    # The broker-trade import runs a yfinance + FX backfill in production to
    # populate historical HoldingValuation / AccountBalance rows. Disable it
    # by default in tests; tests that exercise backfill set it explicitly.
    os.environ.setdefault("BROKER_BACKFILL_ENABLED", "0")


_set_test_env()

import pytest  # noqa: E402

from app.database import SessionLocal  # noqa: E402
from app.security.data_encryption import reset_encryption_config_cache  # noqa: E402


reset_encryption_config_cache()


@pytest.fixture
def db_session():
    """Yield a SQLAlchemy session; roll back and close on teardown."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        session.close()
