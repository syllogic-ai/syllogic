"""Reconciles bank rows with the receipt splits that already cover them.

A photographed receipt is booked as one `Transaction` per category group
(`app/routes/receipt_scan.py`, the confirm endpoint). If the card that paid
for it also syncs, the bank reports the same purchase as a single charge and
the ledger carries it twice.

`supersede_receipt_duplicates` runs at the end of the post-import pipeline,
on the rows that import just produced. Where
`recurring_transaction_dedupe.py` lets the *bank* row win -- a placeholder
carries less information than the real charge -- receipts invert that: the
splits carry the per-category detail, which is the whole reason the user
photographed the receipt. So the bank row is the side that loses. It is kept
(balances need it) with `include_in_analytics = False`, and gets
`receipt_scan_id` set so the link is inspectable; the splits keep their own
`include_in_analytics` untouched.

Balance stays correct because the bank row is still there. Category reports
stay correct because only the splits are counted.

Matching reuses the recurring tolerances -- `MATCH_WINDOW_DAYS` and
`AMOUNT_TOLERANCE_PERCENT` -- rather than tighter receipt-specific ones. A
receipt total is exact where a recurring amount is an estimate, so tightening
is defensible later, but one reconciliation convention in the codebase beats
two tuned ones.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal
from typing import Collection, Iterable, Optional, Sequence
from uuid import UUID

from sqlalchemy import func as sa_func
from sqlalchemy.orm import Session

from app.models import ReceiptLineItem, ReceiptScan, Transaction
from app.services.recurring_transaction_generator import (
    AMOUNT_TOLERANCE_PERCENT,
    MATCH_WINDOW_DAYS,
    amounts_match,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ReceiptMatch:
    """The receipt one bank row turned out to duplicate.

    `splits` is the whole group, not one row: a receipt books one
    transaction per category, and it is their sum that the single bank
    charge has to line up with.
    """

    receipt_scan_id: UUID
    splits: tuple[Transaction, ...]
    total: Decimal


def _normalize_merchant(name: Optional[str]) -> str:
    return " ".join((name or "").lower().split())


def _merchant_matches(bank_names: Sequence[Optional[str]], scan_merchant: Optional[str]) -> bool:
    """True when the bank row names the merchant the receipt came from.

    Bank feeds and printed receipts rarely agree on spelling -- "RIMI LATVIA
    SIA" against "Rimi" -- so this goes no further than containment in
    either direction, over whichever of the bank row's name fields are
    populated. A scan with no merchant name never matches: the only evidence
    left would be the amount, and an amount alone is not enough to retire a
    row from analytics.
    """
    needle = _normalize_merchant(scan_merchant)
    if not needle:
        return False
    for name in bank_names:
        haystack = _normalize_merchant(name)
        if not haystack:
            continue
        if needle in haystack or haystack in needle:
            return True
    return False


def _scan_is_already_reconciled(db: Session, receipt_scan_id) -> bool:
    """True when some bank row has already been reconciled against this scan.

    Demotion writes `receipt_scan_id` onto the bank row, which is what makes
    the link inspectable -- and also what stops that column alone from
    telling a bank row apart from a split. The splits are the rows a
    `ReceiptLineItem` of the scan points at; anything else carrying the scan
    id is a bank row an earlier run already claimed, and one receipt does
    not excuse two charges.
    """
    split_ids = db.query(ReceiptLineItem.booked_transaction_id).filter(
        ReceiptLineItem.receipt_scan_id == receipt_scan_id,
        ReceiptLineItem.booked_transaction_id.isnot(None),
    )
    return (
        db.query(Transaction.id)
        .filter(
            Transaction.receipt_scan_id == receipt_scan_id,
            Transaction.id.notin_(split_ids),
        )
        .first()
        is not None
    )


def find_receipt_splits(
    db: Session,
    *,
    user_id: str,
    account_id,
    booked_at,
    amount,
    merchant_names: Sequence[Optional[str]],
    window_days: int = MATCH_WINDOW_DAYS,
    exclude_scan_ids: Collection[UUID] = (),
) -> Optional[ReceiptMatch]:
    """Find the receipt splits an incoming bank row duplicates.

    Candidates are the booked splits on the same account inside the date
    window; they are grouped by scan and the group's summed magnitude is
    compared against the bank row's, so a receipt split across four
    categories still matches the one charge that paid for it.

    `exclude_scan_ids` holds scans a caller has already spent on an earlier
    bank row in the same sweep -- two identical charges in one week must not
    both hide behind a single receipt.
    """
    target_date = booked_at.date() if hasattr(booked_at, "date") else booked_at
    candidates = (
        db.query(Transaction)
        # A split is a row some `ReceiptLineItem` was booked into. Filtering
        # on `receipt_scan_id` alone would also pick up bank rows a previous
        # run demoted, since demotion sets that same column.
        .join(ReceiptLineItem, ReceiptLineItem.booked_transaction_id == Transaction.id)
        .filter(
            Transaction.user_id == user_id,
            Transaction.account_id == account_id,
            Transaction.receipt_scan_id.isnot(None),
            sa_func.date(Transaction.booked_at) >= target_date - timedelta(days=window_days),
            sa_func.date(Transaction.booked_at) <= target_date + timedelta(days=window_days),
        )
        .order_by(Transaction.booked_at)
        .all()
    )

    # The join yields a split once per line item booked into it, so the same
    # row comes back several times; deduplicated here rather than with
    # SELECT DISTINCT, which would have to compare every selected column.
    by_scan: dict[UUID, list[Transaction]] = {}
    seen: set[UUID] = set()
    for split in candidates:
        if split.receipt_scan_id in exclude_scan_ids or split.id in seen:
            continue
        seen.add(split.id)
        by_scan.setdefault(split.receipt_scan_id, []).append(split)
    if not by_scan:
        return None

    merchant_by_scan = dict(
        db.query(ReceiptScan.id, ReceiptScan.merchant_name)
        .filter(ReceiptScan.id.in_(list(by_scan)))
        .all()
    )

    for receipt_scan_id, splits in by_scan.items():
        if not _merchant_matches(merchant_names, merchant_by_scan.get(receipt_scan_id)):
            continue
        total = sum((abs(Decimal(split.amount)) for split in splits), Decimal("0"))
        if amounts_match(total, Decimal(str(amount)), AMOUNT_TOLERANCE_PERCENT):
            return ReceiptMatch(
                receipt_scan_id=receipt_scan_id,
                splits=tuple(splits),
                total=total,
            )
    return None


def supersede_receipt_duplicates(
    db: Session,
    user_id: str,
    transaction_ids: Optional[Iterable[str]] = None,
    window_days: int = MATCH_WINDOW_DAYS,
    commit: bool = True,
) -> dict:
    """Drop bank rows that receipt splits already account for.

    `transaction_ids` narrows the scan to rows a just-finished import
    produced; omit it to sweep every analytics-visible row of the user.

    Returns the number of demoted rows plus the accounts they sat on. Unlike
    the recurring case the caller has nothing to recompute from that:
    `AccountBalanceService` sums `Transaction.amount` without consulting
    `include_in_analytics`, and the row itself is still there, so no balance
    this pipeline already computed has moved. The account ids are there to
    be logged and inspected.
    """
    query = db.query(Transaction).filter(
        Transaction.user_id == user_id,
        # Receipt splits carry a scan id, and so does a bank row an earlier
        # run already demoted; neither is an incoming charge to reconcile.
        Transaction.receipt_scan_id.is_(None),
        # Generated placeholders are not bank rows. The recurring reconcile
        # runs immediately before this one and owns them.
        Transaction.auto_generated.is_(False),
        # Already out of analytics means some other reconciliation -- an
        # internal transfer, a user's own edit -- got here first.
        Transaction.include_in_analytics.is_(True),
    )
    if transaction_ids is not None:
        ids = list(transaction_ids)
        if not ids:
            return {"demoted": 0, "account_ids": []}
        query = query.filter(Transaction.id.in_(ids))

    bank_rows = query.order_by(Transaction.booked_at).all()
    if not bank_rows:
        return {"demoted": 0, "account_ids": []}

    demoted = 0
    claimed_scan_ids: set[UUID] = set()
    touched_accounts: set[str] = set()

    for bank_row in bank_rows:
        match = find_receipt_splits(
            db,
            user_id=user_id,
            account_id=bank_row.account_id,
            booked_at=bank_row.booked_at,
            amount=bank_row.amount,
            merchant_names=(bank_row.merchant, bank_row.creditor, bank_row.description),
            window_days=window_days,
            exclude_scan_ids=claimed_scan_ids,
        )
        if match is None:
            continue
        if _scan_is_already_reconciled(db, match.receipt_scan_id):
            continue

        claimed_scan_ids.add(match.receipt_scan_id)
        touched_accounts.add(str(bank_row.account_id))
        # The splits keep their own `include_in_analytics`: they are the
        # categorized side, and the categories are the point.
        bank_row.include_in_analytics = False
        bank_row.receipt_scan_id = match.receipt_scan_id
        demoted += 1
        logger.info(
            "[RECEIPT] Bank row %s excluded from analytics; receipt scan %s already "
            "covers it across %d split(s) totalling %s",
            bank_row.id,
            match.receipt_scan_id,
            len(match.splits),
            match.total,
        )

    if commit and demoted:
        db.commit()

    return {"demoted": demoted, "account_ids": sorted(touched_accounts)}
