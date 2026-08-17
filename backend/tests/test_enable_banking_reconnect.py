"""Tests for Enable Banking consent renewal (reconnect an existing connection).

Enable Banking mints a new account uid on every re-authorization, and the
connection sync reads each account's stored uid directly, so a renewal that
fails to re-point those uids leaves every subsequent sync asking the bank for
accounts that no longer exist.
"""
import json
import os
import sys
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _account(name, uid=None, iban=None, currency="EUR"):
    """An unsaved Account with encrypted uid/IBAN fields populated."""
    from app.models import Account
    from app.services.sync_service import SyncService

    acc = Account(
        id=f"acct-{name}",
        user_id="user-1",
        name=name,
        account_type="checking",
        currency=currency,
    )
    if uid:
        SyncService._set_account_external_id_fields(acc, uid)
    if iban:
        SyncService._set_account_iban_fields(acc, iban)
    return acc


def _db_with_linked_accounts(accounts):
    db = MagicMock()
    db.query.return_value.filter.return_value.all.return_value = accounts
    return db


class TestRepointAccountUids(unittest.TestCase):
    def test_rotated_uid_is_matched_by_iban(self):
        """The uid changed at re-consent; the IBAN survives and identifies the account."""
        from app.routes.enable_banking import _repoint_account_uids
        from app.services.sync_service import SyncService

        acc = _account("Giannis", uid="old-uid", iban="NL01ABNA0123456789")
        db = _db_with_linked_accounts([acc])

        count = _repoint_account_uids(
            db,
            MagicMock(id="conn-1"),
            [{"uid": "new-uid", "iban": "NL01 ABNA 0123 456789"}],
        )

        self.assertEqual(count, 1)
        self.assertEqual(SyncService._resolve_account_external_id(acc), "new-uid")

    def test_unchanged_uid_still_matches(self):
        """A bank that keeps uids stable must not fall through to the IBAN path."""
        from app.routes.enable_banking import _repoint_account_uids
        from app.services.sync_service import SyncService

        acc = _account("Giannis", uid="same-uid", iban="NL01ABNA0123456789")
        db = _db_with_linked_accounts([acc])

        count = _repoint_account_uids(
            db, MagicMock(id="conn-1"), [{"uid": "same-uid", "iban": "NL01ABNA0123456789"}]
        )

        self.assertEqual(count, 1)
        self.assertEqual(SyncService._resolve_account_external_id(acc), "same-uid")

    def test_account_new_at_the_bank_is_skipped(self):
        """An unrecognized bank account must not steal a mapped account's uid."""
        from app.routes.enable_banking import _repoint_account_uids
        from app.services.sync_service import SyncService

        acc = _account("Giannis", uid="old-uid", iban="NL01ABNA0123456789")
        db = _db_with_linked_accounts([acc])

        count = _repoint_account_uids(
            db, MagicMock(id="conn-1"), [{"uid": "new-uid", "iban": "NL99RABO9999999999"}]
        )

        self.assertEqual(count, 0)
        self.assertEqual(SyncService._resolve_account_external_id(acc), "old-uid")

    def test_accounts_sharing_an_iban_are_claimed_once(self):
        """Multi-currency accounts share an IBAN; the second must not overwrite the first."""
        from app.routes.enable_banking import _repoint_account_uids
        from app.services.sync_service import SyncService

        acc = _account("Giannis", uid="old-uid", iban="NL01ABNA0123456789")
        db = _db_with_linked_accounts([acc])

        count = _repoint_account_uids(
            db,
            MagicMock(id="conn-1"),
            [
                {"uid": "new-uid-1", "iban": "NL01ABNA0123456789"},
                {"uid": "new-uid-2", "iban": "NL01ABNA0123456789"},
            ],
        )

        self.assertEqual(count, 1)
        self.assertEqual(SyncService._resolve_account_external_id(acc), "new-uid-1")

    def test_two_accounts_sharing_an_iban_are_both_repointed(self):
        """Multi-currency accounts share an IBAN. Leaving one on a dead uid fails the
        whole connection sync, because a per-account failure re-raises."""
        from app.routes.enable_banking import _repoint_account_uids
        from app.services.sync_service import SyncService

        eur = _account("eur", uid="old-eur", iban="NL01ABNA0123456789", currency="EUR")
        usd = _account("usd", uid="old-usd", iban="NL01ABNA0123456789", currency="USD")
        db = _db_with_linked_accounts([eur, usd])

        count = _repoint_account_uids(
            db,
            MagicMock(id="conn-1"),
            [
                {"uid": "new-usd", "iban": "NL01ABNA0123456789", "currency": "USD"},
                {"uid": "new-eur", "iban": "NL01ABNA0123456789", "currency": "EUR"},
            ],
        )

        self.assertEqual(count, 2)
        # Currency, not arrival order, decides which account gets which uid —
        # otherwise one currency's transactions land in the other's account.
        self.assertEqual(SyncService._resolve_account_external_id(usd), "new-usd")
        self.assertEqual(SyncService._resolve_account_external_id(eur), "new-eur")

    def test_ambiguous_shared_iban_is_left_unmapped(self):
        """No currency agrees and several accounts share the IBAN: guessing would file
        one currency's transactions under another's account."""
        from app.routes.enable_banking import _repoint_account_uids
        from app.services.sync_service import SyncService

        eur = _account("eur", uid="old-eur", iban="NL01ABNA0123456789", currency="EUR")
        usd = _account("usd", uid="old-usd", iban="NL01ABNA0123456789", currency="USD")
        db = _db_with_linked_accounts([eur, usd])

        count = _repoint_account_uids(
            db,
            MagicMock(id="conn-1"),
            [{"uid": "new-gbp", "iban": "NL01ABNA0123456789", "currency": "GBP"}],
        )

        self.assertEqual(count, 0)
        self.assertEqual(SyncService._resolve_account_external_id(eur), "old-eur")
        self.assertEqual(SyncService._resolve_account_external_id(usd), "old-usd")

    def test_lone_candidate_still_matches_on_a_currency_mismatch(self):
        """One account on the IBAN is unambiguous, so a currency disagreement (a
        never-recorded currency, say) must not block the re-point."""
        from app.routes.enable_banking import _repoint_account_uids
        from app.services.sync_service import SyncService

        acc = _account("only", uid="old-uid", iban="NL01ABNA0123456789", currency="EUR")
        db = _db_with_linked_accounts([acc])

        count = _repoint_account_uids(
            db,
            MagicMock(id="conn-1"),
            [{"uid": "new-uid", "iban": "NL01ABNA0123456789", "currency": "GBP"}],
        )

        self.assertEqual(count, 1)
        self.assertEqual(SyncService._resolve_account_external_id(acc), "new-uid")

    def test_scheme_form_iban_is_matched(self):
        """EB also returns the IBAN nested under account_id in scheme form."""
        from app.routes.enable_banking import _repoint_account_uids
        from app.services.sync_service import SyncService

        acc = _account("Giannis", uid="old-uid", iban="NL01ABNA0123456789")
        db = _db_with_linked_accounts([acc])

        count = _repoint_account_uids(
            db,
            MagicMock(id="conn-1"),
            [{
                "uid": "new-uid",
                "account_id": {"scheme_name": "IBAN", "identification": "NL01ABNA0123456789"},
            }],
        )

        self.assertEqual(count, 1)
        self.assertEqual(SyncService._resolve_account_external_id(acc), "new-uid")


class TestReconnectSession(unittest.TestCase):
    """POST /session renews the connection carried in the OAuth state."""

    def _patches(self, session_data, state_payload):
        redis_mock = MagicMock()
        redis_mock.get.return_value = json.dumps(state_payload)
        client_patch = patch("app.routes.enable_banking._get_eb_client")
        redis_patch = patch("app.routes.enable_banking._get_redis", return_value=redis_mock)
        client = client_patch.start()
        client.return_value.post.return_value.json.return_value = session_data
        redis_patch.start()
        self.addCleanup(client_patch.stop)
        self.addCleanup(redis_patch.stop)

    def _connection(self):
        return MagicMock(
            id="conn-1",
            aspsp_name="ABN AMRO",
            session_id="old-session",
            status="expired",
            last_sync_error="Consent expired. Please reconnect.",
        )

    def test_renews_in_place_without_creating_a_connection(self):
        from app.routes.enable_banking import create_session, SessionRequest
        from app.services.sync_service import SyncService

        conn = self._connection()
        acc = _account("Giannis", uid="old-uid", iban="NL01ABNA0123456789")
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = conn
        db.query.return_value.filter.return_value.all.return_value = [acc]

        self._patches(
            {
                "session_id": "new-session",
                "aspsp": {"name": "ABN AMRO", "country": "NL"},
                "accounts": [{"uid": "new-uid", "iban": "NL01ABNA0123456789"}],
            },
            {"user_id": "user-1", "connection_id": "conn-1"},
        )

        with patch("tasks.enable_banking_tasks.sync_bank_connection") as sync_task:
            result = create_session(
                SessionRequest(code="auth-code", state="nonce"), user_id="user-1", db=db
            )

        self.assertTrue(result.reconnected)
        self.assertEqual(result.connection_id, "conn-1")
        self.assertEqual(conn.session_id, "new-session")
        self.assertEqual(conn.status, "active")
        self.assertIsNone(conn.last_sync_error)
        db.add.assert_not_called()  # no second connection row
        sync_task.delay.assert_called_once_with("conn-1")
        # The renewal is worthless without this: the sync reads stored uids, so a
        # connection left holding the pre-consent uid asks for dead accounts.
        self.assertEqual(SyncService._resolve_account_external_id(acc), "new-uid")

    def test_authorizing_a_different_bank_is_rejected(self):
        """Otherwise the connection's accounts get re-pointed at another bank's uids."""
        from fastapi import HTTPException
        from app.routes.enable_banking import create_session, SessionRequest

        conn = self._connection()
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = conn

        self._patches(
            {
                "session_id": "new-session",
                "aspsp": {"name": "Revolut", "country": "LT"},
                "accounts": [],
            },
            {"user_id": "user-1", "connection_id": "conn-1"},
        )

        with self.assertRaises(HTTPException) as ctx:
            create_session(
                SessionRequest(code="auth-code", state="nonce"), user_id="user-1", db=db
            )

        self.assertEqual(ctx.exception.status_code, 400)
        self.assertEqual(conn.session_id, "old-session")
        db.commit.assert_not_called()

    def test_state_from_another_user_is_rejected(self):
        from fastapi import HTTPException
        from app.routes.enable_banking import create_session, SessionRequest

        db = MagicMock()
        self._patches(
            {"session_id": "new-session", "aspsp": {"name": "ABN AMRO"}, "accounts": []},
            {"user_id": "someone-else", "connection_id": "conn-1"},
        )

        with self.assertRaises(HTTPException) as ctx:
            create_session(
                SessionRequest(code="auth-code", state="nonce"), user_id="user-1", db=db
            )

        self.assertEqual(ctx.exception.status_code, 403)

    def test_plain_state_without_connection_creates_a_new_connection(self):
        """A first-time connect (and any pre-upgrade nonce) still lands on the wizard."""
        from app.routes.enable_banking import create_session, SessionRequest

        redis_mock = MagicMock()
        redis_mock.get.return_value = "user-1"  # nonce written before payloads were JSON
        db = MagicMock()

        with patch("app.routes.enable_banking._get_redis", return_value=redis_mock), \
             patch("app.routes.enable_banking._get_eb_client") as client:
            client.return_value.post.return_value.json.return_value = {
                "session_id": "new-session",
                "aspsp": {"name": "ABN AMRO", "country": "NL"},
                "accounts": [{"uid": "uid-1"}],
            }
            result = create_session(
                SessionRequest(code="auth-code", state="nonce"), user_id="user-1", db=db
            )

        self.assertFalse(result.reconnected)
        db.add.assert_called_once()


class TestUnreadableState(unittest.TestCase):
    """A state that cannot be read must not silently become a second connection."""

    def _patch_client(self, aspsp_name="ABN AMRO"):
        client_patch = patch("app.routes.enable_banking._get_eb_client")
        client = client_patch.start()
        client.return_value.post.return_value.json.return_value = {
            "session_id": "new-session",
            "aspsp": {"name": aspsp_name, "country": "NL"},
            "accounts": [{"uid": "uid-1"}],
        }
        self.addCleanup(client_patch.stop)

    def test_refuses_when_that_bank_is_already_connected(self):
        """Redis down mid-renewal would otherwise reopen the duplicate-account path."""
        from fastapi import HTTPException
        from app.routes.enable_banking import create_session, SessionRequest

        redis_mock = MagicMock()
        redis_mock.get.side_effect = Exception("redis down")
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = MagicMock(id="conn-1")
        self._patch_client()

        with patch("app.routes.enable_banking._get_redis", return_value=redis_mock):
            with self.assertRaises(HTTPException) as ctx:
                create_session(
                    SessionRequest(code="auth-code", state="nonce"), user_id="user-1", db=db
                )

        self.assertEqual(ctx.exception.status_code, 409)
        db.add.assert_not_called()

    def test_expired_nonce_is_treated_the_same_as_an_unreachable_redis(self):
        from fastapi import HTTPException
        from app.routes.enable_banking import create_session, SessionRequest

        redis_mock = MagicMock()
        redis_mock.get.return_value = None  # nonce outlived its TTL
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = MagicMock(id="conn-1")
        self._patch_client()

        with patch("app.routes.enable_banking._get_redis", return_value=redis_mock):
            with self.assertRaises(HTTPException) as ctx:
                create_session(
                    SessionRequest(code="auth-code", state="nonce"), user_id="user-1", db=db
                )

        self.assertEqual(ctx.exception.status_code, 409)

    def test_first_time_connect_to_a_new_bank_still_proceeds(self):
        """No existing connection means no ambiguity, so this must not regress."""
        from app.routes.enable_banking import create_session, SessionRequest

        redis_mock = MagicMock()
        redis_mock.get.side_effect = Exception("redis down")
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = None
        self._patch_client()

        with patch("app.routes.enable_banking._get_redis", return_value=redis_mock):
            result = create_session(
                SessionRequest(code="auth-code", state="nonce"), user_id="user-1", db=db
            )

        self.assertFalse(result.reconnected)
        db.add.assert_called_once()


class TestUnreadableStateAgainstTheDatabase(unittest.TestCase):
    """The bank-name match happens in SQL, so a mocked session cannot prove it."""

    def test_matches_a_stored_name_differing_by_case_and_padding(self):
        from fastapi import HTTPException
        from app.database import Base, SessionLocal, engine
        from app.db_helpers import get_or_create_system_user
        from app.models import BankConnection
        from app.routes.enable_banking import create_session, SessionRequest

        Base.metadata.create_all(bind=engine)
        db = SessionLocal()
        user_id = None
        try:
            user_id = str(get_or_create_system_user(db).id)
            db.add(BankConnection(
                user_id=user_id,
                provider="enable_banking",
                session_id="old-session",
                aspsp_name="  abn amro  ",  # as stored
                aspsp_country="NL",
                status="expired",
            ))
            db.commit()

            redis_mock = MagicMock()
            redis_mock.get.return_value = None  # nonce gone: intent unknown

            with patch("app.routes.enable_banking._get_redis", return_value=redis_mock), \
                 patch("app.routes.enable_banking._get_eb_client") as client:
                client.return_value.post.return_value.json.return_value = {
                    "session_id": "new-session",
                    "aspsp": {"name": "ABN AMRO", "country": "NL"},  # as returned now
                    "accounts": [{"uid": "uid-1"}],
                }
                with self.assertRaises(HTTPException) as ctx:
                    create_session(
                        SessionRequest(code="auth-code", state="nonce"),
                        user_id=user_id,
                        db=db,
                    )

            self.assertEqual(ctx.exception.status_code, 409)
            self.assertEqual(
                db.query(BankConnection).filter(BankConnection.user_id == user_id).count(),
                1,
                "the guard must not have opened a second connection",
            )
        finally:
            if user_id:
                db.query(BankConnection).filter(
                    BankConnection.user_id == user_id,
                ).delete()
                db.commit()
            db.close()


class TestReconnectAuth(unittest.TestCase):
    """POST /auth carries the connection to renew in the server-side state."""

    def test_state_stores_the_connection_id(self):
        from app.routes.enable_banking import initiate_auth, AuthRequest

        redis_mock = MagicMock()
        db = MagicMock()

        with patch("app.routes.enable_banking._get_redis", return_value=redis_mock), \
             patch("app.routes.enable_banking._get_eb_client") as client:
            client.return_value.redirect_uri = "https://app.example/callback"
            client.return_value.post.return_value.json.return_value = {"url": "https://bank/auth"}
            initiate_auth(
                AuthRequest(aspsp_name="ABN AMRO", aspsp_country="NL", connection_id="conn-1"),
                user_id="user-1",
                db=db,
            )

        stored = json.loads(redis_mock.setex.call_args[0][2])
        self.assertEqual(stored, {"user_id": "user-1", "connection_id": "conn-1"})
        # An expired nonce silently drops the renewal onto the first-time-connect
        # path, so the window has to outlast a 2FA detour into the bank's app.
        self.assertGreaterEqual(redis_mock.setex.call_args[0][1], 1800)

    def test_reconnect_fails_when_state_cannot_be_stored(self):
        """A lost state silently degrades a renewal into duplicate accounts."""
        from fastapi import HTTPException
        from app.routes.enable_banking import initiate_auth, AuthRequest

        redis_mock = MagicMock()
        redis_mock.setex.side_effect = Exception("redis down")
        db = MagicMock()

        with patch("app.routes.enable_banking._get_redis", return_value=redis_mock), \
             patch("app.routes.enable_banking._get_eb_client") as client:
            client.return_value.redirect_uri = "https://app.example/callback"
            with self.assertRaises(HTTPException) as ctx:
                initiate_auth(
                    AuthRequest(aspsp_name="ABN AMRO", aspsp_country="NL", connection_id="conn-1"),
                    user_id="user-1",
                    db=db,
                )

        self.assertEqual(ctx.exception.status_code, 503)

    def test_a_first_time_connect_survives_redis_being_down(self):
        from app.routes.enable_banking import initiate_auth, AuthRequest

        redis_mock = MagicMock()
        redis_mock.setex.side_effect = Exception("redis down")
        db = MagicMock()

        with patch("app.routes.enable_banking._get_redis", return_value=redis_mock), \
             patch("app.routes.enable_banking._get_eb_client") as client:
            client.return_value.redirect_uri = "https://app.example/callback"
            client.return_value.post.return_value.json.return_value = {"url": "https://bank/auth"}
            result = initiate_auth(
                AuthRequest(aspsp_name="ABN AMRO", aspsp_country="NL"),
                user_id="user-1",
                db=db,
            )

        self.assertEqual(result.url, "https://bank/auth")

    def test_reconnecting_a_foreign_connection_is_rejected(self):
        from fastapi import HTTPException
        from app.routes.enable_banking import initiate_auth, AuthRequest

        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = None

        with patch("app.routes.enable_banking._get_eb_client"):
            with self.assertRaises(HTTPException) as ctx:
                initiate_auth(
                    AuthRequest(aspsp_name="ABN AMRO", aspsp_country="NL", connection_id="conn-x"),
                    user_id="user-1",
                    db=db,
                )

        self.assertEqual(ctx.exception.status_code, 404)


if __name__ == "__main__":
    unittest.main()
