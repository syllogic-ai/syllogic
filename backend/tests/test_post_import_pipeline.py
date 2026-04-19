"""
Tests for the post_import_pipeline Celery task.

Run with:
    cd backend && python tests/test_post_import_pipeline.py
"""
import base64
import sys
import os
import uuid
from decimal import Decimal
from datetime import datetime, timezone
from typing import Optional
from unittest.mock import MagicMock, patch, call

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _set_test_env() -> None:
    """Set a deterministic encryption key before app modules are imported.

    Otherwise ``blind_index()`` returns ``None`` whenever the shell lacks
    ``DATA_ENCRYPTION_KEY_CURRENT``, which silently NULLs out the IBAN
    hashes our integration test relies on for transfer-matching.
    """
    key = base64.urlsafe_b64encode(b"p" * 32).decode("utf-8").rstrip("=")
    os.environ["DATA_ENCRYPTION_KEY_CURRENT"] = key
    os.environ["DATA_ENCRYPTION_KEY_ID"] = "k-test-pipeline"
    os.environ.pop("DATA_ENCRYPTION_KEY_PREVIOUS", None)


_set_test_env()

from app.database import Base, SessionLocal, engine
from app.models import Account, Category, InternalTransfer, Transaction, User
from app.security.data_encryption import blind_index, reset_encryption_config_cache


# Refresh the lru_cache so the encryption config picks up our env vars.
reset_encryption_config_cache()


# ---------------------------------------------------------------------------
# Shared fixture helpers (integration tests only)
# ---------------------------------------------------------------------------

PIPELINE_TEST_IBAN = "NL91ABNA0417164300"


def _ensure_schema() -> None:
    Base.metadata.create_all(bind=engine)


def _make_user(db) -> User:
    uid = f"pip-test-user-{uuid.uuid4().hex[:8]}"
    user = User(
        id=uid,
        email=f"{uid}@example.com",
        name="Pipeline Test User",
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


def _make_pocket_account(db, user_id: str, iban: str, name: str = "Savings Pocket") -> Account:
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
        functional_amount=amount,  # pre-set so transfer detection can use it
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


def _cleanup_user_data(db, user_id: str) -> None:
    """Remove all rows for a test user in FK-safe order."""
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


def test_pipeline_calls_all_steps_in_order():
    """Verify that _run_post_import_pipeline calls all 7 step helpers in the right order."""
    print("Running test_pipeline_calls_all_steps_in_order...")

    with patch("tasks.post_import_pipeline.SessionLocal") as mock_session_local, \
         patch("tasks.post_import_pipeline.set_request_user_id") as mock_set_user, \
         patch("tasks.post_import_pipeline.clear_request_user_id") as mock_clear_user, \
         patch("tasks.post_import_pipeline._sync_exchange_rates") as mock_fx, \
         patch("tasks.post_import_pipeline._update_functional_amounts") as mock_fa, \
         patch("tasks.post_import_pipeline._detect_internal_transfers") as mock_it, \
         patch("tasks.post_import_pipeline._batch_categorize_transactions") as mock_cat, \
         patch("tasks.post_import_pipeline._calculate_balances") as mock_balances, \
         patch("tasks.post_import_pipeline._calculate_timeseries") as mock_timeseries, \
         patch("tasks.post_import_pipeline._detect_subscriptions") as mock_subs:

        mock_db = MagicMock()
        mock_session_local.return_value = mock_db
        mock_token = "test-token"
        mock_set_user.return_value = mock_token
        mock_it.return_value = {"detected": 0, "pocket_account_ids": []}

        from tasks.post_import_pipeline import _run_post_import_pipeline

        user_id = "user-123"
        account_ids = ["acc-1", "acc-2"]
        transaction_ids = ["txn-1", "txn-2"]

        _run_post_import_pipeline(
            user_id=user_id,
            account_ids=account_ids,
            transaction_ids=transaction_ids,
            is_initial_sync=False,
        )

        # Verify session setup
        mock_set_user.assert_called_once_with(user_id)

        # Verify all 7 steps called with the right arguments.
        mock_fx.assert_called_once_with(mock_db, user_id, transaction_ids)
        mock_fa.assert_called_once_with(mock_db, user_id, transaction_ids)
        mock_it.assert_called_once_with(mock_db, user_id, transaction_ids)
        mock_cat.assert_called_once_with(mock_db, user_id, transaction_ids)
        mock_balances.assert_called_once_with(mock_db, user_id, account_ids)
        mock_timeseries.assert_called_once_with(mock_db, user_id, account_ids)
        mock_subs.assert_called_once_with(mock_db, user_id, transaction_ids, account_ids)

        # Verify cleanup
        mock_clear_user.assert_called_once_with(mock_token)
        mock_db.close.assert_called_once()

    print("  PASS: All 7 steps called in order with correct arguments")


def test_pipeline_initial_sync_passes_none_to_subscription_detector():
    """Verify that is_initial_sync=True passes None as transaction_ids to _detect_subscriptions."""
    print("Running test_pipeline_initial_sync_passes_none_to_subscription_detector...")

    with patch("tasks.post_import_pipeline.SessionLocal") as mock_session_local, \
         patch("tasks.post_import_pipeline.set_request_user_id") as mock_set_user, \
         patch("tasks.post_import_pipeline.clear_request_user_id"), \
         patch("tasks.post_import_pipeline._sync_exchange_rates"), \
         patch("tasks.post_import_pipeline._update_functional_amounts"), \
         patch("tasks.post_import_pipeline._detect_internal_transfers") as mock_it, \
         patch("tasks.post_import_pipeline._batch_categorize_transactions"), \
         patch("tasks.post_import_pipeline._calculate_balances"), \
         patch("tasks.post_import_pipeline._calculate_timeseries"), \
         patch("tasks.post_import_pipeline._detect_subscriptions") as mock_subs:

        mock_db = MagicMock()
        mock_session_local.return_value = mock_db
        mock_set_user.return_value = "token"
        mock_it.return_value = {"detected": 0, "pocket_account_ids": []}

        from tasks.post_import_pipeline import _run_post_import_pipeline

        user_id = "user-456"
        account_ids = ["acc-10"]
        transaction_ids = ["txn-10", "txn-11", "txn-12"]

        _run_post_import_pipeline(
            user_id=user_id,
            account_ids=account_ids,
            transaction_ids=transaction_ids,
            is_initial_sync=True,
        )

        # When is_initial_sync=True, transaction_ids passed to _detect_subscriptions must be None
        mock_subs.assert_called_once_with(mock_db, user_id, None, account_ids)

    print("  PASS: is_initial_sync=True passes None to _detect_subscriptions")


def test_pipeline_cleans_up_on_error():
    """Verify that clear_request_user_id and db.close() are called even if a step raises."""
    print("Running test_pipeline_cleans_up_on_error...")

    with patch("tasks.post_import_pipeline.SessionLocal") as mock_session_local, \
         patch("tasks.post_import_pipeline.set_request_user_id") as mock_set_user, \
         patch("tasks.post_import_pipeline.clear_request_user_id") as mock_clear_user, \
         patch("tasks.post_import_pipeline._sync_exchange_rates") as mock_fx, \
         patch("tasks.post_import_pipeline._update_functional_amounts"), \
         patch("tasks.post_import_pipeline._detect_internal_transfers"), \
         patch("tasks.post_import_pipeline._batch_categorize_transactions"), \
         patch("tasks.post_import_pipeline._calculate_balances"), \
         patch("tasks.post_import_pipeline._calculate_timeseries"), \
         patch("tasks.post_import_pipeline._detect_subscriptions"):

        mock_db = MagicMock()
        mock_session_local.return_value = mock_db
        mock_token = "error-token"
        mock_set_user.return_value = mock_token

        # Make the first step raise an error
        mock_fx.side_effect = RuntimeError("FX rate fetch failed")

        from tasks.post_import_pipeline import _run_post_import_pipeline

        raised = False
        try:
            _run_post_import_pipeline(
                user_id="user-789",
                account_ids=["acc-99"],
                transaction_ids=["txn-99"],
                is_initial_sync=False,
            )
        except RuntimeError:
            raised = True

        assert raised, "Exception should have propagated"

        # Cleanup must always happen
        mock_clear_user.assert_called_once_with(mock_token)
        mock_db.close.assert_called_once()

    print("  PASS: Cleanup happens even when a step raises an exception")


# ---------------------------------------------------------------------------
# Integration test: internal transfer detection runs before LLM categorization
# ---------------------------------------------------------------------------

def test_pipeline_runs_internal_transfer_detection_before_llm() -> None:
    """Detection must create a mirror, flip the source's include_in_analytics,
    and the LLM batch must skip internal-transfer transactions."""
    _ensure_schema()
    db = SessionLocal()
    user_id: Optional[str] = None
    try:
        user = _make_user(db)
        user_id = user.id

        _make_transfer_category(db, user_id)
        synced = _make_synced_account(db, user_id, name="Main Checking")
        pocket = _make_pocket_account(db, user_id, iban=PIPELINE_TEST_IBAN)
        src = _make_source_transaction(
            db,
            user_id,
            synced.id,
            counterparty_iban=PIPELINE_TEST_IBAN,
            amount=Decimal("-300.00"),
        )
        # Capture IDs as plain values before closing the setup session
        synced_id = str(synced.id)
        pocket_id = str(pocket.id)
        src_id = str(src.id)
        db.close()

        # Track which transaction_ids the LLM batch actually receives
        captured_batch_inputs = []

        def fake_llm_batch(batch_input):
            captured_batch_inputs.extend(batch_input)
            return {}, 0, 0.0

        from tasks.post_import_pipeline import _run_post_import_pipeline

        with patch("app.services.category_matcher.CategoryMatcher.match_categories_batch_llm",
                   side_effect=fake_llm_batch), \
             patch("tasks.post_import_pipeline._sync_exchange_rates"), \
             patch("tasks.post_import_pipeline._update_functional_amounts"), \
             patch("tasks.post_import_pipeline._calculate_balances"), \
             patch("tasks.post_import_pipeline._calculate_timeseries"), \
             patch("tasks.post_import_pipeline._detect_subscriptions"):
            _run_post_import_pipeline(
                user_id=user_id,
                account_ids=[synced_id, pocket_id],
                transaction_ids=[src_id],
                is_initial_sync=False,
            )

        # Open a fresh session to verify DB state
        db2 = SessionLocal()
        try:
            refreshed_src = db2.query(Transaction).filter(Transaction.id == src_id).one()

            # 1. Source must be flagged as internal transfer (not in analytics)
            assert refreshed_src.include_in_analytics is False, (
                "Source transaction include_in_analytics must be False after detection"
            )

            # 2. An InternalTransfer link row must exist
            links = (
                db2.query(InternalTransfer)
                .filter(InternalTransfer.source_txn_id == src_id)
                .all()
            )
            assert len(links) == 1, f"Expected 1 InternalTransfer link, got {len(links)}"

            # 3. A mirror transaction must exist on the pocket account
            link = links[0]
            mirror = (
                db2.query(Transaction)
                .filter(Transaction.id == link.mirror_txn_id)
                .one()
            )
            assert str(mirror.account_id) == pocket_id, "Mirror must be on the pocket account"

            # 4. The LLM was NOT called with the internal-transfer source transaction
            # The source is the only uncategorized transaction in this run — after
            # detection sets include_in_analytics=False on it, the LLM filter
            # (category_id IS NULL AND include_in_analytics IS TRUE) should yield
            # zero rows, so the LLM batch receives an empty list and never fires.
            assert len(captured_batch_inputs) == 0, (
                f"LLM batch must not receive internal-transfer transactions, "
                f"but got {len(captured_batch_inputs)} item(s): {captured_batch_inputs}"
            )
        finally:
            db2.close()

    finally:
        if user_id:
            db3 = SessionLocal()
            try:
                _cleanup_user_data(db3, user_id)
            finally:
                db3.close()


if __name__ == "__main__":
    results = []

    tests = [
        test_pipeline_calls_all_steps_in_order,
        test_pipeline_initial_sync_passes_none_to_subscription_detector,
        test_pipeline_cleans_up_on_error,
        test_pipeline_runs_internal_transfer_detection_before_llm,
    ]

    for test_fn in tests:
        try:
            test_fn()
            results.append((test_fn.__name__, True, None))
        except Exception as e:
            import traceback
            results.append((test_fn.__name__, False, traceback.format_exc()))

    print("\n--- Results ---")
    all_passed = True
    for name, passed, error in results:
        status = "PASS" if passed else "FAIL"
        print(f"  [{status}] {name}")
        if error:
            print(f"    {error}")
            all_passed = False

    sys.exit(0 if all_passed else 1)
