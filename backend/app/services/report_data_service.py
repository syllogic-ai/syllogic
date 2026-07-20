"""Builds the JSON payload consumed by the report newsletter email template.

Reuses the same Account/Transaction ORM models the dashboard reads from,
so report numbers match what the user sees in-app.
"""
from __future__ import annotations

import os
from datetime import datetime
from decimal import Decimal
from typing import Optional
from uuid import UUID

from sqlalchemy import and_, func
from sqlalchemy.orm import Session, joinedload

from app.models import Account, Report, Transaction
from app.services.report_horizon import horizon_start, period_label

_DIRECTION_LABELS = {
    "ALL": "transactions",
    "EXPENSE": "expenses",
    "INCOME": "income",
    "INFLOW": "inflows",
    "OUTFLOW": "outflows",
}

# transaction_type on Transaction is "debit" or "credit".
# EXPENSE/OUTFLOW == debit, INCOME/INFLOW == credit, ALL == both.
_DIRECTION_TYPES = {
    "ALL": ("debit", "credit"),
    "EXPENSE": ("debit",),
    "OUTFLOW": ("debit",),
    "INCOME": ("credit",),
    "INFLOW": ("credit",),
}


def build_report_payload(db: Session, report: Report) -> dict:
    accounts = _fetch_accounts(db, report)
    transactions = _fetch_transactions(db, report)
    functional_currency = (report.user.functional_currency if report.user else None) or "EUR"

    return {
        "report_name": report.name,
        # Trailing "Z" so the frontend's `new Date(generatedAt)` parses this
        # as UTC rather than the worker container's local timezone (which
        # would silently shift the displayed date/time otherwise).
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "period_label": period_label(report.frequency),
        "total_balance": _total_balance(db, report),
        "total_currency": functional_currency,
        "accounts": accounts,
        "transactions": transactions,
    }


def _fetch_accounts(db: Session, report: Report) -> list[dict]:
    if not report.account_ids:
        return []
    account_uuids = [UUID(a) for a in report.account_ids]
    rows = (
        db.query(Account)
        # Eager-load so rendering N accounts does not fire N logo queries.
        .options(joinedload(Account.logo))
        .filter(Account.user_id == report.user_id, Account.id.in_(account_uuids))
        .all()
    )
    functional_currency = (report.user.functional_currency if report.user else None) or "EUR"
    # logo_url on CompanyLogo is a relative path ("/uploads/logos/x.png"); mail
    # clients need it absolute.
    base_url = (os.environ.get("FRONTEND_URL") or os.environ.get("APP_URL", "")).rstrip("/")

    def _logo_url(a: Account) -> str | None:
        logo = a.logo
        if not logo or not logo.logo_url or logo.status != "found":
            return None
        return f"{base_url}{logo.logo_url}"

    def _balance_and_currency(a: Account) -> tuple[str, str]:
        if a.functional_balance is not None:
            # functional_balance is already converted to the user's
            # functional currency, so it must be labeled with that
            # currency, not the account's native currency.
            return str(a.functional_balance), functional_currency
        return str(a.balance_available or 0), a.currency or "EUR"

    accounts = []
    for a in rows:
        balance, currency = _balance_and_currency(a)
        accounts.append({
            "name": a.name,
            "institution": a.institution,
            "balance": balance,
            "currency": currency,
            "logo_url": _logo_url(a),
        })
    return accounts


def _total_balance(db: Session, report: Report) -> Optional[str]:
    """Sum of the selected accounts, or None if they are not all convertible.

    Only functional_balance is expressed in a single currency. Summing an
    account that only has a native balance would produce a confidently wrong
    number, so the total is withheld instead.
    """
    if not report.account_ids:
        return None
    account_uuids = [UUID(a) for a in report.account_ids]
    rows = (
        db.query(Account)
        .filter(Account.user_id == report.user_id, Account.id.in_(account_uuids))
        .all()
    )
    if not rows or any(a.functional_balance is None for a in rows):
        return None
    return str(sum((a.functional_balance for a in rows), Decimal("0")).quantize(Decimal("0.01")))


def _fetch_transactions(db: Session, report: Report) -> dict:
    types = _DIRECTION_TYPES.get(report.transaction_direction, ("debit", "credit"))
    # Both TOP_N and RECENT are scoped to the report's own cadence, so a weekly
    # digest reports on the last seven days rather than on all of history.
    window_start = horizon_start(report.frequency, datetime.utcnow())
    query = db.query(Transaction).filter(
        Transaction.user_id == report.user_id,
        Transaction.transaction_type.in_(types),
        Transaction.booked_at >= window_start,
    )
    if report.account_ids:
        account_uuids = [UUID(a) for a in report.account_ids]
        query = query.filter(Transaction.account_id.in_(account_uuids))

    if report.transaction_mode == "RECENT":
        query = query.order_by(Transaction.booked_at.desc())
    elif types == ("debit", "credit"):
        # direction == ALL: debits are negative, credits are positive, so
        # neither .asc() nor .desc() alone gives "biggest transactions
        # first" — order by absolute magnitude instead.
        query = query.order_by(func.abs(Transaction.amount).desc())
    else:  # TOP_N — order by absolute amount descending
        query = query.order_by(Transaction.amount.desc() if types == ("credit",) else Transaction.amount.asc())

    rows = query.limit(report.transaction_count).all()

    direction_word = _DIRECTION_LABELS.get(report.transaction_direction, "transactions")
    mode_label = (
        f"Last {report.transaction_count} transactions"
        if report.transaction_mode == "RECENT"
        else f"Top {report.transaction_count} {direction_word}"
    )

    items = [
        {
            "description": t.merchant or t.description or "Transaction",
            "category": None,
            "date": t.booked_at.date().isoformat(),
            "amount": str(abs(t.amount)),
            "currency": t.currency or "EUR",
            "direction": "out" if t.transaction_type == "debit" else "in",
        }
        for t in rows
    ]

    return {"mode_label": mode_label, "items": items}
