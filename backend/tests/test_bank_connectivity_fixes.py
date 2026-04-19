"""Tests for bank connectivity audit fixes."""
import sys
import os
import unittest
from unittest.mock import MagicMock, patch, call
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestDisconnectPreservesExternalId(unittest.TestCase):
    """Disconnect should clear bank_connection_id + provider but keep external_id fields."""

    def test_disconnect_does_not_clear_external_id(self):
        """Account.external_id, external_id_ciphertext, external_id_hash are preserved."""
        from unittest.mock import MagicMock, patch
        from app.routes.enable_banking import router

        # Build a minimal fake FastAPI request environment
        mock_db = MagicMock()
        mock_connection = MagicMock()
        mock_connection.id = "conn-1"
        mock_connection.session_id = "sess-1"
        mock_connection.user_id = "user-1"

        mock_db.query.return_value.filter.return_value.first.return_value = mock_connection

        with patch("app.routes.enable_banking._get_eb_client") as mock_client:
            mock_client.return_value.delete.return_value = MagicMock()

            # Call the disconnect route function directly (FastAPI dependency injection
            # is bypassed by passing parameters explicitly)
            from app.routes.enable_banking import disconnect
            result = disconnect(
                connection_id="conn-1",
                user_id="user-1",
                db=mock_db,
            )

        # Verify the bulk update was called
        update_call_args = mock_db.query.return_value.filter.return_value.update.call_args
        self.assertIsNotNone(update_call_args, "Expected db.query().filter().update() to be called")
        update_dict = update_call_args[0][0]

        # Must clear connection link and provider
        from app.models import Account
        self.assertIn(Account.bank_connection_id, update_dict)
        self.assertIsNone(update_dict[Account.bank_connection_id])
        self.assertIn(Account.provider, update_dict)
        self.assertIsNone(update_dict[Account.provider])

        # Must NOT touch external_id fields
        self.assertNotIn(Account.external_id, update_dict)
        self.assertNotIn(Account.external_id_ciphertext, update_dict)
        self.assertNotIn(Account.external_id_hash, update_dict)


class TestSyncIdempotencyGuard(unittest.TestCase):
    """sync_bank_connection should skip if a sync ran recently or is in progress."""

    def _make_connection(self, last_synced_at=None, sync_started_at=None, status="active"):
        conn = MagicMock()
        conn.id = "conn-1"
        conn.user_id = "user-1"
        conn.status = status
        conn.last_synced_at = last_synced_at
        conn.sync_started_at = sync_started_at
        conn.initial_sync_days = 90
        conn.session_id = "sess-1"
        return conn

    def _run_task(self, connection):
        """Run the sync guard logic extracted from the task."""
        from tasks.enable_banking_tasks import _should_skip_sync
        return _should_skip_sync(connection)

    def test_skips_when_synced_within_5_minutes(self):
        conn = self._make_connection(
            last_synced_at=datetime.now(timezone.utc) - timedelta(minutes=2)
        )
        self.assertTrue(self._run_task(conn))

    def test_does_not_skip_when_synced_6_minutes_ago(self):
        conn = self._make_connection(
            last_synced_at=datetime.now(timezone.utc) - timedelta(minutes=6)
        )
        self.assertFalse(self._run_task(conn))

    def test_skips_when_sync_in_progress(self):
        conn = self._make_connection(
            sync_started_at=datetime.now(timezone.utc) - timedelta(minutes=3)
        )
        self.assertTrue(self._run_task(conn))

    def test_does_not_skip_on_initial_sync(self):
        """last_synced_at=None means first sync ever — never skip."""
        conn = self._make_connection(last_synced_at=None, sync_started_at=None)
        self.assertFalse(self._run_task(conn))

    def test_does_not_skip_stale_sync_started_at(self):
        """sync_started_at older than 10 min = stale/crashed, allow re-sync."""
        conn = self._make_connection(
            sync_started_at=datetime.now(timezone.utc) - timedelta(minutes=11)
        )
        self.assertFalse(self._run_task(conn))


if __name__ == "__main__":
    unittest.main()
