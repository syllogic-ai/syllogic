import pytest
from app.schemas_routines import validate_slots


pinned_a = {"id": "a", "kind": "pinned", "symbol": "VUAA", "amount": 400}
pinned_b = {"id": "b", "kind": "pinned", "symbol": "VWCE", "amount": 200}
disc_c = {"id": "c", "kind": "discretionary", "theme": "clean energy", "amount": 200}


def test_rejects_empty():
    with pytest.raises(ValueError, match="at least one slot"):
        validate_slots([], 100)


def test_rejects_zero_amount():
    with pytest.raises(ValueError, match="amount must be > 0"):
        validate_slots([{**pinned_a, "amount": 0}], 0)


def test_rejects_pinned_without_symbol():
    with pytest.raises(ValueError, match="symbol"):
        validate_slots([{"id": "x", "kind": "pinned", "symbol": "", "amount": 100}], 100)


def test_rejects_discretionary_without_theme():
    with pytest.raises(ValueError, match="theme"):
        validate_slots([{"id": "x", "kind": "discretionary", "theme": "", "amount": 100}], 100)


def test_rejects_duplicate_id():
    with pytest.raises(ValueError, match="duplicate"):
        validate_slots([pinned_a, pinned_a], 800)


def test_rejects_bad_sum():
    with pytest.raises(ValueError, match="sum"):
        validate_slots([pinned_a, pinned_b], 700)


def test_accepts_valid():
    validate_slots([pinned_a, disc_c], 600)


def test_accepts_within_tolerance():
    validate_slots([{**pinned_a, "amount": 400.001}], 400)
