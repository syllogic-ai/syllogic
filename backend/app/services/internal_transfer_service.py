"""Detect and manage internal transfers between the user's synced accounts
and their manually-registered pocket accounts.

Matching is done by counterparty IBAN blind index: transactions whose
`counterparty_iban_hash` matches a manual account's `iban_hash` are linked to
that pocket, and a mirror transaction is created on the pocket side.
"""
from __future__ import annotations

import logging
from typing import Dict, List, Optional
from uuid import UUID

from sqlalchemy.orm import Session, joinedload

from app.models import Account, Category, InternalTransfer, Transaction

logger = logging.getLogger(__name__)


class InternalTransferService:
    """Service for detecting and managing internal transfers.

    Constructor intentionally mirrors the minimal convention used by other
    services: ``(db, user_id)``. No feature flags.
    """

    def __init__(self, db: Session, user_id: str):
        self.db = db
        self.user_id = user_id

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _load_pocket_map(self) -> Dict[str, Account]:
        """Return ``{iban_hash: pocket_account}`` for this user's active manual
        accounts that have an IBAN hash recorded.
        """
        pockets = (
            self.db.query(Account)
            .filter(
                Account.user_id == self.user_id,
                Account.provider == "manual",
                Account.iban_hash.isnot(None),
                Account.is_active.is_(True),
            )
            .all()
        )
        return {p.iban_hash: p for p in pockets}

    def _resolve_transfer_category_id(self) -> Optional[UUID]:
        cat = (
            self.db.query(Category)
            .filter(
                Category.user_id == self.user_id,
                Category.category_type == "transfer",
            )
            .order_by(Category.is_system.desc(), Category.created_at.asc())
            .first()
        )
        return cat.id if cat else None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def detect_for_transactions(self, transaction_ids: List[UUID]) -> int:
        """Inspect the given transactions and, for each whose counterparty IBAN
        matches one of the user's pocket accounts, create a mirror transaction
        on the pocket and an ``internal_transfers`` link row.

        Returns the number of transfers detected (newly linked).
        """
        if not transaction_ids:
            return 0

        pocket_map = self._load_pocket_map()
        if not pocket_map:
            return 0

        # Eager-load the source account so we can build a descriptive mirror
        # description without extra queries per-source.
        sources = (
            self.db.query(Transaction)
            .options(joinedload(Transaction.account))
            .filter(
                Transaction.id.in_(transaction_ids),
                Transaction.user_id == self.user_id,
                Transaction.counterparty_iban_hash.isnot(None),
                Transaction.internal_transfer_id.is_(None),
            )
            .all()
        )

        transfer_category_id = self._resolve_transfer_category_id()
        if transfer_category_id is None:
            logger.warning(
                "[INTERNAL_TRANSFER] No Transfer category found for user %s — "
                "mirror transactions will be created without a system category",
                self.user_id,
            )
        detected = 0

        for src in sources:
            pocket = pocket_map.get(src.counterparty_iban_hash)
            if pocket is None or pocket.id == src.account_id:
                continue

            mirror_amount = -src.amount
            mirror_functional = (
                -src.functional_amount if src.functional_amount is not None else None
            )

            src_account_name = getattr(src.account, "name", None) or "account"
            description = (
                f"Transfer from {src_account_name}"
                if mirror_amount > 0
                else f"Transfer to {src_account_name}"
            )

            mirror = Transaction(
                user_id=self.user_id,
                account_id=pocket.id,
                external_id=f"mirror-{src.id}",
                amount=mirror_amount,
                currency=src.currency,
                functional_amount=mirror_functional,
                description=description,
                merchant=src_account_name,
                booked_at=src.booked_at,
                transaction_type="credit" if mirror_amount > 0 else "debit",
                category_system_id=transfer_category_id,
                include_in_analytics=False,
            )
            self.db.add(mirror)
            self.db.flush()  # assigns mirror.id

            link = InternalTransfer(
                user_id=self.user_id,
                source_txn_id=src.id,
                mirror_txn_id=mirror.id,
                source_account_id=src.account_id,
                pocket_account_id=pocket.id,
                amount=abs(src.amount),
                currency=src.currency,
            )
            self.db.add(link)
            self.db.flush()  # assigns link.id (server_default gen_random_uuid())

            src.include_in_analytics = False
            src.internal_transfer_id = link.id
            # Detection is authoritative: overwrite any prior LLM-assigned
            # system category with Transfer. We only defer to the user's
            # explicit category_id override (left untouched below).
            if transfer_category_id and src.category_id is None:
                src.category_system_id = transfer_category_id

            detected += 1

        if detected:
            self.db.commit()

        logger.info(
            "[INTERNAL_TRANSFER] Detected %d transfer(s) for user %s",
            detected,
            self.user_id,
        )
        return detected

    def unlink(self, internal_transfer_id: UUID) -> None:
        """Reverse a single detection: restore the source, delete the mirror,
        and delete the ``internal_transfers`` row.
        """
        link = (
            self.db.query(InternalTransfer)
            .filter(
                InternalTransfer.id == internal_transfer_id,
                InternalTransfer.user_id == self.user_id,
            )
            .one_or_none()
        )
        if link is None:
            return

        src = (
            self.db.query(Transaction)
            .filter(Transaction.id == link.source_txn_id)
            .one_or_none()
        )
        if src is not None:
            src.include_in_analytics = True
            src.internal_transfer_id = None

        if link.mirror_txn_id is not None:
            mirror = (
                self.db.query(Transaction)
                .filter(Transaction.id == link.mirror_txn_id)
                .one_or_none()
            )
            if mirror is not None:
                self.db.delete(mirror)
            else:
                logger.warning(
                    "[INTERNAL_TRANSFER] Mirror %s for link %s already gone — "
                    "link was pointing at a deleted transaction",
                    link.mirror_txn_id,
                    link.id,
                )

        # Flush deletion of the mirror BEFORE deleting the link so the
        # transactions.internal_transfer_id -> internal_transfers.id FK
        # (ON DELETE SET NULL) does not become ambiguous under some drivers.
        self.db.flush()
        self.db.delete(link)
        self.db.commit()

    def unlink_all_for_pocket(self, pocket_account_id: UUID) -> int:
        """Remove all ``internal_transfers`` rows that point at the given pocket,
        restoring each source transaction's analytics flag.

        **IMPORTANT — call contract:** this is the pre-delete cleanup hook. The
        caller MUST delete the pocket account itself immediately after a
        successful return. Mirror transactions (the ones on the pocket side)
        are NOT deleted here — they depend on the ``ON DELETE CASCADE`` from
        ``transactions.account_id`` when the pocket row is removed. If you call
        this method and do NOT delete the pocket, orphan mirror transactions
        will remain on the pocket account with no linking ``internal_transfers``
        row, and analytics will misreport the pocket's activity.

        Returns the number of links removed.
        """
        links = (
            self.db.query(InternalTransfer)
            .filter(
                InternalTransfer.pocket_account_id == pocket_account_id,
                InternalTransfer.user_id == self.user_id,
            )
            .all()
        )
        count = 0
        for link in links:
            src = (
                self.db.query(Transaction)
                .filter(Transaction.id == link.source_txn_id)
                .one_or_none()
            )
            if src is not None:
                src.include_in_analytics = True
                src.internal_transfer_id = None
            self.db.delete(link)
            count += 1

        if count:
            self.db.commit()
        return count
