"""Balance-anchor type selection for Enable Banking syncs.

Pure-function tests — no database. Pins the priority order so a reshuffle is
a deliberate, test-breaking act: XPCD (booked + pending) outranks CLBD
(booked only) because banks that return no available-type balance (ABN AMRO)
otherwise show a balance that sits above the bank app's number by exactly
the pending amount until transactions book.
"""
from tasks.enable_banking_tasks import BALANCE_TYPE_PRIORITY, _choose_balance


def _bal(btype, amount):
    return {"balance_type": btype, "balance_amount": {"amount": amount, "currency": "EUR"}}


def test_available_still_wins_when_present():
    balances = [_bal("CLBD", "814.00"), _bal("ITAV", "614.00"), _bal("XPCD", "614.00")]
    assert _choose_balance(balances)["balance_type"] == "ITAV"


def test_expected_beats_booked_the_abn_amro_case():
    # ABN AMRO returns no CLAV/ITAV; the user's bank app shows the
    # pending-inclusive number. XPCD must win over CLBD.
    balances = [_bal("CLBD", "814.00"), _bal("XPCD", "614.00")]
    assert _choose_balance(balances)["balance_type"] == "XPCD"
    assert _choose_balance(balances)["balance_amount"]["amount"] == "614.00"


def test_booked_only_bank_still_anchors():
    balances = [_bal("CLBD", "814.00")]
    assert _choose_balance(balances)["balance_type"] == "CLBD"


def test_unknown_types_fall_back_to_first_entry():
    balances = [_bal("WEIRD", "1.00"), _bal("ALSO_WEIRD", "2.00")]
    assert _choose_balance(balances)["balance_amount"]["amount"] == "1.00"


def test_case_insensitive_matching():
    balances = [_bal("clbd", "814.00"), _bal("xpcd", "614.00")]
    assert _choose_balance(balances)["balance_type"] == "xpcd"


def test_empty_returns_none():
    assert _choose_balance([]) is None


def test_priority_order_is_pinned():
    assert BALANCE_TYPE_PRIORITY == ("CLAV", "ITAV", "XPCD", "CLBD", "PRCD", "OTHR")
