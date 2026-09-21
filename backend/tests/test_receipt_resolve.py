"""Tests for `app.services.receipt_resolve` (Phase 6.1). Pure functions --
no DB, no LLM -- so lines/scans here are plain dataclasses, not ORM rows.
See docs/specs/receipt-ingestion-implementation.md 6.1 and its "Phase 6
checkpoint": grouping sums to `printed_total` for every fixture, and the
collapse triggers at exactly the threshold and not one cent above.
"""

from dataclasses import dataclass
from decimal import Decimal
from typing import Optional
from uuid import UUID, uuid4

import pytest

from app.services.receipt_resolve import (
    ResolveConfig,
    ResolveError,
    group_and_sum,
    resolve,
)

GROCERY_CATEGORY_ID = uuid4()
DINING_CATEGORY_ID = uuid4()
HOUSEHOLD_CATEGORY_ID = uuid4()


@dataclass(frozen=True)
class Line:
    line_ref: str
    category_id: Optional[UUID]
    net_amount: Decimal


@dataclass(frozen=True)
class Scan:
    printed_total: Optional[Decimal]
    merchant_name: Optional[str]


def _config(
    threshold: Optional[str] = "5.00",
    merchants: frozenset[str] = frozenset({"rimi"}),
    grocery_category_id: Optional[UUID] = GROCERY_CATEGORY_ID,
) -> ResolveConfig:
    return ResolveConfig(
        grocery_merchants=merchants,
        grocery_category_id=grocery_category_id,
        treat_split_threshold=Decimal(threshold) if threshold is not None else None,
    )


# ---------------------------------------------------------------------------
# group_and_sum
# ---------------------------------------------------------------------------


def test_group_and_sum_groups_by_category_and_sums_decimal():
    lines = [
        Line("L1", GROCERY_CATEGORY_ID, Decimal("3.49")),
        Line("L2", GROCERY_CATEGORY_ID, Decimal("2.10")),
        Line("L3", DINING_CATEGORY_ID, Decimal("4.00")),
    ]
    groups = {g.category_id: g for g in group_and_sum(lines)}
    assert groups[GROCERY_CATEGORY_ID].amount == Decimal("5.59")
    assert groups[GROCERY_CATEGORY_ID].line_refs == ("L1", "L2")
    assert groups[DINING_CATEGORY_ID].amount == Decimal("4.00")
    assert groups[DINING_CATEGORY_ID].line_refs == ("L3",)


def test_group_and_sum_handles_uncategorized_lines_as_their_own_group():
    lines = [Line("L1", None, Decimal("1.00")), Line("L2", None, Decimal("2.00"))]
    groups = group_and_sum(lines)
    assert len(groups) == 1
    assert groups[0].category_id is None
    assert groups[0].amount == Decimal("3.00")


def test_group_and_sum_treats_missing_net_amount_as_zero():
    lines = [Line("L1", GROCERY_CATEGORY_ID, None)]  # type: ignore[arg-type]
    groups = group_and_sum(lines)
    assert groups[0].amount == Decimal("0")


# ---------------------------------------------------------------------------
# resolve -- grouping sums to printed_total (Phase 6 checkpoint, "for every
# fixture")
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "lines,printed_total",
    [
        # Single-category grocery run, no collapse-relevant categories.
        (
            [
                Line("L1", GROCERY_CATEGORY_ID, Decimal("3.49")),
                Line("L2", GROCERY_CATEGORY_ID, Decimal("2.10")),
            ],
            Decimal("5.59"),
        ),
        # Multi-category receipt at a non-grocery merchant -- no collapse.
        (
            [
                Line("L1", HOUSEHOLD_CATEGORY_ID, Decimal("12.00")),
                Line("L2", DINING_CATEGORY_ID, Decimal("4.50")),
            ],
            Decimal("16.50"),
        ),
        # One uncategorized line alongside categorized ones.
        (
            [
                Line("L1", GROCERY_CATEGORY_ID, Decimal("10.00")),
                Line("L2", None, Decimal("0.99")),
            ],
            Decimal("10.99"),
        ),
    ],
)
def test_resolve_groups_sum_to_printed_total(lines, printed_total):
    scan = Scan(printed_total=printed_total, merchant_name="Some Other Shop")
    config = _config(threshold=None)  # collapse irrelevant to this checkpoint
    groups = resolve(scan, lines, config)
    assert sum((g.amount for g in groups), Decimal("0")) == printed_total


def test_resolve_raises_when_groups_do_not_sum_to_printed_total():
    scan = Scan(printed_total=Decimal("99.99"), merchant_name="Rimi")
    lines = [Line("L1", GROCERY_CATEGORY_ID, Decimal("5.00"))]
    with pytest.raises(ResolveError):
        resolve(scan, lines, _config(threshold=None))


def test_resolve_raises_when_printed_total_missing():
    scan = Scan(printed_total=None, merchant_name="Rimi")
    lines = [Line("L1", GROCERY_CATEGORY_ID, Decimal("5.00"))]
    with pytest.raises(ResolveError):
        resolve(scan, lines, _config())


# ---------------------------------------------------------------------------
# Merchant/threshold collapse -- exact-boundary checkpoint
# ---------------------------------------------------------------------------


def test_collapse_triggers_at_exactly_the_threshold():
    """treat_total == threshold (5.00) must collapse."""
    scan = Scan(printed_total=Decimal("30.00"), merchant_name="Rimi")
    lines = [
        Line("L1", GROCERY_CATEGORY_ID, Decimal("25.00")),
        Line("L2", DINING_CATEGORY_ID, Decimal("5.00")),
    ]
    groups = resolve(scan, lines, _config(threshold="5.00"))
    assert len(groups) == 1
    assert groups[0].category_id == GROCERY_CATEGORY_ID
    assert groups[0].amount == Decimal("30.00")
    assert set(groups[0].line_refs) == {"L1", "L2"}


def test_collapse_does_not_trigger_one_cent_above_threshold():
    """treat_total == threshold + 0.01 must NOT collapse."""
    scan = Scan(printed_total=Decimal("30.01"), merchant_name="Rimi")
    lines = [
        Line("L1", GROCERY_CATEGORY_ID, Decimal("25.00")),
        Line("L2", DINING_CATEGORY_ID, Decimal("5.01")),
    ]
    groups = resolve(scan, lines, _config(threshold="5.00"))
    by_category = {g.category_id: g.amount for g in groups}
    assert by_category == {
        GROCERY_CATEGORY_ID: Decimal("25.00"),
        DINING_CATEGORY_ID: Decimal("5.01"),
    }


def test_collapse_does_not_trigger_at_a_non_grocery_merchant():
    scan = Scan(printed_total=Decimal("30.00"), merchant_name="Some Cafe")
    lines = [
        Line("L1", GROCERY_CATEGORY_ID, Decimal("25.00")),
        Line("L2", DINING_CATEGORY_ID, Decimal("5.00")),
    ]
    groups = resolve(scan, lines, _config(threshold="5.00", merchants=frozenset({"rimi"})))
    assert len(groups) == 2


def test_collapse_disabled_when_threshold_is_none():
    scan = Scan(printed_total=Decimal("30.00"), merchant_name="Rimi")
    lines = [
        Line("L1", GROCERY_CATEGORY_ID, Decimal("25.00")),
        Line("L2", DINING_CATEGORY_ID, Decimal("5.00")),
    ]
    groups = resolve(scan, lines, _config(threshold=None))
    assert len(groups) == 2


def test_collapse_disabled_when_grocery_category_id_is_none():
    scan = Scan(printed_total=Decimal("30.00"), merchant_name="Rimi")
    lines = [
        Line("L1", GROCERY_CATEGORY_ID, Decimal("25.00")),
        Line("L2", DINING_CATEGORY_ID, Decimal("5.00")),
    ]
    groups = resolve(scan, lines, _config(threshold="5.00", grocery_category_id=None))
    assert len(groups) == 2


def test_merchant_match_is_case_insensitive():
    scan = Scan(printed_total=Decimal("30.00"), merchant_name="RIMI Hypermarket".upper())
    lines = [
        Line("L1", GROCERY_CATEGORY_ID, Decimal("25.00")),
        Line("L2", DINING_CATEGORY_ID, Decimal("5.00")),
    ]
    config = _config(threshold="5.00", merchants=frozenset({"rimi hypermarket".lower()}))
    groups = resolve(scan, lines, config)
    assert len(groups) == 1
