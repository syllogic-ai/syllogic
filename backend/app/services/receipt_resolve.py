"""Stage 3 of the receipt-ingestion pipeline: resolve stage-2 per-line
category assignments into the transaction groups that actually get booked.
See docs/specs/receipt-ingestion.md Part 6.1 and
docs/specs/receipt-ingestion-implementation.md 6.1.

Pure code, deliberately: no DB, no LLM call. This is where receipt-level
*policy* lives, and the reason stage 2 assigns a category per line rather
than per receipt -- the grouping and the merchant/threshold collapse are
both code decisions, made the same way every time given the same inputs,
never a model judgment that could vary between two runs on the same photo.

The final `assert sum(groups) == printed_total` is not defensive decoration.
It is the last checkpoint before a caller writes anything to the ledger --
`ResolveError` is raised instead of an assert so a caller gets a catchable,
descriptive failure rather than an `AssertionError` (which would fire even
when running with `python -O`).
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Optional, Protocol, Sequence
from uuid import UUID


class ResolveError(RuntimeError):
    """Raised when the resolved groups don't sum to `printed_total`. Never
    caught to book a partial or best-effort result -- an unresolved receipt
    is not bookable at all."""


class LineForResolve(Protocol):
    """The minimal shape `resolve`/`group_and_sum` need from a line. Matches
    `ReceiptLineItem`'s own attribute names, so ORM rows can be passed
    directly; tests can pass any object (dataclass, `SimpleNamespace`, ...)
    with the same three attributes instead of touching a database."""

    line_ref: str
    category_id: Optional[UUID]
    net_amount: Optional[Decimal]


class ScanForResolve(Protocol):
    """The minimal shape `resolve` needs from a receipt scan."""

    printed_total: Optional[Decimal]
    merchant_name: Optional[str]


@dataclass(frozen=True)
class TransactionGroup:
    """One category's worth of a receipt, ready to become one `Transaction`.
    `line_refs` is preserved (not just a count) so the caller can write
    `booked_transaction_id` back onto exactly the right `ReceiptLineItem`
    rows after insert."""

    category_id: Optional[UUID]
    amount: Decimal
    line_refs: tuple[str, ...]


@dataclass(frozen=True)
class ResolveConfig:
    """Receipt-resolve policy, sourced from `app_settings`
    (`get_effective_receipt_resolve_config`) -- never a literal in this
    module and never prompt text. `grocery_merchants` is matched
    case-insensitively; callers are expected to have already lower-cased it
    (`app_settings` does), but `resolve` normalizes again defensively since
    a hand-built `ResolveConfig` in a test is not guaranteed to.

    `treat_split_threshold=None` disables the collapse entirely, regardless
    of `grocery_merchants`/`grocery_category_id`.
    """

    grocery_merchants: frozenset[str]
    grocery_category_id: Optional[UUID]
    treat_split_threshold: Optional[Decimal]


def _normalize_merchant(name: Optional[str]) -> str:
    return (name or "").strip().lower()


def group_and_sum(lines: Sequence[LineForResolve]) -> list[TransactionGroup]:
    """Groups lines by `category_id` and sums `net_amount` in `Decimal`,
    preserving each group's line refs. Lines with no category assigned
    (`category_id is None`) form their own group -- a receipt with
    uncategorized lines is still resolvable and still books, just under an
    uncategorized group, rather than raising here (booking with no category
    is a valid outcome; refusing to book at all is `receipt_validate`'s job,
    upstream of this module, not this one's).
    """
    order: list[Optional[UUID]] = []
    amounts: dict[Optional[UUID], Decimal] = {}
    refs: dict[Optional[UUID], list[str]] = {}

    for line in lines:
        category_id = line.category_id
        if category_id not in amounts:
            order.append(category_id)
            amounts[category_id] = Decimal("0")
            refs[category_id] = []
        amounts[category_id] += line.net_amount if line.net_amount is not None else Decimal("0")
        refs[category_id].append(line.line_ref)

    return [
        TransactionGroup(category_id=cat, amount=amounts[cat], line_refs=tuple(refs[cat]))
        for cat in order
    ]


def _collapse_into_groceries(
    groups: list[TransactionGroup], config: ResolveConfig
) -> list[TransactionGroup]:
    """Spec 6.1's merchant/threshold collapse: at a grocery merchant, if
    everything that *isn't* already the grocery category sums to at most
    `treat_split_threshold`, the whole receipt collapses into one grocery
    transaction. `<=`, not `<` -- the threshold is inclusive, so a treat
    total exactly at the threshold collapses and one cent above does not.
    """
    if config.treat_split_threshold is None or config.grocery_category_id is None:
        return groups

    treat_total = sum(
        (g.amount for g in groups if g.category_id != config.grocery_category_id),
        Decimal("0"),
    )
    if treat_total > config.treat_split_threshold:
        return groups

    grand_total = sum((g.amount for g in groups), Decimal("0"))
    all_refs = tuple(ref for g in groups for ref in g.line_refs)
    return [
        TransactionGroup(
            category_id=config.grocery_category_id,
            amount=grand_total,
            line_refs=all_refs,
        )
    ]


def resolve(
    scan: ScanForResolve,
    lines: Sequence[LineForResolve],
    config: ResolveConfig,
) -> list[TransactionGroup]:
    """Groups `lines` by category, applies the merchant/threshold collapse,
    then asserts the result sums to `scan.printed_total` -- the last
    checkpoint before a caller books anything. Raises `ResolveError` (never
    returns a partial result) if:

    - `scan.printed_total` is missing, or
    - the resolved groups don't sum to it, to the cent.
    """
    groups = group_and_sum(lines)

    merchants = frozenset(m.strip().lower() for m in config.grocery_merchants)
    if _normalize_merchant(scan.merchant_name) in merchants:
        groups = _collapse_into_groceries(groups, config)

    if scan.printed_total is None:
        raise ResolveError("Cannot resolve: scan.printed_total is not set.")

    printed_total = Decimal(scan.printed_total)
    resolved_total = sum((g.amount for g in groups), Decimal("0"))
    if resolved_total != printed_total:
        raise ResolveError(
            f"Resolved groups sum to {resolved_total}, but printed_total is "
            f"{printed_total}. Refusing to book a receipt that doesn't add up."
        )

    return groups
