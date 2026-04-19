"""Tests for POST /api/accounts/pocket — pocket account registration with backfill.

Run with:
    cd backend && .venv/bin/pytest tests/test_pocket_account_routes.py -v
"""
from __future__ import annotations

import base64
import os
import sys
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

# Ensure backend/ is importable
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _set_test_env() -> None:
    """Configure encryption and internal-auth secrets before importing app."""
    key = base64.urlsafe_b64encode(b"p" * 32).decode("utf-8").rstrip("=")
    os.environ["DATA_ENCRYPTION_KEY_CURRENT"] = key
    os.environ["DATA_ENCRYPTION_KEY_ID"] = "k-test-pocket"
    os.environ.pop("DATA_ENCRYPTION_KEY_PREVIOUS", None)
    os.environ.setdefault("INTERNAL_AUTH_SECRET", "test-internal-secret")


_set_test_env()

from app.database import Base, SessionLocal, engine  # noqa: E402
from app.models import (  # noqa: E402
    Account,
    Category,
    InternalTransfer,
    Transaction,
    User,
)
from app.security.data_encryption import (  # noqa: E402
    blind_index,
    reset_encryption_config_cache,
)
from tests.internal_auth import build_internal_auth_headers  # noqa: E402


# Refresh the lru_cache so the encryption config picks up our env vars.
reset_encryption_config_cache()


POCKET_IBAN = "NL91ABNA0417164300"


# ---------------------------------------------------------------------------
# Fixture helpers (mirror the style used in test_internal_transfer_service.py)
# ---------------------------------------------------------------------------


def _ensure_schema() -> None:
    Base.metadata.create_all(bind=engine)


def _make_user(db) -> User:
    uid = f"pocket-route-user-{uuid.uuid4().hex[:8]}"
    user = User(
        id=uid,
        email=f"{uid}@example.com",
        name="Pocket Route Test User",
        email_verified=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _make_synced_account(db, user_id: str, name: str = "Checking") -> Account:
    acc = Account(
        user_id=user_id,
        name=name,
        account_type="checking",
        institution="Test Bank",
        currency="EUR",
        provider="enable_banking",
        external_id=f"ext-{uuid.uuid4().hex[:12]}",
        is_active=True,
        starting_balance=Decimal("0"),
    )
    db.add(acc)
    db.commit()
    db.refresh(acc)
    return acc


def _make_transfer_category(db, user_id: str) -> Category:
    cat = Category(
        user_id=user_id,
        name="Transfer",
        category_type="transfer",
        is_system=True,
    )
    db.add(cat)
    db.commit()
    db.refresh(cat)
    return cat


def _make_source_transaction(
    db,
    user_id: str,
    account_id,
    counterparty_iban: Optional[str],
    amount: Decimal = Decimal("-150.00"),
) -> Transaction:
    tx = Transaction(
        user_id=user_id,
        account_id=account_id,
        external_id=f"src-{uuid.uuid4().hex[:12]}",
        amount=amount,
        currency="EUR",
        functional_amount=amount,
        description="Source transfer",
        merchant="Counterparty",
        booked_at=datetime(2026, 4, 15, tzinfo=timezone.utc),
        transaction_type="debit" if amount < 0 else "credit",
        counterparty_iban_hash=blind_index(counterparty_iban) if counterparty_iban else None,
        include_in_analytics=True,
    )
    db.add(tx)
    db.commit()
    db.refresh(tx)
    return tx


def _cleanup_user(db, user_id: str) -> None:
    """FK-safe cleanup identical to test_internal_transfer_service._cleanup_user."""
    db.query(Transaction).filter(Transaction.user_id == user_id).update(
        {Transaction.internal_transfer_id: None}, synchronize_session=False
    )
    db.query(InternalTransfer).filter(InternalTransfer.user_id == user_id).delete(
        synchronize_session=False
    )
    db.query(Transaction).filter(Transaction.user_id == user_id).delete(
        synchronize_session=False
    )
    db.query(Account).filter(Account.user_id == user_id).delete(
        synchronize_session=False
    )
    db.query(Category).filter(Category.user_id == user_id).delete(
        synchronize_session=False
    )
    db.query(User).filter(User.id == user_id).delete(synchronize_session=False)
    db.commit()


def _client():
    """Return a fresh TestClient, importing main lazily so env vars are set first."""
    from fastapi.testclient import TestClient
    from app.main import app

    return TestClient(app)


def _signed_post(client, user_id: str, path: str, body: dict):
    """POST to an internal-auth-protected endpoint with properly signed headers."""
    headers = build_internal_auth_headers("POST", path, user_id)
    return client.post(path, headers=headers, json=body)


def _signed_delete(client, user_id: str, path: str):
    """DELETE to an internal-auth-protected endpoint with properly signed headers."""
    headers = build_internal_auth_headers("DELETE", path, user_id)
    return client.delete(path, headers=headers)


# ---------------------------------------------------------------------------
# Test 1: happy path — encrypts IBAN, creates pocket, backfills existing txns
# ---------------------------------------------------------------------------


def test_create_pocket_account_encrypts_iban_and_backfills() -> None:
    _ensure_schema()
    db = SessionLocal()
    user_id: Optional[str] = None
    try:
        user = _make_user(db)
        user_id = user.id
        _make_transfer_category(db, user_id)
        synced = _make_synced_account(db, user_id, name="Main Checking")
        src_tx = _make_source_transaction(
            db,
            user_id,
            synced.id,
            counterparty_iban=POCKET_IBAN,
            amount=Decimal("-200.00"),
        )

        client = _client()
        path = "/api/accounts/pocket"
        body = {
            "name": "My Pocket",
            "account_type": "savings",
            "currency": "EUR",
            "starting_balance": "0",
            "iban": POCKET_IBAN,
        }
        response = _signed_post(client, user_id, path, body)

        assert response.status_code == 200, (
            f"Expected 200, got {response.status_code}: {response.text}"
        )
        payload = response.json()
        assert "account_id" in payload
        assert payload["backfilled_count"] == 1, (
            f"Expected 1 backfilled transaction, got {payload.get('backfilled_count')}"
        )

        # New account row has encrypted IBAN + hash + manual provider
        account = (
            db.query(Account)
            .filter(Account.id == payload["account_id"])
            .one()
        )
        assert account.user_id == user_id
        assert account.provider == "manual"
        assert account.iban_hash == blind_index(POCKET_IBAN)
        assert account.iban_ciphertext is not None
        assert account.iban_ciphertext.startswith("enc:v1:"), (
            f"Expected enc:v1: envelope, got {account.iban_ciphertext[:20]!r}"
        )

        # Pre-existing transaction is now linked + excluded from analytics
        db.expire_all()
        refreshed = db.query(Transaction).filter(Transaction.id == src_tx.id).one()
        assert refreshed.include_in_analytics is False
        assert refreshed.internal_transfer_id is not None

        # Exactly one InternalTransfer row for this user
        links = (
            db.query(InternalTransfer)
            .filter(InternalTransfer.user_id == user_id)
            .all()
        )
        assert len(links) == 1
        assert links[0].pocket_account_id == account.id
        assert links[0].source_txn_id == src_tx.id
    finally:
        if user_id:
            _cleanup_user(db, user_id)
        db.close()


# ---------------------------------------------------------------------------
# Test 2: duplicate IBAN for the same user => 400
# ---------------------------------------------------------------------------


def test_create_pocket_account_rejects_duplicate_iban() -> None:
    _ensure_schema()
    db = SessionLocal()
    user_id: Optional[str] = None
    try:
        user = _make_user(db)
        user_id = user.id

        # Seed an existing manual account with the same iban_hash
        existing = Account(
            user_id=user_id,
            name="Existing Pocket",
            account_type="savings",
            currency="EUR",
            provider="manual",
            iban_hash=blind_index(POCKET_IBAN),
            is_active=True,
            starting_balance=Decimal("0"),
        )
        db.add(existing)
        db.commit()

        client = _client()
        path = "/api/accounts/pocket"
        body = {
            "name": "Another Pocket",
            "account_type": "savings",
            "currency": "EUR",
            "starting_balance": "0",
            "iban": POCKET_IBAN,
        }
        response = _signed_post(client, user_id, path, body)

        assert response.status_code == 400, (
            f"Expected 400 on duplicate IBAN, got {response.status_code}: {response.text}"
        )
        detail = response.json().get("detail", "")
        assert "already" in detail.lower(), (
            f"Expected 'already' in error detail, got: {detail!r}"
        )
    finally:
        if user_id:
            _cleanup_user(db, user_id)
        db.close()


# ---------------------------------------------------------------------------
# Test 3: duplicate scope is manual-only — synced accounts with the same
# hash do NOT collide. (Defense in depth: synced accounts don't populate
# iban_hash today, but the scoping check should still enforce it.)
# ---------------------------------------------------------------------------


def test_create_pocket_account_duplicate_check_ignores_non_manual_providers() -> None:
    _ensure_schema()
    db = SessionLocal()
    user_id: Optional[str] = None
    try:
        user = _make_user(db)
        user_id = user.id

        # Seed a non-manual account sharing the same iban_hash — must NOT
        # block the pocket registration.
        synced_sharing_hash = Account(
            user_id=user_id,
            name="Synced ABN Account",
            account_type="checking",
            currency="EUR",
            provider="enable_banking",
            external_id=f"ext-{uuid.uuid4().hex[:12]}",
            iban_hash=blind_index(POCKET_IBAN),
            is_active=True,
            starting_balance=Decimal("0"),
        )
        db.add(synced_sharing_hash)
        db.commit()

        client = _client()
        path = "/api/accounts/pocket"
        body = {
            "name": "Pocket With Same IBAN",
            "account_type": "savings",
            "currency": "EUR",
            "starting_balance": "0",
            "iban": POCKET_IBAN,
        }
        response = _signed_post(client, user_id, path, body)

        assert response.status_code == 200, (
            f"Expected 200 (synced account with same hash must not block), "
            f"got {response.status_code}: {response.text}"
        )
    finally:
        if user_id:
            _cleanup_user(db, user_id)
        db.close()


# ---------------------------------------------------------------------------
# Test 4: malformed IBAN => validation failure (400 or 422)
# ---------------------------------------------------------------------------


def test_create_pocket_account_rejects_invalid_iban() -> None:
    _ensure_schema()
    db = SessionLocal()
    user_id: Optional[str] = None
    try:
        user = _make_user(db)
        user_id = user.id

        client = _client()
        path = "/api/accounts/pocket"
        body = {
            "name": "Bad IBAN Pocket",
            "account_type": "savings",
            "currency": "EUR",
            "starting_balance": "0",
            "iban": "not-an-iban",
        }
        response = _signed_post(client, user_id, path, body)

        # Pydantic validator raises ValueError => FastAPI returns 422 by default.
        # Accept either 400 (explicit check) or 422 (pydantic validation).
        assert response.status_code in (400, 422), (
            f"Expected 400 or 422, got {response.status_code}: {response.text}"
        )
    finally:
        if user_id:
            _cleanup_user(db, user_id)
        db.close()


# ---------------------------------------------------------------------------
# Task 9: DELETE /api/accounts/internal-transfers/{transfer_id}
# ---------------------------------------------------------------------------


def _make_pocket_account(db, user_id: str, iban: str) -> Account:
    """Create a manual pocket account with encrypted IBAN + hash."""
    from app.security.data_encryption import encrypt_value

    acc = Account(
        user_id=user_id,
        name="Pocket",
        account_type="savings",
        currency="EUR",
        provider="manual",
        iban_ciphertext=encrypt_value(iban),
        iban_hash=blind_index(iban),
        is_active=True,
        starting_balance=Decimal("0"),
    )
    db.add(acc)
    db.commit()
    db.refresh(acc)
    return acc


def test_unlink_internal_transfer_restores_source() -> None:
    _ensure_schema()
    db = SessionLocal()
    user_id: Optional[str] = None
    try:
        from app.services.internal_transfer_service import InternalTransferService

        user = _make_user(db)
        user_id = user.id
        _make_transfer_category(db, user_id)
        synced = _make_synced_account(db, user_id, name="Main")
        pocket = _make_pocket_account(db, user_id, iban=POCKET_IBAN)
        src = _make_source_transaction(
            db, user_id, synced.id, counterparty_iban=POCKET_IBAN,
            amount=Decimal("-9.00"),
        )
        # Trigger detection so there's a link to unlink
        assert (
            InternalTransferService(db, user_id=user_id)
            .detect_for_transactions([src.id])["detected"]
            == 1
        )
        link = db.query(InternalTransfer).filter_by(user_id=user_id).one()

        client = _client()
        path = f"/api/accounts/internal-transfers/{link.id}"
        response = _signed_delete(client, user_id, path)
        assert response.status_code == 204, f"Expected 204, got {response.status_code}: {response.text}"

        db.refresh(src)
        assert src.include_in_analytics is True
        assert src.internal_transfer_id is None
        # Link is gone
        assert db.query(InternalTransfer).filter_by(id=link.id).first() is None
        # Mirror transaction was deleted too
        assert db.query(Transaction).filter_by(account_id=pocket.id).count() == 0
    finally:
        if user_id:
            _cleanup_user(db, user_id)
        db.close()


# ---------------------------------------------------------------------------
# Task 10: DELETE /api/accounts/{account_id} with pre-delete cleanup
# ---------------------------------------------------------------------------


def test_delete_pocket_account_restores_linked_sources() -> None:
    _ensure_schema()
    db = SessionLocal()
    user_id: Optional[str] = None
    try:
        from app.services.internal_transfer_service import InternalTransferService

        user = _make_user(db)
        user_id = user.id
        _make_transfer_category(db, user_id)
        synced = _make_synced_account(db, user_id, name="Main")
        pocket = _make_pocket_account(db, user_id, iban=POCKET_IBAN)
        src = _make_source_transaction(
            db, user_id, synced.id, counterparty_iban=POCKET_IBAN,
            amount=Decimal("-4.00"),
        )
        InternalTransferService(db, user_id=user_id).detect_for_transactions([src.id])
        pocket_id = pocket.id
        assert db.query(InternalTransfer).filter_by(pocket_account_id=pocket_id).count() == 1

        client = _client()
        path = f"/api/accounts/{pocket_id}"
        response = _signed_delete(client, user_id, path)
        assert response.status_code == 204, f"Expected 204, got {response.status_code}: {response.text}"

        # Pocket gone
        assert db.query(Account).filter_by(id=pocket_id).count() == 0
        # Source restored
        db.refresh(src)
        assert src.include_in_analytics is True
        assert src.internal_transfer_id is None
        # Links gone
        assert db.query(InternalTransfer).filter_by(user_id=user_id).count() == 0
    finally:
        if user_id:
            _cleanup_user(db, user_id)
        db.close()


def test_delete_pocket_account_returns_404_for_other_user() -> None:
    _ensure_schema()
    db = SessionLocal()
    user_a_id: Optional[str] = None
    user_b_id: Optional[str] = None
    try:
        from app.services.internal_transfer_service import InternalTransferService

        user_a = _make_user(db)
        user_b = _make_user(db)
        user_a_id = user_a.id
        user_b_id = user_b.id

        # User B has a pocket with a detected internal transfer — we want to
        # prove that a cross-user delete attempt CANNOT trigger any mutation
        # of B's data (ownership check must short-circuit before the service
        # call).
        _make_transfer_category(db, user_b_id)
        b_synced = _make_synced_account(db, user_b_id, name="B's Main")
        b_pocket = _make_pocket_account(db, user_b_id, iban=POCKET_IBAN)
        b_src = _make_source_transaction(
            db, user_b_id, b_synced.id,
            counterparty_iban=POCKET_IBAN, amount=Decimal("-50.00"),
        )
        assert (
            InternalTransferService(db, user_id=user_b_id)
            .detect_for_transactions([b_src.id])["detected"]
            == 1
        )
        b_link_count_before = db.query(InternalTransfer).filter_by(user_id=user_b_id).count()
        assert b_link_count_before == 1

        client = _client()
        path = f"/api/accounts/{b_pocket.id}"
        response = _signed_delete(client, user_a_id, path)
        assert response.status_code == 404, (
            f"Expected 404, got {response.status_code}: {response.text}"
        )

        # Account still exists (owned by user B)
        assert db.query(Account).filter_by(id=b_pocket.id).count() == 1
        # B's link was NOT torn down by the cross-user attempt
        assert (
            db.query(InternalTransfer).filter_by(user_id=user_b_id).count()
            == b_link_count_before
        )
        # B's source transaction is still in its detected state
        db.refresh(b_src)
        assert b_src.include_in_analytics is False
        assert b_src.internal_transfer_id is not None
    finally:
        if user_a_id:
            _cleanup_user(db, user_a_id)
        if user_b_id:
            _cleanup_user(db, user_b_id)
        db.close()


if __name__ == "__main__":
    tests = [
        test_create_pocket_account_encrypts_iban_and_backfills,
        test_create_pocket_account_rejects_duplicate_iban,
        test_create_pocket_account_duplicate_check_ignores_non_manual_providers,
        test_create_pocket_account_rejects_invalid_iban,
        test_unlink_internal_transfer_restores_source,
        test_delete_pocket_account_restores_linked_sources,
        test_delete_pocket_account_returns_404_for_other_user,
    ]
    results = []
    for fn in tests:
        try:
            fn()
            results.append((fn.__name__, True, None))
        except Exception:
            import traceback
            results.append((fn.__name__, False, traceback.format_exc()))

    print("\n--- Results ---")
    all_passed = True
    for name, passed, err in results:
        print(f"  [{'PASS' if passed else 'FAIL'}] {name}")
        if err:
            print(err)
            all_passed = False

    sys.exit(0 if all_passed else 1)
