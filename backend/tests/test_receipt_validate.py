"""Tests for `app.services.receipt_validate` -- pure-function validation of an
extracted receipt (Phase 4 of the receipt-ingestion rework). See
docs/specs/receipt-ingestion-implementation.md "Phase 4 tests" and
docs/specs/receipt-ingestion.md Part 1.2.

No DB, no model, no HTTP -- this module is where the real correctness of the
rework lives, so it's tested in isolation before anything else in Phase 4.
"""

from decimal import Decimal

from app.services.receipt_extract import ExtractedLine, ExtractedReceipt
from app.services.receipt_validate import (
    BAD_CURRENCY,
    BAD_DATE,
    BAD_TOTAL,
    DISCOUNT_MISMATCH,
    LINE_ARITHMETIC,
    ORPHAN_DEPOSIT,
    TOTAL_MISMATCH,
    validate,
)


def _receipt(**overrides) -> ExtractedReceipt:
    defaults = dict(
        merchant_name="Test Store",
        merchant_legal_name=None,
        merchant_address=None,
        receipt_no=None,
        fiscal_code=None,
        vat_id=None,
        booked_at="2026-08-18T10:00:00",
        currency="EUR",
        payment_method="card",
        card_last4=None,
        printed_total=Decimal("3.49"),
        printed_discount_total=None,
        lines=[],
        extraction_model="gpt-4o-mini",
    )
    defaults.update(overrides)
    return ExtractedReceipt(**defaults)


def _line(id_, name, net, gross=None, discount=Decimal("0"), kind="item", parent_id=None):
    return ExtractedLine(
        id=id_,
        raw_text=name,
        name=name,
        quantity=None,
        gross_amount=gross if gross is not None else net,
        discount_amount=discount,
        net_amount=net,
        kind=kind,
        parent_id=parent_id,
    )


def _codes(errors):
    return {e.code for e in errors}


# ---------------------------------------------------------------------------
# A clean receipt reconciles
# ---------------------------------------------------------------------------


def test_clean_single_line_receipt_has_no_errors():
    receipt = _receipt(
        printed_total=Decimal("3.49"),
        lines=[_line("L1", "Milk 2L", Decimal("3.49"))],
    )
    assert validate(receipt) == []


# ---------------------------------------------------------------------------
# Discount line: gross 2.99, discount 0.90, net 2.09 reconciles
# ---------------------------------------------------------------------------


def test_discount_line_reconciles():
    receipt = _receipt(
        printed_total=Decimal("2.09"),
        printed_discount_total=Decimal("0.90"),
        lines=[
            _line(
                "L1", "Coffee", net=Decimal("2.09"), gross=Decimal("2.99"), discount=Decimal("0.90")
            ),
        ],
    )
    assert validate(receipt) == []


def test_discount_line_with_wrong_arithmetic_is_flagged():
    # gross 2.99 - discount 0.90 should be 2.09, not 2.10.
    receipt = _receipt(
        printed_total=Decimal("2.10"),
        lines=[
            _line(
                "L1", "Coffee", net=Decimal("2.10"), gross=Decimal("2.99"), discount=Decimal("0.90")
            ),
        ],
    )
    errors = validate(receipt)
    arithmetic = [e for e in errors if e.code == LINE_ARITHMETIC]
    assert len(arithmetic) == 1
    assert arithmetic[0].line_refs == ("L1",)


# ---------------------------------------------------------------------------
# Deposit lines
# ---------------------------------------------------------------------------


def test_deposit_line_with_valid_parent_reconciles():
    receipt = _receipt(
        printed_total=Decimal("3.49"),
        lines=[
            _line("L1", "Beer 0.5L", net=Decimal("2.99")),
            _line("L2", "Deposit", net=Decimal("0.50"), kind="deposit", parent_id="L1"),
        ],
    )
    assert validate(receipt) == []


def test_orphaned_deposit_line_is_flagged():
    receipt = _receipt(
        printed_total=Decimal("0.50"),
        lines=[
            _line("L1", "Deposit", net=Decimal("0.50"), kind="deposit", parent_id="L99"),
        ],
    )
    errors = validate(receipt)
    orphan = [e for e in errors if e.code == ORPHAN_DEPOSIT]
    assert len(orphan) == 1
    assert orphan[0].line_refs == ("L1",)


def test_deposit_line_with_no_parent_id_at_all_is_orphaned():
    receipt = _receipt(
        printed_total=Decimal("0.50"),
        lines=[
            _line("L1", "Deposit", net=Decimal("0.50"), kind="deposit", parent_id=None),
        ],
    )
    errors = validate(receipt)
    assert ORPHAN_DEPOSIT in _codes(errors)


# ---------------------------------------------------------------------------
# A recap block duplicated into lines
# ---------------------------------------------------------------------------


def test_recap_block_duplicated_into_lines_flags_total_mismatch_naming_the_dupes():
    # "Coffee" appears twice at the same net amount -- as if a recap summary
    # line got turned into its own line entry instead of only informing
    # printed_discount_total. The item sum (4.18) overshoots printed_total
    # (2.09) by exactly the duplicate.
    receipt = _receipt(
        printed_total=Decimal("2.09"),
        lines=[
            _line("L1", "Coffee", net=Decimal("2.09")),
            _line("L2", "Coffee", net=Decimal("2.09")),
        ],
    )
    errors = validate(receipt)
    total_mismatch = [e for e in errors if e.code == TOTAL_MISMATCH]
    assert len(total_mismatch) == 1
    assert set(total_mismatch[0].line_refs) == {"L1", "L2"}


# ---------------------------------------------------------------------------
# Exactness, not tolerance
# ---------------------------------------------------------------------------


def test_one_cent_off_is_flagged_not_tolerated():
    receipt = _receipt(
        printed_total=Decimal("3.50"),
        lines=[_line("L1", "Milk 2L", net=Decimal("3.49"))],
    )
    errors = validate(receipt)
    assert TOTAL_MISMATCH in _codes(errors)


def test_exact_total_has_no_total_mismatch():
    receipt = _receipt(
        printed_total=Decimal("6.48"),
        lines=[
            _line("L1", "Milk 2L", net=Decimal("3.49")),
            _line("L2", "Bread", net=Decimal("2.99")),
        ],
    )
    assert validate(receipt) == []


# ---------------------------------------------------------------------------
# Lithuanian fixture -- regression on spec 0.3 (total detection used to be
# English-keyword-only, so it never ran on a Lithuanian receipt; validate()
# does no keyword matching at all, so language is irrelevant to it).
# ---------------------------------------------------------------------------


def test_lithuanian_receipt_with_printed_total_reconciles():
    receipt = _receipt(
        merchant_name="Maxima",
        currency="EUR",
        printed_total=Decimal("4.58"),
        printed_discount_total=Decimal("0.90"),
        lines=[
            _line(
                "L1",
                "Nealkoholinis kokteilis",
                net=Decimal("2.09"),
                gross=Decimal("2.99"),
                discount=Decimal("0.90"),
            ),
            _line("L2", "Uzstatas", net=Decimal("0.50"), kind="deposit", parent_id="L1"),
            _line("L3", "Duona", net=Decimal("1.99")),
        ],
    )
    assert validate(receipt) == []


def test_lithuanian_receipt_without_printed_total_is_flagged_bad_total():
    # Bug 0.3's actual symptom: printed_total stays unset because nothing
    # matched an English "total" keyword. Under the new pipeline this is a
    # `bad_total` validation error (never booked), not a silently-skipped
    # check.
    receipt = _receipt(printed_total=None, lines=[_line("L1", "Duona", net=Decimal("1.99"))])
    errors = validate(receipt)
    assert BAD_TOTAL in _codes(errors)


# ---------------------------------------------------------------------------
# Header sanity: currency / date / total
# ---------------------------------------------------------------------------


def test_bad_currency_is_flagged():
    receipt = _receipt(
        currency="EUE",
        lines=[_line("L1", "Milk", net=Decimal("3.49"))],
        printed_total=Decimal("3.49"),
    )
    assert BAD_CURRENCY in _codes(validate(receipt))


def test_null_currency_is_flagged():
    receipt = _receipt(
        currency=None,
        lines=[_line("L1", "Milk", net=Decimal("3.49"))],
        printed_total=Decimal("3.49"),
    )
    assert BAD_CURRENCY in _codes(validate(receipt))


def test_unparseable_date_is_flagged():
    receipt = _receipt(
        booked_at="not a date",
        lines=[_line("L1", "Milk", net=Decimal("3.49"))],
        printed_total=Decimal("3.49"),
    )
    assert BAD_DATE in _codes(validate(receipt))


def test_null_date_is_flagged():
    receipt = _receipt(
        booked_at=None,
        lines=[_line("L1", "Milk", net=Decimal("3.49"))],
        printed_total=Decimal("3.49"),
    )
    assert BAD_DATE in _codes(validate(receipt))


def test_iso_date_with_trailing_z_parses():
    receipt = _receipt(
        booked_at="2026-08-18T10:00:00Z",
        lines=[_line("L1", "Milk", net=Decimal("3.49"))],
        printed_total=Decimal("3.49"),
    )
    assert BAD_DATE not in _codes(validate(receipt))


def test_zero_printed_total_is_flagged_bad_total():
    receipt = _receipt(printed_total=Decimal("0"), lines=[_line("L1", "Milk", net=Decimal("0"))])
    assert BAD_TOTAL in _codes(validate(receipt))


def test_negative_printed_total_is_flagged_bad_total():
    receipt = _receipt(
        printed_total=Decimal("-1.00"), lines=[_line("L1", "Milk", net=Decimal("-1.00"))]
    )
    assert BAD_TOTAL in _codes(validate(receipt))


# ---------------------------------------------------------------------------
# discount_mismatch
# ---------------------------------------------------------------------------


def test_discount_total_mismatch_is_flagged():
    receipt = _receipt(
        printed_total=Decimal("2.09"),
        printed_discount_total=Decimal("1.00"),  # actual per-line discount is 0.90
        lines=[
            _line(
                "L1", "Coffee", net=Decimal("2.09"), gross=Decimal("2.99"), discount=Decimal("0.90")
            ),
        ],
    )
    errors = validate(receipt)
    mismatch = [e for e in errors if e.code == DISCOUNT_MISMATCH]
    assert len(mismatch) == 1
    assert mismatch[0].line_refs == ("L1",)


def test_no_discount_mismatch_when_printed_discount_total_absent():
    receipt = _receipt(
        printed_total=Decimal("2.09"),
        printed_discount_total=None,
        lines=[
            _line(
                "L1", "Coffee", net=Decimal("2.09"), gross=Decimal("2.99"), discount=Decimal("0.90")
            ),
        ],
    )
    assert DISCOUNT_MISMATCH not in _codes(validate(receipt))


# ---------------------------------------------------------------------------
# Missing net_amount on a line
# ---------------------------------------------------------------------------


def test_line_with_missing_net_amount_flags_line_arithmetic_and_total_mismatch():
    receipt = _receipt(
        printed_total=Decimal("3.49"),
        lines=[_line("L1", "Milk", net=None)],
    )
    errors = validate(receipt)
    codes = _codes(errors)
    assert LINE_ARITHMETIC in codes
    assert TOTAL_MISMATCH in codes
    total_mismatch = next(e for e in errors if e.code == TOTAL_MISMATCH)
    assert total_mismatch.line_refs == ("L1",)


def test_validate_returns_list_not_raises_on_completely_empty_receipt():
    receipt = _receipt(printed_total=None, currency=None, booked_at=None, lines=[])
    errors = validate(receipt)
    assert isinstance(errors, list)
    assert {BAD_CURRENCY, BAD_DATE, BAD_TOTAL} <= _codes(errors)
