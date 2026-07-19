"""Builds the JSON payload consumed by the report newsletter email template.

Reuses the same Account/Transaction ORM models the dashboard reads from,
so report numbers match what the user sees in-app.
"""
from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import and_, func
from sqlalchemy.orm import Session

from app.models import Account, Report, Transaction

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

    return {
        "report_name": report.name,
        "generated_at": datetime.utcnow().isoformat(),
        "accounts": accounts,
        "transactions": transactions,
    }


def _fetch_accounts(db: Session, report: Report) -> list[dict]:
    if not report.account_ids:
        return []
    account_uuids = [UUID(a) for a in report.account_ids]
    rows = (
        db.query(Account)
        .filter(Account.user_id == report.user_id, Account.id.in_(account_uuids))
        .all()
    )
    functional_currency = (report.user.functional_currency if report.user else None) or "EUR"

    def _balance_and_currency(a: Account) -> tuple[str, str]:
        if a.functional_balance is not None:
            # functional_balance is already converted to the user's
            # functional currency, so it must be labeled with that
            # currency, not the account's native currency.
            return str(a.functional_balance), functional_currency
        return str(a.balance_available or 0), a.currency or "EUR"

    return [
        {
            "name": a.name,
            "institution": a.institution,
            "balance": _balance_and_currency(a)[0],
            "currency": _balance_and_currency(a)[1],
        }
        for a in rows
    ]


def _fetch_transactions(db: Session, report: Report) -> dict:
    types = _DIRECTION_TYPES.get(report.transaction_direction, ("debit", "credit"))
    query = db.query(Transaction).filter(
        Transaction.user_id == report.user_id,
        Transaction.transaction_type.in_(types),
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
