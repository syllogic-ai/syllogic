"""
Unit tests for the encryption upgrade orchestration script.
"""
import os
import sys
from unittest.mock import patch

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from postgres_migration.run_encryption_upgrade import (  # noqa: E402
    coverage_is_complete,
    main,
)


def _coverage(
    *,
    accounts_missing_encryption: int = 0,
    csv_missing_encryption: int = 0,
    external_id_plaintext_present: int = 0,
    file_path_plaintext_present: int = 0,
) -> dict[str, int]:
    return {
        "accounts_total": 10,
        "external_id_plaintext_present": external_id_plaintext_present,
        "external_id_ciphertext_present": 10,
        "external_id_hash_present": 10,
        "accounts_missing_encryption": accounts_missing_encryption,
        "csv_total": 10,
        "file_path_plaintext_present": file_path_plaintext_present,
        "file_path_ciphertext_present": 10,
        "csv_missing_encryption": csv_missing_encryption,
    }


def test_coverage_is_complete() -> None:
    assert coverage_is_complete(_coverage(), require_plaintext_cleared=False) is True
    assert coverage_is_complete(
        _coverage(accounts_missing_encryption=1),
        require_plaintext_cleared=False,
    ) is False
    assert coverage_is_complete(
        _coverage(csv_missing_encryption=1),
        require_plaintext_cleared=False,
    ) is False
    assert coverage_is_complete(
        _coverage(external_id_plaintext_present=2),
        require_plaintext_cleared=True,
    ) is False
    assert coverage_is_complete(
        _coverage(file_path_plaintext_present=1),
        require_plaintext_cleared=True,
    ) is False
    print("✓ coverage completion checks")


def test_main_exit_codes() -> None:
    backfill_result = {"accounts_updated": 5, "csv_imports_updated": 5}

    with patch(
        "postgres_migration.run_encryption_upgrade.run_upgrade",
        return_value=(backfill_result, _coverage()),
    ):
        assert main(["--batch-size", "100"]) == 0

    with patch(
        "postgres_migration.run_encryption_upgrade.run_upgrade",
        return_value=(backfill_result, _coverage(accounts_missing_encryption=2)),
    ):
        assert main(["--batch-size", "100"]) == 1

    with patch(
        "postgres_migration.run_encryption_upgrade.run_upgrade",
        return_value=(
            backfill_result,
            _coverage(external_id_plaintext_present=1, file_path_plaintext_present=1),
        ),
    ):
        assert main(["--batch-size", "100", "--clear-plaintext"]) == 1

    with patch(
        "postgres_migration.run_encryption_upgrade.run_upgrade",
        return_value=(backfill_result, _coverage()),
    ):
        assert main(["--batch-size", "100", "--dry-run"]) == 0

    print("✓ main exit code checks")


if __name__ == "__main__":
    test_coverage_is_complete()
    test_main_exit_codes()
    print("All encryption upgrade tests passed.")
