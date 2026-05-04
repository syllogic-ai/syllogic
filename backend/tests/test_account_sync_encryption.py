"""
Integration-style test for encrypted account external_id dedupe in SyncService.
"""
import base64
import os
import sys
import uuid
from decimal import Decimal
from typing import Optional
from datetime import datetime

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import Base, SessionLocal, engine  # noqa: E402
from app.db_helpers import (  # noqa: E402
    clear_request_user_id,
    get_or_create_system_user,
    set_request_user_id,
)
from app.integrations.base import AccountData, BankAdapter, TransactionData  # noqa: E402
from app.models import Account, User  # noqa: E402
from app.security.data_encryption import (  # noqa: E402
    decrypt_with_fallback,
    reset_encryption_config_cache,
)
from app.services.sync_service import SyncService  # noqa: E402


def _make_user(db) -> User:
    uid = f"sync-iban-test-user-{uuid.uuid4().hex[:8]}"
    user = User(
        id=uid,
        email=f"{uid}@example.com",
        name="Sync IBAN Test User",
        email_verified=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _set_encryption_env() -> None:
    key = base64.urlsafe_b64encode(b"a" * 32).decode("utf-8").rstrip("=")
    os.environ["DATA_ENCRYPTION_KEY_CURRENT"] = key
    os.environ["DATA_ENCRYPTION_KEY_ID"] = "k-test"
    if "DATA_ENCRYPTION_KEY_PREVIOUS" in os.environ:
        del os.environ["DATA_ENCRYPTION_KEY_PREVIOUS"]
    reset_encryption_config_cache()


class _Adapter(BankAdapter):
    def fetch_accounts(self) -> list[AccountData]:
        return [
            AccountData(
                external_id="provider-account-123",
                name="Encrypted Account",
                account_type="checking",
                institution="Test Institution",
                currency="EUR",
                balance_available=Decimal("123.45"),
            )
        ]

    def fetch_transactions(
        self,
        account_external_id: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> list[TransactionData]:
        return []

    def normalize_transaction(self, raw: dict) -> TransactionData:
        raise NotImplementedError


def test_account_sync_dedupes_on_encrypted_external_id() -> bool:
    _set_encryption_env()
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    user_id: Optional[str] = None
    try:
        user = get_or_create_system_user(db)
        user_id = str(user.id)

        db.query(Account).filter(
            Account.user_id == user_id,
            Account.provider == "adapter-test",
        ).delete()
        db.commit()

        token = set_request_user_id(user_id)
        service = SyncService(db, user_id=user_id)
        adapter = _Adapter()

        try:
            service.sync_accounts(adapter, provider="adapter-test")
            service.sync_accounts(adapter, provider="adapter-test")
        finally:
            clear_request_user_id(token)

        rows = (
            db.query(Account)
            .filter(Account.user_id == user_id, Account.provider == "adapter-test")
            .all()
        )

        assert len(rows) == 1, "Expected exactly one synced account after duplicate sync."
        row = rows[0]
        assert row.external_id == "provider-account-123", "Dual-write should keep plaintext during validation window."
        assert row.external_id_ciphertext, "Ciphertext should be populated."
        assert row.external_id_hash, "Blind index hash should be populated."
        assert (
            decrypt_with_fallback(row.external_id_ciphertext, row.external_id) == "provider-account-123"
        ), "Decrypted external_id should match original value."

        print("✓ encrypted account dedupe sync")
        return True
    finally:
        if user_id:
            db.query(Account).filter(
                Account.user_id == user_id,
                Account.provider == "adapter-test",
            ).delete()
            db.commit()
        db.close()


class _IBANAdapter(BankAdapter):
    """Minimal adapter that returns a single transaction with a counterparty IBAN."""

    def __init__(self, account_external_id: str, iban: Optional[str] = "NL91ABNA0417164300") -> None:
        self._account_external_id = account_external_id
        self._iban = iban

    def fetch_accounts(self) -> list[AccountData]:
        return [
            AccountData(
                external_id=self._account_external_id,
                name="IBAN Test Account",
                account_type="checking",
                institution="Test Bank",
                currency="EUR",
                balance_available=Decimal("0.00"),
            )
        ]

    def fetch_transactions(
        self,
        account_external_id: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> list[TransactionData]:
        from datetime import timezone
        return [
            TransactionData(
                external_id="ext-iban-1",
                account_external_id=account_external_id,
                amount=Decimal("-10.00"),
                currency="EUR",
                description="IBAN test transaction",
                counterparty_iban=self._iban,
                booked_at=datetime(2026, 4, 1, tzinfo=timezone.utc),
                transaction_type="debit",
            )
        ]

    def normalize_transaction(self, raw: dict) -> TransactionData:
        raise NotImplementedError


def test_sync_service_persists_encrypted_counterparty_iban() -> bool:
    _set_encryption_env()
    Base.metadata.create_all(bind=engine)

    from app.models import Transaction
    from app.security.data_encryption import decrypt_value, blind_index

    db = SessionLocal()
    user_id: Optional[str] = None
    try:
        user = get_or_create_system_user(db)
        user_id = str(user.id)

        # Clean up any leftover rows from prior runs
        provider = "iban-enc-test"
        existing_accounts = db.query(Account).filter(
            Account.user_id == user_id,
            Account.provider == provider,
        ).all()
        for acc in existing_accounts:
            db.query(Transaction).filter(Transaction.account_id == acc.id).delete()
        db.query(Account).filter(
            Account.user_id == user_id,
            Account.provider == provider,
        ).delete()
        db.commit()

        token = set_request_user_id(user_id)
        service = SyncService(db, user_id=user_id, use_llm_categorization=False)
        adapter = _IBANAdapter(account_external_id="iban-test-acct-001")

        try:
            service.sync_all(adapter, provider=provider)
        finally:
            clear_request_user_id(token)

        row = db.query(Transaction).join(Account).filter(
            Account.user_id == user_id,
            Account.provider == provider,
            Transaction.external_id == "ext-iban-1",
        ).first()

        assert row is not None, "Transaction row should have been created."
        assert row.counterparty_iban_ciphertext is not None, (
            f"counterparty_iban_ciphertext should not be None, got: {row.counterparty_iban_ciphertext!r}"
        )
        assert row.counterparty_iban_ciphertext.startswith("enc:v1:"), (
            f"Unexpected ciphertext format: {row.counterparty_iban_ciphertext!r}"
        )
        assert decrypt_value(row.counterparty_iban_ciphertext) == "NL91ABNA0417164300", (
            "Decrypted IBAN should match the original value."
        )
        assert row.counterparty_iban_hash == blind_index("NL91ABNA0417164300"), (
            "Blind index should match expected HMAC."
        )

        print("✓ sync service persists encrypted counterparty IBAN + blind index")
        return True
    finally:
        if user_id:
            provider = "iban-enc-test"
            existing_accounts = db.query(Account).filter(
                Account.user_id == user_id,
                Account.provider == provider,
            ).all()
            for acc in existing_accounts:
                db.query(Transaction).filter(Transaction.account_id == acc.id).delete()
            db.query(Account).filter(
                Account.user_id == user_id,
                Account.provider == provider,
            ).delete()
            db.commit()
        db.close()
        reset_encryption_config_cache()


def _cleanup_user(db, user_id: str) -> None:
    """Best-effort cleanup of a synthetic test user and its accounts."""
    try:
        from app.models import Transaction
        accs = db.query(Account).filter(Account.user_id == user_id).all()
        for acc in accs:
            db.query(Transaction).filter(Transaction.account_id == acc.id).delete()
        db.query(Account).filter(Account.user_id == user_id).delete()
        db.query(User).filter(User.id == user_id).delete()
        db.commit()
    except Exception:
        db.rollback()


def test_sync_service_persists_iban_on_synced_account_first_sync() -> bool:
    """When AccountData.iban is set on a fresh sync, the synced account row is
    persisted with iban_ciphertext (enc:v1: envelope) + iban_hash (blind index)."""
    _set_encryption_env()
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    user_id: Optional[str] = None
    try:
        from app.security.data_encryption import blind_index, decrypt_value

        user = _make_user(db)
        user_id = str(user.id)
        service = SyncService(db, user_id=user_id, use_llm_categorization=False)

        from unittest.mock import MagicMock
        adapter = MagicMock()
        adapter.fetch_accounts.return_value = [
            AccountData(
                external_id="ext-iban-1",
                name="ABN Checking",
                account_type="checking",
                institution="ABN AMRO",
                currency="EUR",
                iban="NL91ABNA0417164300",
            ),
        ]

        service.sync_accounts(adapter, provider="enable_banking")
        db.commit()

        row = db.query(Account).filter_by(user_id=user_id, external_id="ext-iban-1").one()
        assert row.iban_ciphertext is not None
        assert row.iban_ciphertext.startswith("enc:v1:")
        assert decrypt_value(row.iban_ciphertext) == "NL91ABNA0417164300"
        assert row.iban_hash == blind_index("NL91ABNA0417164300")

        print("✓ sync service persists iban on first sync")
        return True
    finally:
        if user_id:
            _cleanup_user(db, user_id)
        db.close()
        reset_encryption_config_cache()


def test_sync_service_does_not_overwrite_existing_iban() -> bool:
    """If iban_hash is already set on the account, sync must NOT overwrite it."""
    _set_encryption_env()
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    user_id: Optional[str] = None
    try:
        from app.security.data_encryption import encrypt_value, blind_index

        user = _make_user(db)
        user_id = str(user.id)

        # Pre-create an account with a different IBAN already set.
        original_iban = "NL01PRESET0000000000"
        existing = Account(
            user_id=user_id,
            name="ABN Checking",
            account_type="checking",
            institution="ABN AMRO",
            currency="EUR",
            provider="enable_banking",
            external_id="ext-iban-2",
            iban_ciphertext=encrypt_value(original_iban),
            iban_hash=blind_index(original_iban),
            starting_balance=Decimal("0"),
            is_active=True,
        )
        db.add(existing)
        db.commit()

        service = SyncService(db, user_id=user_id, use_llm_categorization=False)
        from unittest.mock import MagicMock
        adapter = MagicMock()
        adapter.fetch_accounts.return_value = [
            AccountData(
                external_id="ext-iban-2",
                name="ABN Checking",
                account_type="checking",
                institution="ABN AMRO",
                currency="EUR",
                iban="NL99DIFFERENT0000000",  # different IBAN — must be ignored
            ),
        ]

        service.sync_accounts(adapter, provider="enable_banking")
        db.commit()

        db.refresh(existing)
        assert existing.iban_hash == blind_index(original_iban), (
            "iban_hash must NOT be overwritten when already set"
        )

        print("✓ sync service preserves existing iban_hash")
        return True
    finally:
        if user_id:
            _cleanup_user(db, user_id)
        db.close()
        reset_encryption_config_cache()


def test_sync_service_skips_iban_when_account_data_iban_is_none() -> bool:
    """Accounts without an IBAN (some credit cards) must not trigger encryption."""
    _set_encryption_env()
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    user_id: Optional[str] = None
    try:
        user = _make_user(db)
        user_id = str(user.id)
        service = SyncService(db, user_id=user_id, use_llm_categorization=False)
        from unittest.mock import MagicMock
        adapter = MagicMock()
        adapter.fetch_accounts.return_value = [
            AccountData(
                external_id="ext-noiban",
                name="Credit Card",
                account_type="credit",
                institution="ABN AMRO",
                currency="EUR",
                iban=None,
            ),
        ]
        service.sync_accounts(adapter, provider="enable_banking")
        db.commit()

        row = db.query(Account).filter_by(user_id=user_id, external_id="ext-noiban").one()
        assert row.iban_ciphertext is None
        assert row.iban_hash is None

        print("✓ sync service skips iban encryption when iban is None")
        return True
    finally:
        if user_id:
            _cleanup_user(db, user_id)
        db.close()
        reset_encryption_config_cache()


if __name__ == "__main__":
    success = test_account_sync_dedupes_on_encrypted_external_id()
    success2 = test_sync_service_persists_encrypted_counterparty_iban()
    success3 = test_sync_service_persists_iban_on_synced_account_first_sync()
    success4 = test_sync_service_does_not_overwrite_existing_iban()
    success5 = test_sync_service_skips_iban_when_account_data_iban_is_none()
    all_passed = success and success2 and success3 and success4 and success5
    print("All encrypted account sync tests passed." if all_passed else "Encrypted account sync tests failed.")
    sys.exit(0 if all_passed else 1)
