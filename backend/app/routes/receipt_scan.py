"""
API endpoints for receipt scanning: upload -> enqueue extraction (async,
Celery) -> poll -> user-reviewed confirm that resolves the receipt into one
or more Transaction rows, grouped by category (Phase 6 -- see
docs/specs/receipt-ingestion-implementation.md 6.2 and
docs/specs/receipt-ingestion.md Part 6.2).

Extraction itself (`RECEIPT_EXTRACTION_ENGINE=vision|tesseract`, vision under
a strict JSON schema, tesseract as the rollback path) runs off the request
thread in `tasks.receipt_tasks.extract_receipt_task` -- see
docs/specs/receipt-ingestion-implementation.md 4.3/4.4 and
docs/specs/receipt-ingestion.md Part 4.1. This module only ever does the
storage write and the enqueue; it does not call a model.

Resolve (grouping lines by category, the merchant/threshold collapse, and
the printed_total checkpoint) is `app.services.receipt_resolve` -- pure
policy code, never reimplemented here or in the frontend. This module's job
is: apply the user's per-line category edits, call `resolve`, refuse a
submission that doesn't match what `resolve` computes, and book exactly
that.
"""

import hashlib
import logging
import re
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import Response
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import get_db
from app.db_helpers import get_user_id
from app.models import Account, Category, ReceiptLineItem, ReceiptScan, Transaction
from app.schemas import (
    ReceiptConfirmResponse,
    ReceiptLineCorrectionRequest,
    ReceiptLineItemSchema,
    ReceiptResolvePreviewRequest,
    ReceiptResolvePreviewResponse,
    ReceiptResolvedGroupSchema,
    ReceiptScanConfirmRequest,
    ReceiptScanExtractResponse,
    ReceiptValidationErrorSchema,
    TransactionWithDetails,
)
from app.security.data_encryption import decrypt_with_fallback
from app.services import app_settings, receipt_resolve, receipt_storage, receipt_validate
from app.services.receipt_extract import ExtractedLine, ExtractedReceipt
from app.services.receipt_resolve import ResolveConfig, ResolveError, TransactionGroup

logger = logging.getLogger(__name__)

router = APIRouter()

# Raw receipt photos shouldn't need to exceed this; guards against an
# oversized upload tying up the request thread with a giant body it's about
# to hand straight to storage.
MAX_IMAGE_BYTES = 10 * 1024 * 1024

# Header fields copied verbatim onto a new scan when its upload's
# `file_sha256` matches an already-`processed` scan for the same user (spec
# 6.4). Deliberately excludes `id`/`account_id`/`user_id`/`file_path*` (the
# new scan keeps its own) and `status`/`completed_at` (set explicitly by the
# caller, since the new scan's line items haven't been re-categorized yet).
_CACHEABLE_HEADER_FIELDS = (
    "merchant_name",
    "merchant_legal_name",
    "merchant_address",
    "receipt_no",
    "fiscal_code",
    "vat_id",
    "currency",
    "payment_method",
    "card_last4",
    "printed_total",
    "receipt_total",
    "printed_discount_total",
    "extraction_model",
    "receipt_date",
    "validation_errors",
)


def _receipt_scan_response(receipt_scan: ReceiptScan) -> ReceiptScanExtractResponse:
    """Shared response builder for the POST (right after enqueue, so `items`
    and `validation_errors` are necessarily empty -- extraction hasn't run
    yet -- unless a cache hit copied them on synchronously, spec 6.4) and
    the GET (with whatever the Celery task has persisted so far)."""
    validation_errors = [
        ReceiptValidationErrorSchema(
            code=error.get("code", ""),
            message=error.get("message", ""),
            line_refs=list(error.get("line_refs") or []),
        )
        for error in (receipt_scan.validation_errors or [])
    ]

    items = [
        ReceiptLineItemSchema(
            id=line.id,
            line_ref=line.line_ref,
            position=line.position,
            raw_text=line.raw_text,
            name=line.name,
            quantity=line.quantity,
            gross_amount=line.gross_amount,
            discount_amount=line.discount_amount,
            net_amount=line.net_amount,
            kind=line.kind,
            parent_line_ref=line.parent_line_ref,
            category_id=line.category_id,
            category_confidence=line.category_confidence,
            category_reason=line.category_reason,
            user_edited=line.user_edited,
        )
        for line in receipt_scan.line_items
    ]

    return ReceiptScanExtractResponse(
        receipt_scan_id=receipt_scan.id,
        status=receipt_scan.status or "pending",
        merchant_name=receipt_scan.merchant_name,
        receipt_date=receipt_scan.receipt_date,
        receipt_total=receipt_scan.receipt_total,
        currency=receipt_scan.currency,
        items=items,
        validation_errors=validation_errors,
        error_message=receipt_scan.error_message,
    )


def _find_extraction_cache_source(
    db: Session, user_id: str, file_sha256: str
) -> Optional[ReceiptScan]:
    """Spec 6.4: a `processed` scan for the same user with the same
    `file_sha256` (backed by the partial index from plan 2.2,
    `idx_receipt_scans_sha256` / `ix_receipt_scans_user_id_file_sha256`).
    Scoped to `user_id` deliberately -- two different users uploading the
    same receipt photo (a shared purchase, a forwarded image) must never
    let one user's extraction satisfy another's request."""
    return (
        db.query(ReceiptScan)
        .filter(
            ReceiptScan.user_id == user_id,
            ReceiptScan.file_sha256 == file_sha256,
            ReceiptScan.status == "processed",
        )
        .order_by(ReceiptScan.created_at.desc())
        .first()
    )


def _copy_cached_extraction(db: Session, source: ReceiptScan, target: ReceiptScan) -> None:
    """Copies stage 1's output (header fields + line items, minus any
    category assignment) from `source` onto `target`. Stage 2 always
    re-runs against the copy rather than being copied too, so results stay
    current with any category rule edited since `source` was extracted
    (spec 6.4)."""
    for field in _CACHEABLE_HEADER_FIELDS:
        setattr(target, field, getattr(source, field))
    target.status = "processed"

    for line in sorted(source.line_items, key=lambda item: item.position):
        db.add(
            ReceiptLineItem(
                receipt_scan_id=target.id,
                line_ref=line.line_ref,
                position=line.position,
                raw_text=line.raw_text,
                name=line.name,
                quantity=line.quantity,
                gross_amount=line.gross_amount,
                discount_amount=line.discount_amount,
                net_amount=line.net_amount,
                kind=line.kind,
                parent_line_ref=line.parent_line_ref,
                # category_id/category_confidence/category_reason
                # intentionally not copied -- stage 2 re-runs.
            )
        )


@router.post("/extract", response_model=ReceiptScanExtractResponse, status_code=202)
async def extract_receipt(
    request: Request,
    account_id: UUID = Query(...),
    content_type: str = Query("image/jpeg"),
    user_id: str | None = None,
    db: Session = Depends(get_db),
):
    """Stores the uploaded receipt image and enqueues extraction; does not
    wait for it. The image is the raw request body
    (`application/octet-stream`), not JSON/base64 -- see
    docs/specs/receipt-ingestion-implementation.md 1.1 for why: the auth
    middleware already buffers the whole body to sign it, so base64-in-JSON
    would buffer it a second time for nothing, and the query string is
    already inside that same signature.

    Returns 202. Ordinarily `status="pending"` with no items -- poll
    `GET /{receipt_scan_id}` for the result (spec 4.4/4.5). On a
    `file_sha256` cache hit against an already-processed scan of this same
    user (spec 6.4), stage 1 is skipped, the header/lines are copied
    synchronously, and only stage 2 (categorization) is enqueued -- the
    response already reflects `status="processed"` and the copied items."""
    resolved_user_id = get_user_id(user_id)

    account = (
        db.query(Account)
        .filter(Account.id == account_id, Account.user_id == resolved_user_id)
        .first()
    )
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")

    image_bytes = await request.body()

    if not image_bytes:
        raise HTTPException(status_code=400, detail="Empty file")
    if len(image_bytes) > MAX_IMAGE_BYTES:
        raise HTTPException(status_code=413, detail="Receipt image is too large")

    stored = receipt_storage.put(resolved_user_id, image_bytes, content_type)

    cache_source = _find_extraction_cache_source(db, resolved_user_id, stored.sha256)

    receipt_scan = ReceiptScan(
        user_id=resolved_user_id,
        account_id=account_id,
        status="pending",
        file_path=stored.file_path,
        file_path_ciphertext=stored.file_path_ciphertext,
        file_sha256=stored.sha256,
    )
    db.add(receipt_scan)
    db.commit()
    db.refresh(receipt_scan)

    # Imported lazily (matching every other route in this codebase that
    # enqueues a Celery task, e.g. routes/csv_import.py) rather than at
    # module load time.
    from tasks.receipt_tasks import categorize_receipt_task, extract_receipt_task

    if cache_source is not None:
        _copy_cached_extraction(db, cache_source, receipt_scan)
        db.commit()
        db.refresh(receipt_scan)
        # Commit before enqueueing (see below) -- same reasoning, just for
        # stage 2 instead of stage 1.
        categorize_receipt_task.delay(str(receipt_scan.id))
    else:
        # Commit before enqueueing: with a warm worker and broker, the task
        # can start executing almost immediately, and it must always find
        # the row it was handed (same reasoning as tasks/report_tasks.py's
        # check_due_reports -- enqueueing before the commit lands is a
        # data-loss race).
        extract_receipt_task.delay(str(receipt_scan.id))

    return _receipt_scan_response(receipt_scan)


@router.get("/{receipt_scan_id}", response_model=ReceiptScanExtractResponse)
def get_receipt_scan(
    receipt_scan_id: UUID,
    user_id: str | None = None,
    db: Session = Depends(get_db),
):
    resolved_user_id = get_user_id(user_id)
    receipt_scan = (
        db.query(ReceiptScan)
        .filter(ReceiptScan.id == receipt_scan_id, ReceiptScan.user_id == resolved_user_id)
        .first()
    )
    if not receipt_scan:
        raise HTTPException(status_code=404, detail="Receipt scan not found")

    return _receipt_scan_response(receipt_scan)


@router.get("/{receipt_scan_id}/image")
def get_receipt_scan_image(
    receipt_scan_id: UUID,
    user_id: str | None = None,
    db: Session = Depends(get_db),
):
    """Streams the stored receipt photo back to its owner. The review UI
    needs this to show a mismatch against the photo (spec 1.2's
    `needs_review` state); without it there is nothing to display."""
    resolved_user_id = get_user_id(user_id)
    receipt_scan = (
        db.query(ReceiptScan)
        .filter(ReceiptScan.id == receipt_scan_id, ReceiptScan.user_id == resolved_user_id)
        .first()
    )
    if not receipt_scan:
        raise HTTPException(status_code=404, detail="Receipt scan not found")

    file_path = decrypt_with_fallback(receipt_scan.file_path_ciphertext, receipt_scan.file_path)
    if not file_path:
        raise HTTPException(status_code=404, detail="Receipt image not found")

    try:
        data = receipt_storage.get(file_path)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Receipt image not found")

    return Response(content=data, media_type=receipt_storage.content_type_for_path(file_path))


def _parse_uuid(value: str | None) -> Optional[UUID]:
    if not value:
        return None
    try:
        return UUID(str(value))
    except ValueError:
        return None


def _load_resolve_config(db: Session) -> ResolveConfig:
    """Builds `receipt_resolve.ResolveConfig` from `app_settings` -- database
    override, then env, then default, per setting (spec 6.1;
    `app_settings.get_effective_receipt_resolve_config` does the actual
    resolution, following `get_effective_llm_model`'s pattern)."""
    raw = app_settings.get_effective_receipt_resolve_config(db)
    return ResolveConfig(
        grocery_merchants=frozenset(raw["grocery_merchants"]),
        grocery_category_id=_parse_uuid(raw["grocery_category_id"]),
        treat_split_threshold=raw["treat_split_threshold"],
    )


class _WorkingLine:
    """The minimal `receipt_resolve.LineForResolve` shape, used by the
    `/resolve` preview endpoint to apply not-yet-saved category overrides
    without mutating the real `ReceiptLineItem` rows."""

    __slots__ = ("line_ref", "category_id", "net_amount")

    def __init__(self, line_ref: str, category_id: Optional[UUID], net_amount: Decimal):
        self.line_ref = line_ref
        self.category_id = category_id
        self.net_amount = net_amount


def _category_names_for(db: Session, user_id: str, category_ids: set) -> dict:
    category_ids = {cid for cid in category_ids if cid}
    if not category_ids:
        return {}
    found = (
        db.query(Category.id, Category.name)
        .filter(Category.id.in_(category_ids), Category.user_id == user_id)
        .all()
    )
    return {row[0]: row[1] for row in found}


def _groups_to_schema(groups: list[TransactionGroup], category_names: dict):
    return [
        ReceiptResolvedGroupSchema(
            category_id=group.category_id,
            category_name=category_names.get(group.category_id) if group.category_id else None,
            amount=group.amount,
            line_refs=list(group.line_refs),
        )
        for group in groups
    ]


@router.post("/{receipt_scan_id}/resolve", response_model=ReceiptResolvePreviewResponse)
def preview_receipt_scan_resolve(
    receipt_scan_id: UUID,
    request: ReceiptResolvePreviewRequest,
    user_id: str | None = None,
    db: Session = Depends(get_db),
):
    """Stateless preview of stage 3 (spec 6.1): the raw per-category
    grouping side by side with the policy-applied (collapsed) grouping the
    confirm endpoint would actually book, given the currently-persisted
    line items plus any not-yet-saved category edits in `overrides`. Never
    writes anything. Exists so the review UI can show "collapsed vs
    uncollapsed" (spec 6.2 -- "genuinely the user's call") by calling this
    on every category edit, instead of reimplementing the collapse policy
    in TypeScript."""
    resolved_user_id = get_user_id(user_id)

    receipt_scan = (
        db.query(ReceiptScan)
        .filter(ReceiptScan.id == receipt_scan_id, ReceiptScan.user_id == resolved_user_id)
        .first()
    )
    if not receipt_scan:
        raise HTTPException(status_code=404, detail="Receipt scan not found")

    lines = (
        db.query(ReceiptLineItem)
        .filter(ReceiptLineItem.receipt_scan_id == receipt_scan.id)
        .order_by(ReceiptLineItem.position)
        .all()
    )
    if not lines:
        raise HTTPException(status_code=400, detail="Receipt scan has no line items")

    overrides = {o.line_ref: o.category_id for o in request.overrides}
    working_lines = [
        _WorkingLine(
            line_ref=line.line_ref,
            category_id=overrides.get(line.line_ref, line.category_id),
            net_amount=line.net_amount if line.net_amount is not None else Decimal("0"),
        )
        for line in lines
    ]

    category_names = _category_names_for(
        db, resolved_user_id, {wl.category_id for wl in working_lines}
    )

    uncollapsed = receipt_resolve.group_and_sum(working_lines)

    config = _load_resolve_config(db)
    try:
        resolved = receipt_resolve.resolve(receipt_scan, working_lines, config)
    except ResolveError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    return ReceiptResolvePreviewResponse(
        uncollapsed=_groups_to_schema(uncollapsed, category_names),
        resolved=_groups_to_schema(resolved, category_names),
    )


_LINE_REF_RE = re.compile(r"^L(\d+)$")


@router.patch("/{receipt_scan_id}/lines", response_model=ReceiptScanExtractResponse)
def correct_receipt_scan_lines(
    receipt_scan_id: UUID,
    request: ReceiptLineCorrectionRequest,
    user_id: str | None = None,
    db: Session = Depends(get_db),
):
    """Phase 6.5: closes the `needs_review` dead end (spec 1.2). Before this
    endpoint existed, a receipt that failed reconciliation could never be
    corrected and never be booked -- Phase 4 gated confirm on
    `step !== "needs_review"` and Phase 6 removed every means of editing a
    line. This is the fix: apply the caller's edits/inserts/deletes to the
    real `ReceiptLineItem` rows, re-run `receipt_validate.validate()` on the
    corrected set (never trust the client's own arithmetic), and flip
    `status` both ways -- `needs_review` -> `processed` when it now
    reconciles, and back if a later edit breaks it again.

    Deleting a line cascades onto any deposit line whose `parent_line_ref`
    points to it, rather than leaving it dangling for `validate()` to flag as
    `orphan_deposit` on the very next request -- a deposit with no parent
    item is never something the user would want to keep."""
    resolved_user_id = get_user_id(user_id)

    receipt_scan = (
        db.query(ReceiptScan)
        .filter(ReceiptScan.id == receipt_scan_id, ReceiptScan.user_id == resolved_user_id)
        .first()
    )
    if not receipt_scan:
        raise HTTPException(status_code=404, detail="Receipt scan not found")

    if receipt_scan.status == "completed":
        raise HTTPException(status_code=409, detail="A booked receipt cannot be edited")

    lines = (
        db.query(ReceiptLineItem)
        .filter(ReceiptLineItem.receipt_scan_id == receipt_scan.id)
        .order_by(ReceiptLineItem.position)
        .all()
    )
    lines_by_ref = {line.line_ref: line for line in lines}

    # --- deletes, cascaded onto orphaned deposits ---------------------------
    delete_refs: set[str] = set()
    for ref in request.deletes:
        if ref not in lines_by_ref:
            raise HTTPException(status_code=404, detail=f"Unknown line_ref {ref!r}")
        delete_refs.add(ref)

    # Fixed-point: a deposit whose parent just got added to the delete set is
    # itself added, which can in turn matter if deposits ever chain (they
    # don't today, but the loop costs nothing and doesn't assume otherwise).
    changed = True
    while changed:
        changed = False
        for line in lines:
            if line.line_ref in delete_refs:
                continue
            if line.kind == "deposit" and line.parent_line_ref in delete_refs:
                delete_refs.add(line.line_ref)
                changed = True

    edit_refs = {edit.line_ref for edit in request.edits}
    conflict = edit_refs & delete_refs
    if conflict:
        raise HTTPException(
            status_code=400,
            detail=(
                f"line_ref(s) {sorted(conflict)} cannot be both edited and "
                "deleted in the same request"
            ),
        )

    surviving_item_refs = {
        line.line_ref for line in lines if line.line_ref not in delete_refs and line.kind == "item"
    }

    # --- edits ---------------------------------------------------------------
    for edit in request.edits:
        line = lines_by_ref.get(edit.line_ref)
        if line is None:
            raise HTTPException(status_code=404, detail=f"Unknown line_ref {edit.line_ref!r}")

        touched = False
        if edit.discount_amount is not None:
            line.discount_amount = edit.discount_amount
            touched = True
        if edit.net_amount is not None:
            line.net_amount = edit.net_amount
            touched = True
        if edit.gross_amount is not None:
            line.gross_amount = edit.gross_amount
            touched = True
        elif edit.net_amount is not None:
            # Only net_amount was corrected -- keep gross - discount == net
            # holding automatically rather than forcing every amount
            # correction to also resend gross/discount by hand.
            discount = line.discount_amount if line.discount_amount is not None else Decimal("0")
            line.gross_amount = line.net_amount + discount
        if edit.name is not None:
            line.name = edit.name
            touched = True
        if touched:
            line.user_edited = True

    # --- inserts ---------------------------------------------------------------
    existing_numeric_refs = [
        int(match.group(1))
        for ref in lines_by_ref
        for match in [_LINE_REF_RE.match(ref or "")]
        if match
    ]
    next_ref_n = max(existing_numeric_refs, default=0) + 1
    max_position = max((line.position for line in lines), default=-1)

    inserted_lines: list[ReceiptLineItem] = []
    for insert in request.inserts:
        if insert.kind not in ("item", "deposit"):
            raise HTTPException(
                status_code=400, detail=f"Invalid kind {insert.kind!r}: must be item or deposit"
            )
        if insert.parent_line_ref is not None and insert.parent_line_ref not in surviving_item_refs:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"parent_line_ref {insert.parent_line_ref!r} does not refer to a "
                    "surviving item line"
                ),
            )

        line_ref = f"L{next_ref_n}"
        next_ref_n += 1
        max_position += 1

        discount_amount = (
            insert.discount_amount if insert.discount_amount is not None else Decimal("0")
        )
        gross_amount = (
            insert.gross_amount
            if insert.gross_amount is not None
            else insert.net_amount + discount_amount
        )

        new_line = ReceiptLineItem(
            receipt_scan_id=receipt_scan.id,
            line_ref=line_ref,
            position=max_position,
            name=insert.name,
            gross_amount=gross_amount,
            discount_amount=discount_amount,
            net_amount=insert.net_amount,
            kind=insert.kind,
            parent_line_ref=insert.parent_line_ref,
            user_edited=True,
        )
        db.add(new_line)
        inserted_lines.append(new_line)
        # Server-assigned ref for THIS insert may itself be a parent for a
        # later insert in the same request (e.g. a new item plus its own
        # deposit, both missing from the original extraction).
        if insert.kind == "item":
            surviving_item_refs.add(line_ref)

    # --- deletes, applied ------------------------------------------------------
    for line in lines:
        if line.line_ref in delete_refs:
            db.delete(line)

    db.flush()

    # --- re-validate, never trusting the client's own arithmetic ---------------
    surviving_lines = [line for line in lines if line.line_ref not in delete_refs]
    surviving_lines.extend(inserted_lines)
    surviving_lines.sort(key=lambda line: line.position)

    extracted_lines = [
        ExtractedLine(
            id=line.line_ref,
            raw_text=line.raw_text,
            name=line.name,
            quantity=line.quantity,
            gross_amount=line.gross_amount,
            discount_amount=line.discount_amount
            if line.discount_amount is not None
            else Decimal("0"),
            net_amount=line.net_amount,
            kind=line.kind,
            parent_id=line.parent_line_ref,
        )
        for line in surviving_lines
    ]
    extracted = ExtractedReceipt(
        merchant_name=receipt_scan.merchant_name,
        merchant_legal_name=receipt_scan.merchant_legal_name,
        merchant_address=receipt_scan.merchant_address,
        receipt_no=receipt_scan.receipt_no,
        fiscal_code=receipt_scan.fiscal_code,
        vat_id=receipt_scan.vat_id,
        booked_at=receipt_scan.receipt_date.isoformat() if receipt_scan.receipt_date else None,
        currency=receipt_scan.currency,
        payment_method=receipt_scan.payment_method,
        card_last4=receipt_scan.card_last4,
        printed_total=receipt_scan.printed_total,
        printed_discount_total=receipt_scan.printed_discount_total,
        lines=extracted_lines,
        extraction_model=receipt_scan.extraction_model,
    )
    errors = receipt_validate.validate(extracted)

    receipt_scan.validation_errors = [
        {"code": error.code, "message": error.message, "line_refs": list(error.line_refs)}
        for error in errors
    ] or None
    # Flips both ways: needs_review -> processed when the correction
    # reconciles, and back if a later edit breaks it again (requirement 2).
    receipt_scan.status = "needs_review" if errors else "processed"

    db.commit()
    db.refresh(receipt_scan)

    return _receipt_scan_response(receipt_scan)


def _receipt_group_external_id(receipt_scan: ReceiptScan, group: TransactionGroup) -> str:
    """Spec 6.3. Deterministic per (receipt identity, category) -- the same
    photo confirmed twice always produces the same `external_id` for the
    same group, which is what lets the database-level unique constraint
    catch the duplicate instead of an application-level check that can't
    survive a worker crash between two inserts."""
    key = "|".join(
        [
            receipt_scan.fiscal_code or receipt_scan.receipt_no or "",
            receipt_scan.merchant_name or "",
            str(receipt_scan.printed_total),
            str(group.category_id),
        ]
    )
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
    return f"receipt:{digest[:48]}"


def _transaction_with_details(
    transaction: Transaction, account: Account, category_names: dict
) -> TransactionWithDetails:
    return TransactionWithDetails(
        id=transaction.id,
        account_id=transaction.account_id,
        external_id=transaction.external_id,
        transaction_type=transaction.transaction_type,
        amount=transaction.amount,
        currency=transaction.currency,
        description=transaction.description,
        merchant=transaction.merchant,
        category_id=transaction.category_id,
        category_system_id=transaction.category_system_id,
        booked_at=transaction.booked_at,
        pending=transaction.pending,
        categorization_instructions=transaction.categorization_instructions,
        enrichment_data=transaction.enrichment_data,
        created_at=transaction.created_at,
        updated_at=transaction.updated_at,
        category_name=category_names.get(transaction.category_id),
        account_name=account.name,
    )


@router.post("/{receipt_scan_id}/confirm", response_model=ReceiptConfirmResponse)
def confirm_receipt_scan(
    receipt_scan_id: UUID,
    request: ReceiptScanConfirmRequest,
    user_id: str | None = None,
    db: Session = Depends(get_db),
):
    """Books the receipt as one `Transaction` per resolved category group
    (spec 6.2 -- not one per line). The submitted `groups` describe the
    user's per-line category edits; this endpoint applies them to the real
    `ReceiptLineItem` rows, re-runs `receipt_resolve.resolve` itself, and
    refuses to book anything if the submission doesn't match what `resolve`
    computes -- so the grouping/collapse policy lives here exactly once and
    can't be bypassed by a crafted request (implementation plan 6.2)."""
    resolved_user_id = get_user_id(user_id)

    receipt_scan = (
        db.query(ReceiptScan)
        .filter(ReceiptScan.id == receipt_scan_id, ReceiptScan.user_id == resolved_user_id)
        .first()
    )
    if not receipt_scan:
        raise HTTPException(status_code=404, detail="Receipt scan not found")

    if not request.groups:
        raise HTTPException(status_code=400, detail="No groups to import")

    account = (
        db.query(Account)
        .filter(Account.id == receipt_scan.account_id, Account.user_id == resolved_user_id)
        .first()
    )
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")

    lines = (
        db.query(ReceiptLineItem)
        .filter(ReceiptLineItem.receipt_scan_id == receipt_scan.id)
        .order_by(ReceiptLineItem.position)
        .all()
    )
    if not lines:
        raise HTTPException(status_code=400, detail="Receipt scan has no line items to confirm")
    lines_by_ref = {line.line_ref: line for line in lines}

    seen_refs: set[str] = set()
    for group in request.groups:
        for ref in group.line_refs:
            if ref not in lines_by_ref:
                raise HTTPException(status_code=400, detail=f"Unknown line_ref {ref!r}")
            if ref in seen_refs:
                raise HTTPException(
                    status_code=400,
                    detail=f"line_ref {ref!r} was submitted in more than one group",
                )
            seen_refs.add(ref)
    missing_refs = sorted(set(lines_by_ref) - seen_refs)
    if missing_refs:
        raise HTTPException(
            status_code=400,
            detail=f"Missing line_ref(s) in submitted groups: {missing_refs}",
        )

    submitted_category_ids = {group.category_id for group in request.groups if group.category_id}
    category_names = _category_names_for(db, resolved_user_id, submitted_category_ids)
    if submitted_category_ids and set(category_names.keys()) != submitted_category_ids:
        raise HTTPException(status_code=404, detail="Category not found")

    # Apply the user's per-line category edits before resolving -- `resolve`
    # groups strictly by `ReceiptLineItem.category_id`, so an edit has to
    # land there, not just in the echoed group, or the submission-vs-resolve
    # comparison below would match by construction rather than actually
    # checking anything.
    for group in request.groups:
        for ref in group.line_refs:
            line = lines_by_ref[ref]
            if line.category_id != group.category_id:
                line.category_id = group.category_id
                line.user_edited = True

    config = _load_resolve_config(db)
    try:
        resolved_groups = receipt_resolve.resolve(receipt_scan, lines, config)
    except ResolveError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc))

    submitted_amount_by_category: dict = {}
    for group in request.groups:
        submitted_amount_by_category[group.category_id] = (
            submitted_amount_by_category.get(group.category_id, Decimal("0")) + group.amount
        )
    resolved_amount_by_category = {g.category_id: g.amount for g in resolved_groups}

    if submitted_amount_by_category != resolved_amount_by_category:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail={
                "message": (
                    "Submitted grouping does not match the server-computed "
                    "resolution. Re-fetch POST /{id}/resolve and resubmit "
                    "exactly what it returns as `resolved`."
                ),
                "resolved": [
                    schema.model_dump(mode="json")
                    for schema in _groups_to_schema(resolved_groups, category_names)
                ],
            },
        )

    booked_at = request.booked_at or receipt_scan.receipt_date
    if booked_at is None:
        db.rollback()
        raise HTTPException(
            status_code=400,
            detail="booked_at is required: the scan has no receipt date to default to",
        )

    description_by_category: dict = {}
    transaction_type_by_category: dict = {}
    for group in request.groups:
        description_by_category.setdefault(group.category_id, group.description)
        transaction_type_by_category.setdefault(group.category_id, group.transaction_type)

    created: list[Transaction] = []
    for group in resolved_groups:
        transaction = Transaction(
            user_id=resolved_user_id,
            account_id=account.id,
            transaction_type=transaction_type_by_category.get(group.category_id, "debit"),
            amount=group.amount,
            currency=account.currency,
            description=description_by_category.get(group.category_id)
            or receipt_scan.merchant_name
            or "Receipt",
            booked_at=booked_at,
            category_id=group.category_id,
            receipt_scan_id=receipt_scan.id,
            external_id=_receipt_group_external_id(receipt_scan, group),
        )
        db.add(transaction)
        created.append(transaction)

    receipt_scan.status = "completed"
    receipt_scan.completed_at = datetime.now(timezone.utc)

    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        # Portable across dialects: SQLite's message is "UNIQUE constraint
        # failed: transactions.account_id, transactions.external_id" (no
        # constraint name); Postgres's is
        # 'duplicate key value violates unique constraint
        # "transactions_account_external_id"' plus a DETAIL line naming the
        # columns. Both always mention "external_id"; nothing else this
        # insert could violate does (account_id/category_id were already
        # validated to exist above).
        message = str(getattr(exc, "orig", exc) or exc).lower()
        if "external_id" not in message:
            raise

        logger.info(
            "confirm_receipt_scan: scan %s already booked (external_id collision)",
            receipt_scan.id,
        )
        external_ids = [_receipt_group_external_id(receipt_scan, g) for g in resolved_groups]
        existing = (
            db.query(Transaction)
            .filter(Transaction.account_id == account.id, Transaction.external_id.in_(external_ids))
            .all()
        )
        receipt_scan.status = "completed"
        receipt_scan.completed_at = datetime.now(timezone.utc)
        db.commit()
        return ReceiptConfirmResponse(
            transactions=[_transaction_with_details(t, account, category_names) for t in existing],
            already_booked=True,
        )

    for transaction in created:
        db.refresh(transaction)

    for group, transaction in zip(resolved_groups, created):
        for ref in group.line_refs:
            lines_by_ref[ref].booked_transaction_id = transaction.id
    db.commit()

    return ReceiptConfirmResponse(
        transactions=[_transaction_with_details(t, account, category_names) for t in created],
        already_booked=False,
    )
