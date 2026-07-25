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


class TestPerAccountSyncStartDate(unittest.TestCase):
    """Each account should use its own last_synced_at as the sync start date."""

    def test_previously_synced_account_uses_account_last_synced_at(self):
        """An account with last_synced_at gets start_date = last_synced_at - 1 day."""
        from tasks.enable_banking_tasks import _account_sync_start_date

        account = MagicMock()
        account.last_synced_at = datetime(2026, 4, 10, 12, 0, 0, tzinfo=timezone.utc)

        connection = MagicMock()
        connection.initial_sync_days = 90

        start = _account_sync_start_date(account, connection)
        expected = datetime(2026, 4, 9, tzinfo=timezone.utc).date()
        self.assertEqual(start, expected)

    def test_new_account_uses_initial_sync_days(self):
        """An account with no last_synced_at uses the connection's initial_sync_days."""
        from tasks.enable_banking_tasks import _account_sync_start_date

        account = MagicMock()
        account.last_synced_at = None

        connection = MagicMock()
        connection.initial_sync_days = 30

        now = datetime.now(timezone.utc)
        start = _account_sync_start_date(account, connection)
        expected = (now - timedelta(days=30)).date()
        self.assertEqual(start, expected)


class TestSuggestedMappings(unittest.TestCase):
    """GET /connections/{id}/suggested-mappings returns link suggestion for known accounts."""

    def test_returns_link_suggestion_for_known_external_id(self):
        from app.routes.enable_banking import _build_suggested_mappings

        # Simulate: one known account (blind index matches), one unknown
        existing_account = MagicMock()
        existing_account.id = "acc-uuid-1"
        existing_account.name = "My Savings"
        existing_account.external_id_hash = "hash-abc"

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = existing_account

        raw_accounts = [
            {"uid": "bank-uid-1", "account_name": "Savings Account"},
            {"uid": "bank-uid-2", "account_name": "New Current Account"},
        ]

        with patch("app.routes.enable_banking.blind_index") as mock_bi:
            # bank-uid-1 matches existing_account hash, bank-uid-2 does not
            mock_bi.side_effect = lambda uid: "hash-abc" if uid == "bank-uid-1" else "hash-xyz"

            # We need different first() results per UID — adjust the mock
            call_count = [0]
            def first_side_effect():
                call_count[0] += 1
                if call_count[0] == 1:
                    return existing_account  # bank-uid-1 matches
                return None  # bank-uid-2 does not match

            mock_db.query.return_value.filter.return_value.first.side_effect = first_side_effect

            result = _build_suggested_mappings(
                db=mock_db,
                user_id="user-1",
                raw_accounts=raw_accounts,
            )

        self.assertEqual(len(result), 2)
        match = next(r for r in result if r["bank_uid"] == "bank-uid-1")
        no_match = next(r for r in result if r["bank_uid"] == "bank-uid-2")

        self.assertEqual(match["suggested_action"], "link")
        self.assertEqual(match["suggested_account_id"], "acc-uuid-1")
        self.assertEqual(match["suggested_account_name"], "My Savings")

        self.assertEqual(no_match["suggested_action"], "create")
        self.assertIsNone(no_match["suggested_account_id"])

    def test_falls_back_to_iban_when_external_id_is_unknown(self):
        """Re-authorization mints a new uid; the IBAN still identifies the account.

        Without the fallback the wizard suggests "create", producing a
        duplicate of an account the user already has.
        """
        from app.routes.enable_banking import _build_suggested_mappings

        existing_account = MagicMock()
        existing_account.id = "acc-uuid-1"
        existing_account.name = "ABN AMRO Giannis"

        mock_db = MagicMock()

        # The uid lookup misses (new uid after re-consent); the IBAN lookup hits.
        results_by_hash = {"iban-hash": existing_account, "new-uid-hash": None}
        captured = []

        def filter_side_effect(*args, **kwargs):
            captured.append(args)
            holder = MagicMock()
            # The second positional filter is the hash comparison; decide from
            # whichever hash the production code looked up most recently.
            holder.first.return_value = results_by_hash.get(lookup["hash"])
            return holder

        lookup = {"hash": None}

        def blind_index_side_effect(value):
            mapping = {
                "eb-new-uid": "new-uid-hash",
                "NL64ABNA0123453784": "iban-hash",
            }
            lookup["hash"] = mapping.get(value)
            return lookup["hash"]

        mock_db.query.return_value.filter.side_effect = filter_side_effect

        with patch("app.routes.enable_banking.blind_index", side_effect=blind_index_side_effect):
            result = _build_suggested_mappings(
                db=mock_db,
                user_id="user-1",
                raw_accounts=[
                    {
                        "uid": "eb-new-uid",
                        "account_name": "I KOTSAKIACHIDIS",
                        "iban": "NL64 ABNA 0123 4537 84",
                    }
                ],
            )

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["suggested_action"], "link")
        self.assertEqual(result[0]["suggested_account_id"], "acc-uuid-1")
        self.assertEqual(result[0]["suggested_account_name"], "ABN AMRO Giannis")

    def test_unhashable_values_do_not_match_an_arbitrary_account(self):
        """A null blind index must not compile to `hash IS NULL` and match anything."""
        from app.routes.enable_banking import _build_suggested_mappings

        stray_account = MagicMock()
        stray_account.id = "acc-uuid-stray"
        stray_account.name = "Unrelated Account"

        mock_db = MagicMock()
        # Any query that reaches the DB returns a row — so if the production
        # code queries at all with a null hash, the test fails.
        mock_db.query.return_value.filter.return_value.first.return_value = stray_account

        with patch("app.routes.enable_banking.blind_index", return_value=None):
            result = _build_suggested_mappings(
                db=mock_db,
                user_id="user-1",
                raw_accounts=[{"uid": "some-uid", "account_name": "X", "iban": "NL64ABNA0123453784"}],
            )

        self.assertEqual(result[0]["suggested_action"], "create")
        self.assertIsNone(result[0]["suggested_account_id"])


class TestRelinkableConnectionStatuses(unittest.TestCase):
    """Accounts on a dead connection must be re-linkable after re-authorization."""

    def test_dead_statuses_cover_every_non_syncing_state(self):
        from app.routes.enable_banking import _RELINKABLE_CONNECTION_STATUSES

        # These are the states a connection lands in when it stops syncing.
        # If one were missing, its accounts would be permanently unlinkable
        # and the user would be forced to create a duplicate.
        for status in ("expired", "disconnected", "error"):
            self.assertIn(status, _RELINKABLE_CONNECTION_STATUSES)

        # An active connection is a genuine conflict and must NOT be included.
        self.assertNotIn("active", _RELINKABLE_CONNECTION_STATUSES)
        self.assertNotIn("pending_setup", _RELINKABLE_CONNECTION_STATUSES)

    def test_frontend_and_backend_status_lists_agree(self):
        """The wizard offers the account; the API must accept it.

        If these two lists drift, the account is shown as linkable and then
        rejected on submit — a dead end for the user.
        """
        import pathlib
        import re

        from app.routes.enable_banking import _RELINKABLE_CONNECTION_STATUSES

        ts_path = (
            pathlib.Path(__file__).resolve().parents[2]
            / "frontend"
            / "lib"
            / "actions"
            / "bank-connections.ts"
        )
        if not ts_path.exists():  # backend-only checkout
            self.skipTest("frontend source not present")

        source = ts_path.read_text(encoding="utf-8")
        match = re.search(
            r"DEAD_CONNECTION_STATUSES\s*=\s*\[([^\]]*)\]", source, re.S
        )
        self.assertIsNotNone(match, "DEAD_CONNECTION_STATUSES not found in frontend")
        frontend_statuses = set(re.findall(r'"([^"]+)"', match.group(1)))

        self.assertEqual(
            frontend_statuses,
            set(_RELINKABLE_CONNECTION_STATUSES),
            "Frontend linkable-account filter and backend link guard disagree.",
        )


if __name__ == "__main__":
    unittest.main()
