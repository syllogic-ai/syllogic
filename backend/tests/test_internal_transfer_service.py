"""
Tests for InternalTransferService.

Run with:
    cd backend && pytest tests/test_internal_transfer_service.py -v
or:
    cd backend && python tests/test_internal_transfer_service.py
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
    """Make the encryption config deterministic before app modules are imported.

    Without this, ``blind_index()`` returns ``None`` whenever
    ``DATA_ENCRYPTION_KEY_CURRENT`` isn't set in the shell, which leaves the
    pocket's ``iban_hash`` and the source transaction's
    ``counterparty_iban_hash`` both NULL — and detection silently matches
    nothing. Set a deterministic test key here so the tests always exercise
    the encryption-enabled code path.
    """
    key = base64.urlsafe_b64encode(b"p" * 32).decode("utf-8").rstrip("=")
    os.environ["DATA_ENCRYPTION_KEY_CURRENT"] = key
    os.environ["DATA_ENCRYPTION_KEY_ID"] = "k-test-internal-transfer"
    os.environ.pop("DATA_ENCRYPTION_KEY_PREVIOUS", None)


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


# Refresh the lru_cache so the encryption config picks up our env vars.
reset_encryption_config_cache()


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------

POCKET_IBAN = "NL91ABNA0417164300"
UNRELATED_IBAN = "DE89370400440532013000"


def _ensure_schema() -> None:
    Base.metadata.create_all(bind=engine)


def _make_user(db) -> User:
    uid = f"itf-test-user-{uuid.uuid4().hex[:8]}"
    user = User(
        id=uid,
        email=f"{uid}@example.com",
        name="Internal Transfer Test User",
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


def _make_pocket_account(
    db, user_id: str, iban: str, name: str = "Savings Pocket"
) -> Account:
    acc = Account(
        user_id=user_id,
        name=name,
        account_type="savings",
        institution="Manual",
        currency="EUR",
        provider="manual",
        iban_hash=blind_index(iban),
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
    currency: str = "EUR",
) -> Transaction:
    tx = Transaction(
        user_id=user_id,
        account_id=account_id,
        external_id=f"src-{uuid.uuid4().hex[:12]}",
        amount=amount,
        currency=currency,
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
    # Delete in FK-safe order: transactions + internal_transfers must go before
    # accounts, but transactions.internal_transfer_id -> internal_transfers uses
    # ON DELETE SET NULL, and internal_transfers -> transactions uses CASCADE.
    # Null-out the back-reference first so we can freely delete.
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


# ---------------------------------------------------------------------------
# Test 1: detect creates mirror and marks source not in analytics
# ---------------------------------------------------------------------------

def test_detect_creates_mirror_and_marks_source_not_in_analytics() -> None:
    _ensure_schema()
    db = SessionLocal()
    user_id: Optional[str] = None
    try:
        from app.services.internal_transfer_service import InternalTransferService

        user = _make_user(db)
        user_id = user.id
        transfer_cat = _make_transfer_category(db, user_id)
        synced = _make_synced_account(db, user_id, name="Main Checking")
        pocket = _make_pocket_account(db, user_id, iban=POCKET_IBAN)
        src = _make_source_transaction(
            db,
            user_id,
            synced.id,
            counterparty_iban=POCKET_IBAN,
            amount=Decimal("-200.00"),
        )

        service = InternalTransferService(db, user_id=user_id)
        result = service.detect_for_transactions([src.id])
        assert result["detected"] == 1, f"Expected 1 detection, got {result}"
        assert result["pocket_account_ids"] == [pocket.id], (
            f"Expected pocket_account_ids=[{pocket.id}], got {result['pocket_account_ids']}"
        )

        db.refresh(src)
        assert src.include_in_analytics is False
        assert src.internal_transfer_id is not None

        link = (
            db.query(InternalTransfer)
            .filter(InternalTransfer.id == src.internal_transfer_id)
            .one()
        )
        assert link.source_txn_id == src.id
        assert link.source_account_id == synced.id
        assert link.pocket_account_id == pocket.id
        assert Decimal(str(link.amount)) == Decimal("200.00")
        assert link.currency == "EUR"

        mirror = (
            db.query(Transaction)
            .filter(Transaction.id == link.mirror_txn_id)
            .one()
        )
        assert mirror.account_id == pocket.id
        assert Decimal(str(mirror.amount)) == Decimal("200.00")
        assert mirror.currency == "EUR"
        assert mirror.include_in_analytics is False
        assert mirror.category_system_id == transfer_cat.id
        assert mirror.external_id == f"mirror-{src.id}"
        assert mirror.transaction_type == "credit"  # positive amount => credit
        print("  PASS: test_detect_creates_mirror_and_marks_source_not_in_analytics")
    finally:
        if user_id:
            _cleanup_user(db, user_id)
        db.close()


# ---------------------------------------------------------------------------
# Test 2: detect is idempotent
# ---------------------------------------------------------------------------

def test_detect_is_idempotent() -> None:
    _ensure_schema()
    db = SessionLocal()
    user_id: Optional[str] = None
    try:
        from app.services.internal_transfer_service import InternalTransferService

        user = _make_user(db)
        user_id = user.id
        _make_transfer_category(db, user_id)
        synced = _make_synced_account(db, user_id)
        _make_pocket_account(db, user_id, iban=POCKET_IBAN)
        src = _make_source_transaction(
            db,
            user_id,
            synced.id,
            counterparty_iban=POCKET_IBAN,
            amount=Decimal("-50.00"),
        )

        service = InternalTransferService(db, user_id=user_id)
        first = service.detect_for_transactions([src.id])
        second = service.detect_for_transactions([src.id])

        assert first["detected"] == 1
        assert second["detected"] == 0, "Second detection should be a no-op"
        assert second["pocket_account_ids"] == []

        mirrors = (
            db.query(Transaction)
            .filter(Transaction.external_id == f"mirror-{src.id}")
            .all()
        )
        assert len(mirrors) == 1, f"Expected exactly one mirror, got {len(mirrors)}"

        links = (
            db.query(InternalTransfer)
            .filter(InternalTransfer.source_txn_id == src.id)
            .all()
        )
        assert len(links) == 1, f"Expected exactly one internal_transfer row, got {len(links)}"
        print("  PASS: test_detect_is_idempotent")
    finally:
        if user_id:
            _cleanup_user(db, user_id)
        db.close()


# ---------------------------------------------------------------------------
# Test 3: detect skips when no matching pocket
# ---------------------------------------------------------------------------

def test_detect_skips_when_no_matching_pocket() -> None:
    _ensure_schema()
    db = SessionLocal()
    user_id: Optional[str] = None
    try:
        from app.services.internal_transfer_service import InternalTransferService

        user = _make_user(db)
        user_id = user.id
        _make_transfer_category(db, user_id)
        synced = _make_synced_account(db, user_id)
        # Pocket has a DIFFERENT IBAN
        _make_pocket_account(db, user_id, iban=POCKET_IBAN)
        src = _make_source_transaction(
            db,
            user_id,
            synced.id,
            counterparty_iban=UNRELATED_IBAN,  # no matching pocket
            amount=Decimal("-75.00"),
        )

        service = InternalTransferService(db, user_id=user_id)
        result = service.detect_for_transactions([src.id])

        assert result["detected"] == 0
        assert result["pocket_account_ids"] == []
        db.refresh(src)
        assert src.include_in_analytics is True
        assert src.internal_transfer_id is None

        links = db.query(InternalTransfer).filter(
            InternalTransfer.user_id == user_id
        ).count()
        mirrors = db.query(Transaction).filter(
            Transaction.external_id == f"mirror-{src.id}"
        ).count()
        assert links == 0
        assert mirrors == 0
        print("  PASS: test_detect_skips_when_no_matching_pocket")
    finally:
        if user_id:
            _cleanup_user(db, user_id)
        db.close()


# ---------------------------------------------------------------------------
# Test 4: unlink reverses detection
# ---------------------------------------------------------------------------

def test_unlink_reverses_detection() -> None:
    _ensure_schema()
    db = SessionLocal()
    user_id: Optional[str] = None
    try:
        from app.services.internal_transfer_service import InternalTransferService

        user = _make_user(db)
        user_id = user.id
        _make_transfer_category(db, user_id)
        synced = _make_synced_account(db, user_id)
        _make_pocket_account(db, user_id, iban=POCKET_IBAN)
        src = _make_source_transaction(
            db,
            user_id,
            synced.id,
            counterparty_iban=POCKET_IBAN,
            amount=Decimal("-120.00"),
        )

        service = InternalTransferService(db, user_id=user_id)
        assert service.detect_for_transactions([src.id])['detected'] == 1

        db.refresh(src)
        transfer_id = src.internal_transfer_id
        assert transfer_id is not None

        service.unlink(transfer_id)

        db.refresh(src)
        assert src.include_in_analytics is True
        assert src.internal_transfer_id is None

        mirrors = (
            db.query(Transaction)
            .filter(Transaction.external_id == f"mirror-{src.id}")
            .count()
        )
        assert mirrors == 0, "Mirror transaction should be deleted on unlink"

        links = (
            db.query(InternalTransfer)
            .filter(InternalTransfer.id == transfer_id)
            .count()
        )
        assert links == 0, "Internal transfer row should be deleted on unlink"
        print("  PASS: test_unlink_reverses_detection")
    finally:
        if user_id:
            _cleanup_user(db, user_id)
        db.close()


# ---------------------------------------------------------------------------
# Test 5: unlink_all_for_pocket restores sources
# ---------------------------------------------------------------------------

def test_unlink_all_for_pocket_restores_sources() -> None:
    _ensure_schema()
    db = SessionLocal()
    user_id: Optional[str] = None
    try:
        from app.services.internal_transfer_service import InternalTransferService

        user = _make_user(db)
        user_id = user.id
        _make_transfer_category(db, user_id)
        synced = _make_synced_account(db, user_id)
        pocket = _make_pocket_account(db, user_id, iban=POCKET_IBAN)

        src_a = _make_source_transaction(
            db,
            user_id,
            synced.id,
            counterparty_iban=POCKET_IBAN,
            amount=Decimal("-60.00"),
        )
        src_b = _make_source_transaction(
            db,
            user_id,
            synced.id,
            counterparty_iban=POCKET_IBAN,
            amount=Decimal("-25.00"),
        )

        service = InternalTransferService(db, user_id=user_id)
        assert service.detect_for_transactions([src_a.id, src_b.id])['detected'] == 2

        unlinked = service.unlink_all_for_pocket(pocket.id)
        assert unlinked == 2, f"Expected 2 unlinked, got {unlinked}"

        db.refresh(src_a)
        db.refresh(src_b)
        assert src_a.include_in_analytics is True
        assert src_a.internal_transfer_id is None
        assert src_b.include_in_analytics is True
        assert src_b.internal_transfer_id is None

        remaining_links = (
            db.query(InternalTransfer)
            .filter(InternalTransfer.pocket_account_id == pocket.id)
            .count()
        )
        assert remaining_links == 0
        # NOTE: mirrors are NOT expected to be deleted here — cascade handles them
        # when the pocket account itself is deleted. unlink_all_for_pocket's job
        # is to detach the sources.
        print("  PASS: test_unlink_all_for_pocket_restores_sources")
    finally:
        if user_id:
            _cleanup_user(db, user_id)
        db.close()


# ---------------------------------------------------------------------------
# Test 6: detection overwrites a stale LLM-assigned category_system_id
# (authoritative overwrite; preserves only user-set category_id)
# ---------------------------------------------------------------------------

def test_detect_overwrites_stale_system_category() -> None:
    _ensure_schema()
    db = SessionLocal()
    user_id: Optional[str] = None
    try:
        from app.services.internal_transfer_service import InternalTransferService

        user = _make_user(db)
        user_id = user.id
        transfer_cat = _make_transfer_category(db, user_id)

        # Seed an unrelated "Groceries" category that the LLM might have picked.
        stale_cat = Category(
            user_id=user_id,
            name="Groceries",
            category_type="expense",
            is_system=True,
        )
        db.add(stale_cat)
        db.commit()
        db.refresh(stale_cat)

        synced = _make_synced_account(db, user_id, name="Main Checking")
        pocket = _make_pocket_account(db, user_id, iban=POCKET_IBAN)
        src = _make_source_transaction(
            db,
            user_id,
            synced.id,
            counterparty_iban=POCKET_IBAN,
            amount=Decimal("-75.00"),
        )
        # Simulate a prior LLM run: a stale system category is already set,
        # and the user has NOT overridden (category_id is None).
        src.category_system_id = stale_cat.id
        db.commit()

        service = InternalTransferService(db, user_id=user_id)
        detected = service.detect_for_transactions([src.id])
        assert detected["detected"] == 1

        db.refresh(src)
        # Detection is authoritative — category_system_id flipped to Transfer.
        assert src.category_system_id == transfer_cat.id, (
            "Detection must overwrite a stale LLM system category with Transfer."
        )
        # User override untouched (still None).
        assert src.category_id is None
    finally:
        if user_id:
            _cleanup_user(db, user_id)
        db.close()


# ---------------------------------------------------------------------------
# Test 7: detection preserves user category override
# ---------------------------------------------------------------------------

def test_detect_preserves_user_category_override() -> None:
    _ensure_schema()
    db = SessionLocal()
    user_id: Optional[str] = None
    try:
        from app.services.internal_transfer_service import InternalTransferService

        user = _make_user(db)
        user_id = user.id
        transfer_cat = _make_transfer_category(db, user_id)

        user_cat = Category(
            user_id=user_id,
            name="My Custom",
            category_type="expense",
            is_system=False,
        )
        db.add(user_cat)
        db.commit()
        db.refresh(user_cat)

        synced = _make_synced_account(db, user_id, name="Main Checking")
        _ = _make_pocket_account(db, user_id, iban=POCKET_IBAN)
        src = _make_source_transaction(
            db,
            user_id,
            synced.id,
            counterparty_iban=POCKET_IBAN,
            amount=Decimal("-30.00"),
        )
        # User has explicitly chosen a category for this transaction.
        src.category_id = user_cat.id
        db.commit()

        service = InternalTransferService(db, user_id=user_id)
        assert service.detect_for_transactions([src.id])['detected'] == 1

        db.refresh(src)
        # Link was still created and analytics was flipped off,
        # but the user's category_id MUST be preserved.
        assert src.include_in_analytics is False
        assert src.internal_transfer_id is not None
        assert src.category_id == user_cat.id
        # category_system_id is NOT overwritten when category_id is set.
        # It may or may not be None depending on prior state — here we left it
        # None, so it should stay None.
        assert src.category_system_id is None
    finally:
        if user_id:
            _cleanup_user(db, user_id)
        db.close()


# ---------------------------------------------------------------------------
# Test 8: detection is strictly scoped to user — cross-user pockets never match
# (security invariant; relies on the user_id filter in _load_pocket_map)
# ---------------------------------------------------------------------------

def test_detect_does_not_match_cross_user_pocket() -> None:
    _ensure_schema()
    db = SessionLocal()
    user_a_id: Optional[str] = None
    user_b_id: Optional[str] = None
    try:
        from app.services.internal_transfer_service import InternalTransferService

        user_a = _make_user(db)
        user_a_id = user_a.id
        user_b = _make_user(db)
        user_b_id = user_b.id

        # User B owns a pocket with the IBAN.
        _make_transfer_category(db, user_b_id)
        _ = _make_pocket_account(db, user_b_id, iban=POCKET_IBAN)

        # User A has a transaction whose counterparty matches that IBAN.
        _make_transfer_category(db, user_a_id)
        synced_a = _make_synced_account(db, user_a_id, name="A's Checking")
        src_a = _make_source_transaction(
            db,
            user_a_id,
            synced_a.id,
            counterparty_iban=POCKET_IBAN,
            amount=Decimal("-40.00"),
        )

        service_a = InternalTransferService(db, user_id=user_a_id)
        assert service_a.detect_for_transactions([src_a.id])['detected'] == 0, (
            "User A's detection must not link to User B's pocket, "
            "even with a matching IBAN hash."
        )
        db.refresh(src_a)
        assert src_a.include_in_analytics is True
        assert src_a.internal_transfer_id is None
        assert db.query(InternalTransfer).filter_by(user_id=user_a_id).count() == 0
    finally:
        if user_a_id:
            _cleanup_user(db, user_a_id)
        if user_b_id:
            _cleanup_user(db, user_b_id)
        db.close()


if __name__ == "__main__":
    tests = [
        test_detect_creates_mirror_and_marks_source_not_in_analytics,
        test_detect_is_idempotent,
        test_detect_skips_when_no_matching_pocket,
        test_unlink_reverses_detection,
        test_unlink_all_for_pocket_restores_sources,
        test_detect_overwrites_stale_system_category,
        test_detect_preserves_user_category_override,
        test_detect_does_not_match_cross_user_pocket,
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
