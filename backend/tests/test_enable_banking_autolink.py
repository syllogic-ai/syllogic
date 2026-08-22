"""Auto-linking a bank account to the user's existing account during setup.

Enable Banking mints a new account uid on every authorization, so matching on
uid alone misses whenever a user reconnects. The wizard then offers only
"create new" and the same real account is added a second time. IBAN survives
re-consent, so it is the fallback identity key.
"""
import os
import sys
import unittest
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class AutoLinkTestCase(unittest.TestCase):
    """Real database: the matching runs in SQL over blind indexes."""

    def setUp(self):
        from app.database import Base, SessionLocal, engine
        from app.db_helpers import get_or_create_system_user

        Base.metadata.create_all(bind=engine)
        self.db = SessionLocal()
        self.user_id = str(get_or_create_system_user(self.db).id)
        # Unique per test: the system user is shared across the suite.
        self.iban = f"NL91ABNA{uuid.uuid4().hex[:10].upper()}"
        self.old_uid = f"uid-old-{uuid.uuid4().hex[:8]}"
        self.new_uid = f"uid-new-{uuid.uuid4().hex[:8]}"
        self.created_accounts = []
        self.created_connections = []

    def tearDown(self):
        from app.models import Account, BankConnection

        for account in self.created_accounts:
            self.db.query(Account).filter(Account.id == account).delete()
        for connection in self.created_connections:
            self.db.query(BankConnection).filter(BankConnection.id == connection).delete()
        self.db.commit()
        self.db.close()

    def _connection(self, status):
        from app.models import BankConnection

        conn = BankConnection(
            user_id=self.user_id,
            provider="enable_banking",
            session_id=f"sess-{uuid.uuid4().hex[:8]}",
            aspsp_name="ABN AMRO",
            aspsp_country="NL",
            status=status,
        )
        self.db.add(conn)
        self.db.commit()
        self.created_connections.append(conn.id)
        return conn

    def _account(self, connection=None):
        from app.models import Account
        from app.services.sync_service import SyncService

        acc = Account(
            user_id=self.user_id,
            name="ABN AMRO Giannis",
            account_type="checking",
            currency="EUR",
            provider="enable_banking",
            bank_connection_id=connection.id if connection else None,
        )
        SyncService._set_account_external_id_fields(acc, self.old_uid)
        SyncService._set_account_iban_fields(acc, self.iban)
        self.db.add(acc)
        self.db.commit()
        self.created_accounts.append(acc.id)
        return acc

    def _suggest(self):
        from app.routes.enable_banking import _build_suggested_mappings

        return _build_suggested_mappings(
            db=self.db,
            user_id=self.user_id,
            raw_accounts=[{
                "uid": self.new_uid,          # rotated by the new consent
                "iban": self.iban,            # survives re-consent
                "account_name": "Betaalrekening",
                "currency": "EUR",
            }],
        )[0]


class TestSuggestedMappings(AutoLinkTestCase):
    def test_rotated_uid_is_matched_by_iban(self):
        """The core case: reconnecting must recognize the account, not duplicate it."""
        account = self._account(self._connection("expired"))

        suggestion = self._suggest()

        self.assertEqual(suggestion["suggested_action"], "link")
        self.assertEqual(suggestion["suggested_account_id"], str(account.id))
        self.assertEqual(suggestion["suggested_account_name"], "ABN AMRO Giannis")

    def test_unlinked_account_is_matched_by_iban(self):
        """After a manual disconnect the account is unlinked but still the same account."""
        account = self._account(connection=None)

        suggestion = self._suggest()

        self.assertEqual(suggestion["suggested_action"], "link")
        self.assertEqual(suggestion["suggested_account_id"], str(account.id))

    def test_account_held_by_a_live_connection_is_not_suggested(self):
        """Re-linking it would silently break the connection that still works."""
        self._account(self._connection("active"))

        suggestion = self._suggest()

        self.assertEqual(suggestion["suggested_action"], "create")
        self.assertIsNone(suggestion["suggested_account_id"])

    def test_an_unrelated_iban_is_not_matched(self):
        """A genuinely new bank account must still be created, not linked to a stranger."""
        self._account(self._connection("expired"))
        from app.routes.enable_banking import _build_suggested_mappings

        suggestion = _build_suggested_mappings(
            db=self.db,
            user_id=self.user_id,
            raw_accounts=[{
                "uid": f"uid-other-{uuid.uuid4().hex[:8]}",
                "iban": f"NL91RABO{uuid.uuid4().hex[:10].upper()}",
                "account_name": "Spaarrekening",
            }],
        )[0]

        self.assertEqual(suggestion["suggested_action"], "create")

    def test_known_and_unknown_accounts_in_one_batch(self):
        """A consent usually returns a mix; each account is judged on its own."""
        account = self._account(self._connection("expired"))
        from app.routes.enable_banking import _build_suggested_mappings

        known, unknown = _build_suggested_mappings(
            db=self.db,
            user_id=self.user_id,
            raw_accounts=[
                {"uid": self.new_uid, "iban": self.iban, "account_name": "Betaalrekening"},
                {
                    "uid": f"uid-fresh-{uuid.uuid4().hex[:8]}",
                    "iban": f"NL91RABO{uuid.uuid4().hex[:10].upper()}",
                    "account_name": "New Current Account",
                },
            ],
        )

        self.assertEqual(known["suggested_action"], "link")
        self.assertEqual(known["suggested_account_id"], str(account.id))
        self.assertEqual(known["suggested_account_name"], "ABN AMRO Giannis")
        self.assertEqual(unknown["suggested_action"], "create")
        self.assertIsNone(unknown["suggested_account_id"])

    def test_unchanged_uid_still_matches(self):
        """Banks that keep uids stable must not depend on the IBAN leg."""
        account = self._account(self._connection("expired"))
        from app.routes.enable_banking import _build_suggested_mappings

        suggestion = _build_suggested_mappings(
            db=self.db,
            user_id=self.user_id,
            raw_accounts=[{"uid": self.old_uid, "account_name": "Betaalrekening"}],
        )[0]

        self.assertEqual(suggestion["suggested_action"], "link")
        self.assertEqual(suggestion["suggested_account_id"], str(account.id))


class TestMapAccountsLinkGuard(AutoLinkTestCase):
    """The suggestion is worthless if submitting it is rejected."""

    def _map(self, target_account, pending_connection):
        from app.routes.enable_banking import map_accounts, MapAccountsRequest, AccountMapping

        return map_accounts(
            connection_id=str(pending_connection.id),
            request=MapAccountsRequest(
                mappings=[AccountMapping(
                    bank_uid=self.new_uid,
                    action="link",
                    existing_account_id=str(target_account.id),
                )],
                initial_sync_days=90,
            ),
            db=self.db,
            user_id=self.user_id,
        )

    def _pending(self):
        conn = self._connection("pending_setup")
        conn.raw_session_data = {"accounts": [{"uid": self.new_uid, "iban": self.iban}]}
        self.db.commit()
        return conn

    def test_account_on_a_dead_consent_can_be_relinked(self):
        account = self._account(self._connection("expired"))
        pending = self._pending()

        result = self._map(account, pending)

        self.assertEqual(result.accounts_linked, 1)
        self.db.refresh(account)
        self.assertEqual(account.bank_connection_id, pending.id)

    def test_account_on_a_live_consent_is_refused(self):
        from fastapi import HTTPException

        live = self._connection("active")
        account = self._account(live)
        pending = self._pending()

        with self.assertRaises(HTTPException) as ctx:
            self._map(account, pending)

        self.assertEqual(ctx.exception.status_code, 400)
        self.db.rollback()
        self.db.refresh(account)
        self.assertEqual(
            account.bank_connection_id, live.id, "the working connection must keep its account"
        )


if __name__ == "__main__":
    unittest.main()
