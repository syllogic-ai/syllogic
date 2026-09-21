"""
Pure-function validation of an `ExtractedReceipt` -- no DB, no model calls.
See docs/specs/receipt-ingestion.md Part 1.2 and
docs/specs/receipt-ingestion-implementation.md 4.2.

This is where the real correctness of the receipt-ingestion rework lives: the
model never does arithmetic and never decides whether a receipt is trustworthy
enough to book. `validate()` is the code that decides that instead, in exact
Decimal arithmetic, and returns a list of `ValidationError` rather than
raising -- an empty list means "book it", anything else means
`status="needs_review"` and nothing gets booked.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Dict, List, Tuple

from app.services.receipt_extract import ExtractedLine, ExtractedReceipt

# A currency parses "as ISO 4217" when it's a 3-letter alphabetic code drawn
# from the actual ISO 4217 list, not merely 3 uppercase letters -- an OCR/
# vision misread like "EUE" would otherwise pass a bare regex check. This is
# the standard active-currency list (not exhaustive of every historical or
# non-decimal code, but covers every currency a receipt in ordinary use is
# plausibly denominated in).
ISO_4217_CODES = frozenset(
    {
        "AED",
        "AFN",
        "ALL",
        "AMD",
        "ANG",
        "AOA",
        "ARS",
        "AUD",
        "AWG",
        "AZN",
        "BAM",
        "BBD",
        "BDT",
        "BGN",
        "BHD",
        "BIF",
        "BMD",
        "BND",
        "BOB",
        "BRL",
        "BSD",
        "BTN",
        "BWP",
        "BYN",
        "BZD",
        "CAD",
        "CDF",
        "CHF",
        "CLP",
        "CNY",
        "COP",
        "CRC",
        "CUP",
        "CVE",
        "CZK",
        "DJF",
        "DKK",
        "DOP",
        "DZD",
        "EGP",
        "ERN",
        "ETB",
        "EUR",
        "FJD",
        "FKP",
        "GBP",
        "GEL",
        "GHS",
        "GIP",
        "GMD",
        "GNF",
        "GTQ",
        "GYD",
        "HKD",
        "HNL",
        "HRK",
        "HTG",
        "HUF",
        "IDR",
        "ILS",
        "INR",
        "IQD",
        "IRR",
        "ISK",
        "JMD",
        "JOD",
        "JPY",
        "KES",
        "KGS",
        "KHR",
        "KMF",
        "KPW",
        "KRW",
        "KWD",
        "KYD",
        "KZT",
        "LAK",
        "LBP",
        "LKR",
        "LRD",
        "LSL",
        "LYD",
        "MAD",
        "MDL",
        "MGA",
        "MKD",
        "MMK",
        "MNT",
        "MOP",
        "MRU",
        "MUR",
        "MVR",
        "MWK",
        "MXN",
        "MYR",
        "MZN",
        "NAD",
        "NGN",
        "NIO",
        "NOK",
        "NPR",
        "NZD",
        "OMR",
        "PAB",
        "PEN",
        "PGK",
        "PHP",
        "PKR",
        "PLN",
        "PYG",
        "QAR",
        "RON",
        "RSD",
        "RUB",
        "RWF",
        "SAR",
        "SBD",
        "SCR",
        "SDG",
        "SEK",
        "SGD",
        "SHP",
        "SLE",
        "SLL",
        "SOS",
        "SRD",
        "SSP",
        "STN",
        "SYP",
        "SZL",
        "THB",
        "TJS",
        "TMT",
        "TND",
        "TOP",
        "TRY",
        "TTD",
        "TWD",
        "TZS",
        "UAH",
        "UGX",
        "USD",
        "UYU",
        "UZS",
        "VES",
        "VND",
        "VUV",
        "WST",
        "XAF",
        "XCD",
        "XOF",
        "XPF",
        "YER",
        "ZAR",
        "ZMW",
        "ZWL",
    }
)

# Validation error codes.
TOTAL_MISMATCH = "total_mismatch"
DISCOUNT_MISMATCH = "discount_mismatch"
ORPHAN_DEPOSIT = "orphan_deposit"
LINE_ARITHMETIC = "line_arithmetic"
BAD_CURRENCY = "bad_currency"
BAD_DATE = "bad_date"
BAD_TOTAL = "bad_total"


@dataclass(frozen=True)
class ValidationError:
    """One reconcile failure. `line_refs` names the `ExtractedLine.id`s
    involved so the review UI can highlight exactly those rows against the
    stored image -- a bare string can't drive that."""

    code: str
    message: str
    line_refs: Tuple[str, ...] = field(default_factory=tuple)


def parse_booked_at(raw: str | None) -> datetime | None:
    """Parses `booked_at` as extracted (ISO 8601, local time as printed).
    Shared with `tasks/receipt_tasks.py`'s persistence step so both agree on
    exactly what counts as a parseable date."""
    if not raw or not raw.strip():
        return None
    text = raw.strip()
    # Python's `datetime.fromisoformat` (3.11+) accepts a trailing "Z"
    # directly; kept as an explicit branch since we don't control the
    # runtime's exact minor version at deploy time.
    candidate = text[:-1] + "+00:00" if text.endswith("Z") else text
    try:
        return datetime.fromisoformat(candidate)
    except ValueError:
        return None


def _duplicate_line_refs(lines: List[ExtractedLine]) -> Tuple[str, ...]:
    """Identifies lines that look like the same purchase transcribed twice --
    the signature of a recap block (a summary re-listing lines already
    itemized) mistakenly turned into its own line entries. Grouped on
    (name, net_amount): two lines with the same name charging the same net
    amount are indistinguishable from a duplicate without more information,
    so every member of such a group is reported, not just the second one."""
    groups: Dict[Tuple[str, str], List[str]] = {}
    for line in lines:
        if line.net_amount is None or not line.name:
            continue
        key = (line.name.strip().lower(), str(line.net_amount))
        groups.setdefault(key, []).append(line.id)

    duplicate_refs: List[str] = []
    for refs in groups.values():
        if len(refs) > 1:
            duplicate_refs.extend(refs)
    return tuple(duplicate_refs)


def validate(extracted: ExtractedReceipt) -> List[ValidationError]:
    """Returns a list of reconcile failures, never raises. An empty list
    means the receipt is trustworthy enough to book as-is."""
    errors: List[ValidationError] = []
    lines = extracted.lines

    # --- Header sanity -------------------------------------------------
    currency = (extracted.currency or "").strip().upper()
    if not currency or currency not in ISO_4217_CODES:
        errors.append(
            ValidationError(
                BAD_CURRENCY,
                f"Currency {extracted.currency!r} is not a recognized ISO 4217 code.",
            )
        )

    if parse_booked_at(extracted.booked_at) is None:
        errors.append(
            ValidationError(
                BAD_DATE,
                f"booked_at {extracted.booked_at!r} could not be parsed as a date/time.",
            )
        )

    if extracted.printed_total is None or extracted.printed_total <= 0:
        errors.append(
            ValidationError(
                BAD_TOTAL,
                f"printed_total must be greater than 0, got {extracted.printed_total!r}.",
            )
        )

    # --- Per-line arithmetic --------------------------------------------
    # gross_amount - discount_amount != net_amount on any line. Not in the
    # spec's checklist, but the cheapest possible check, and it localises a
    # total_mismatch to the specific line that caused it.
    arithmetic_bad_refs: List[str] = []
    for line in lines:
        if line.net_amount is None:
            arithmetic_bad_refs.append(line.id)
            continue
        gross = line.gross_amount if line.gross_amount is not None else line.net_amount
        discount = line.discount_amount if line.discount_amount is not None else Decimal("0")
        if gross - discount != line.net_amount:
            arithmetic_bad_refs.append(line.id)
    if arithmetic_bad_refs:
        errors.append(
            ValidationError(
                LINE_ARITHMETIC,
                "gross_amount - discount_amount != net_amount on line(s): "
                + ", ".join(arithmetic_bad_refs),
                tuple(arithmetic_bad_refs),
            )
        )

    # --- Orphan deposits --------------------------------------------------
    item_ids = {line.id for line in lines if line.kind == "item"}
    orphan_refs = tuple(
        line.id
        for line in lines
        if line.kind == "deposit" and (not line.parent_id or line.parent_id not in item_ids)
    )
    if orphan_refs:
        errors.append(
            ValidationError(
                ORPHAN_DEPOSIT,
                "Deposit line(s) with no matching parent item line: " + ", ".join(orphan_refs),
                orphan_refs,
            )
        )

    # --- Totals reconcile, exactly, to the cent ---------------------------
    if extracted.printed_total is not None:
        missing_net_refs = tuple(line.id for line in lines if line.net_amount is None)
        net_sum = sum(
            (line.net_amount for line in lines if line.net_amount is not None),
            Decimal("0"),
        )
        if missing_net_refs or net_sum != extracted.printed_total:
            duplicate_refs = _duplicate_line_refs(lines)
            line_refs = missing_net_refs or duplicate_refs
            errors.append(
                ValidationError(
                    TOTAL_MISMATCH,
                    f"sum(net_amount)={net_sum} != printed_total={extracted.printed_total}",
                    line_refs,
                )
            )

    if extracted.printed_discount_total is not None:
        discount_sum = sum(
            (line.discount_amount or Decimal("0") for line in lines),
            Decimal("0"),
        )
        if discount_sum != extracted.printed_discount_total:
            discounted_refs = tuple(
                line.id for line in lines if (line.discount_amount or Decimal("0")) > 0
            )
            errors.append(
                ValidationError(
                    DISCOUNT_MISMATCH,
                    "sum(discount_amount)="
                    f"{discount_sum} != printed_discount_total="
                    f"{extracted.printed_discount_total}",
                    discounted_refs,
                )
            )

    return errors
