import pytest
from uuid import uuid4
from app.services.ownership_service import (
    resolve_shares,
    attribute_amount,
)

def test_resolve_shares_single_owner_null():
    pid = str(uuid4())
    assert resolve_shares([{"person_id": pid, "share": None}]) == {pid: 1.0}

def test_resolve_shares_equal_split():
    a, b = str(uuid4()), str(uuid4())
    out = resolve_shares([{"person_id": a, "share": None}, {"person_id": b, "share": None}])
    assert out[a] == pytest.approx(0.5)
    assert out[b] == pytest.approx(0.5)

def test_resolve_shares_explicit():
    a, b = str(uuid4()), str(uuid4())
    out = resolve_shares([{"person_id": a, "share": 0.7}, {"person_id": b, "share": 0.3}])
    assert out[a] == pytest.approx(0.7)
    assert out[b] == pytest.approx(0.3)

def test_attribute_amount_full_for_null_filter():
    assert attribute_amount(100, [{"person_id": "x", "share": None}], None) == 100

def test_attribute_amount_zero_for_non_owner():
    assert attribute_amount(100, [{"person_id": "x", "share": None}], "y") == 0

def test_attribute_amount_explicit_share():
    a = "a"
    assert attribute_amount(100, [{"person_id": a, "share": 0.4}, {"person_id": "b", "share": 0.6}], a) == pytest.approx(40)
