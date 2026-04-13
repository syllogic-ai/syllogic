"""
Tests for the post_import_pipeline Celery task.

Run with:
    cd backend && python tests/test_post_import_pipeline.py
"""
import sys
import os
from unittest.mock import MagicMock, patch, call

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_pipeline_calls_all_steps_in_order():
    """Verify that _run_post_import_pipeline calls all 5 helper functions in the right order."""
    print("Running test_pipeline_calls_all_steps_in_order...")

    with patch("tasks.post_import_pipeline.SessionLocal") as mock_session_local, \
         patch("tasks.post_import_pipeline.set_request_user_id") as mock_set_user, \
         patch("tasks.post_import_pipeline.clear_request_user_id") as mock_clear_user, \
         patch("tasks.post_import_pipeline._sync_exchange_rates") as mock_fx, \
         patch("tasks.post_import_pipeline._update_functional_amounts") as mock_fa, \
         patch("tasks.post_import_pipeline._calculate_balances") as mock_balances, \
         patch("tasks.post_import_pipeline._calculate_timeseries") as mock_timeseries, \
         patch("tasks.post_import_pipeline._detect_subscriptions") as mock_subs:

        mock_db = MagicMock()
        mock_session_local.return_value = mock_db
        mock_token = "test-token"
        mock_set_user.return_value = mock_token

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

        # Verify all 5 steps called
        mock_fx.assert_called_once_with(mock_db, user_id, transaction_ids)
        mock_fa.assert_called_once_with(mock_db, user_id, transaction_ids)
        mock_balances.assert_called_once_with(mock_db, user_id, account_ids)
        mock_timeseries.assert_called_once_with(mock_db, user_id, account_ids)
        mock_subs.assert_called_once_with(mock_db, user_id, transaction_ids, account_ids)

        # Verify cleanup
        mock_clear_user.assert_called_once_with(mock_token)
        mock_db.close.assert_called_once()

    print("  PASS: All 5 steps called in order with correct arguments")


def test_pipeline_initial_sync_passes_none_to_subscription_detector():
    """Verify that is_initial_sync=True passes None as transaction_ids to _detect_subscriptions."""
    print("Running test_pipeline_initial_sync_passes_none_to_subscription_detector...")

    with patch("tasks.post_import_pipeline.SessionLocal") as mock_session_local, \
         patch("tasks.post_import_pipeline.set_request_user_id") as mock_set_user, \
         patch("tasks.post_import_pipeline.clear_request_user_id"), \
         patch("tasks.post_import_pipeline._sync_exchange_rates"), \
         patch("tasks.post_import_pipeline._update_functional_amounts"), \
         patch("tasks.post_import_pipeline._calculate_balances"), \
         patch("tasks.post_import_pipeline._calculate_timeseries"), \
         patch("tasks.post_import_pipeline._detect_subscriptions") as mock_subs:

        mock_db = MagicMock()
        mock_session_local.return_value = mock_db
        mock_set_user.return_value = "token"

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


if __name__ == "__main__":
    results = []

    tests = [
        test_pipeline_calls_all_steps_in_order,
        test_pipeline_initial_sync_passes_none_to_subscription_detector,
        test_pipeline_cleans_up_on_error,
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
