"""
Integration-style test for encrypted account external_id dedupe in SyncService.
"""
import base64
import os
import sys
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
from app.models import Account  # noqa: E402
from app.security.data_encryption import (  # noqa: E402
    decrypt_with_fallback,
    reset_encryption_config_cache,
)
from app.services.sync_service import SyncService  # noqa: E402


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


if __name__ == "__main__":
    success = test_account_sync_dedupes_on_encrypted_external_id()
    print("All encrypted account sync tests passed." if success else "Encrypted account sync tests failed.")
    sys.exit(0 if success else 1)
