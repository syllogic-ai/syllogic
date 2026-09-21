"""Celery task: extract a scanned receipt (stage 1 of the receipt-ingestion
pipeline) off the request thread. See
docs/specs/receipt-ingestion-implementation.md 4.3 and
docs/specs/receipt-ingestion.md Part 4.1.

**Must be registered in `backend/celery_app.py`'s `include=[...]` list.**
`autodiscover_tasks(["tasks"])` there is belt-and-braces and will NOT save a
module missing from `include` -- the task enqueues fine (the producer side
only needs the task *name*, a string) and is then silently never consumed by
any worker that never imported this module. There is no error, no log line,
just a scan stuck `pending` forever.

Flow: load the scan -> `receipt_storage.get(file_path)` -> `extract_receipt`
(engine gated by `RECEIPT_EXTRACTION_ENGINE`) -> `validate` -> persist header
fields, line items, and `extraction_model` -> `status` becomes `processed` or
`needs_review`. On an unexpected exception, `status="failed"` and
`error_message`, matching what the synchronous route used to do.

**Stage 2 (categorization) runs only when validation passed.** There is no
reason to categorize a receipt that will not be booked
(docs/specs/receipt-ingestion-implementation.md 5.2). A categorization
failure (provider error, or `ReceiptCategorizationError` from
`receipt_categorize`'s enforcement) is logged and swallowed rather than
failing the whole task: extraction and validation already succeeded and are
already committed by that point, `receipt_line_items.category_id` is
nullable, and there is no `status` value in this schema for "extracted but
not categorized" -- inventing one is Phase 6/8 territory, not this one's.
The scan is left `processed` with its lines uncategorized, which is a
strictly better outcome than losing an otherwise-good extraction over a
transient categorization failure.

Retries (`max_retries=2`) are for transient provider errors only -- a
timeout, a connection failure, a rate limit. A validation failure is not a
retry; it is an answer, and retrying it would just ask the same question of
the same photo and get the same answer.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from uuid import UUID

from celery import shared_task
from celery.exceptions import Retry
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models import Account, ReceiptLineItem, ReceiptScan
from app.security.data_encryption import decrypt_with_fallback
from app.services import receipt_storage
from app.services.llm_client import NoCapableProviderError
from app.services.receipt_categorize import categorize_receipt_lines
from app.services.receipt_extract import ExtractedReceipt, extract_receipt
from app.services.receipt_validate import parse_booked_at, validate

logger = logging.getLogger(__name__)

# Substrings of an exception's message (or its chained `__cause__`, since
# `call_structured`/`StructuredCallError` wrap the real failure) that mark it
# as a transient provider problem worth a Celery retry with backoff, rather
# than a permanent one (bad config, bad content, refusal) that retrying the
# same input against the same provider can't fix.
_TRANSIENT_ERROR_MARKERS = (
    "timeout",
    "timed out",
    "connection",
    "connect",
    "429",
    "rate limit",
    "502",
    "503",
    "504",
    "temporarily unavailable",
    "overloaded",
)


def _is_transient_extraction_error(exc: Exception) -> bool:
    if isinstance(exc, NoCapableProviderError):
        # A configuration problem ("no provider supports vision") -- retrying
        # the same task won't make a provider capability appear.
        return False

    candidates = [exc]
    if exc.__cause__ is not None:
        candidates.append(exc.__cause__)

    for candidate in candidates:
        message = str(candidate).lower()
        if any(marker in message for marker in _TRANSIENT_ERROR_MARKERS):
            return True
    return False


def _load_receipt_image(receipt_scan: ReceiptScan) -> tuple[bytes, str]:
    file_path = decrypt_with_fallback(receipt_scan.file_path_ciphertext, receipt_scan.file_path)
    if not file_path:
        raise FileNotFoundError("Receipt scan has no stored file path")
    data = receipt_storage.get(file_path)  # raises FileNotFoundError if missing
    content_type = receipt_storage.content_type_for_path(file_path)
    return data, content_type


def _apply_legacy_engine_defaults(
    db: Session, receipt_scan: ReceiptScan, extracted: ExtractedReceipt
) -> None:
    """The tesseract engine (`RECEIPT_EXTRACTION_ENGINE=tesseract`, the
    default for this release) has no way to read a currency code or a date
    off a receipt -- it never did, even before this rework. Defaulting those
    two fields from context (the account's currency; the scan's upload time)
    only for that engine keeps the rollback path actually usable, rather than
    forcing every tesseract-extracted scan into permanent `needs_review` over
    fields whose `null` means something different for the vision engine
    ("illegible, don't guess" -- spec 1.3). `extracted.extraction_model` is
    `None` only for the tesseract engine; the vision path always sets it to
    the provider's model string, so it's a reliable discriminator here.
    """
    if extracted.extraction_model is not None:
        return

    if extracted.currency is None:
        account = db.query(Account).filter(Account.id == receipt_scan.account_id).first()
        if account is not None and account.currency:
            extracted.currency = account.currency

    if extracted.booked_at is None:
        reference = receipt_scan.created_at or datetime.now(timezone.utc)
        extracted.booked_at = reference.isoformat()


def _persist_extraction(
    db: Session,
    receipt_scan: ReceiptScan,
    extracted: ExtractedReceipt,
    errors,
) -> None:
    receipt_scan.merchant_name = extracted.merchant_name
    receipt_scan.merchant_legal_name = extracted.merchant_legal_name
    receipt_scan.merchant_address = extracted.merchant_address
    receipt_scan.receipt_no = extracted.receipt_no
    receipt_scan.fiscal_code = extracted.fiscal_code
    receipt_scan.vat_id = extracted.vat_id
    receipt_scan.currency = extracted.currency
    receipt_scan.payment_method = extracted.payment_method
    receipt_scan.card_last4 = extracted.card_last4
    receipt_scan.printed_total = extracted.printed_total
    # `receipt_total` is kept as an alias of `printed_total` for one release
    # (spec 2.1) -- the extract/get routes' response schema still reads it.
    receipt_scan.receipt_total = extracted.printed_total
    receipt_scan.printed_discount_total = extracted.printed_discount_total
    receipt_scan.extraction_model = extracted.extraction_model

    parsed_booked_at = parse_booked_at(extracted.booked_at)
    if parsed_booked_at is not None:
        receipt_scan.receipt_date = parsed_booked_at

    receipt_scan.validation_errors = [
        {
            "code": error.code,
            "message": error.message,
            "line_refs": list(error.line_refs),
        }
        for error in errors
    ] or None

    # Replacing rather than diffing: this task only ever runs once per scan
    # before any user edit exists. Re-extraction against a scan a user has
    # already reviewed (retry, model upgrade, cache miss) and `user_edited`
    # preservation is Phase 6's idempotency/resolve concern, not this one's.
    db.query(ReceiptLineItem).filter(ReceiptLineItem.receipt_scan_id == receipt_scan.id).delete()

    for position, line in enumerate(extracted.lines):
        db.add(
            ReceiptLineItem(
                receipt_scan_id=receipt_scan.id,
                line_ref=line.id,
                position=position,
                raw_text=line.raw_text,
                name=line.name,
                quantity=line.quantity,
                gross_amount=line.gross_amount,
                discount_amount=line.discount_amount,
                net_amount=line.net_amount,
                kind=line.kind,
                parent_line_ref=line.parent_id,
            )
        )

    receipt_scan.status = "needs_review" if errors else "processed"


def _run_categorization(db: Session, receipt_scan: ReceiptScan) -> None:
    """Stage 2, gated on validation having passed (see module docstring).
    Commits its own writes separately from stage 1's so a categorization
    failure can never roll back an otherwise-good extraction.

    A failure here does not fail the scan -- extraction and validation have
    already succeeded and been committed, and `category_id` is nullable, so
    the receipt is still reviewable and bookable with categories assigned by
    hand. But it is recorded on `error_message` rather than only logged: the
    user would otherwise be shown a review screen where every line is
    uncategorized with nothing saying why, which reads as the model having
    chosen nothing rather than as a stage that never ran.
    """
    lines = (
        db.query(ReceiptLineItem)
        .filter(ReceiptLineItem.receipt_scan_id == receipt_scan.id)
        .order_by(ReceiptLineItem.position)
        .all()
    )
    try:
        categorize_receipt_lines(db, receipt_scan.user_id, lines)
        db.commit()
    except Exception as exc:
        db.rollback()
        logger.exception(
            "extract_receipt_task: categorization failed for scan %s; lines left uncategorized",
            receipt_scan.id,
        )
        # Re-read: the rollback above expired the instance the caller holds.
        scan = db.query(ReceiptScan).filter(ReceiptScan.id == receipt_scan.id).first()
        if scan is not None:
            scan.error_message = (
                f"Automatic categorization failed ({type(exc).__name__}); "
                "line items were extracted but not categorized."
            )[:2000]
            db.commit()


@shared_task(
    bind=True,
    name="tasks.receipt_tasks.categorize_receipt_task",
    max_retries=2,
)
def categorize_receipt_task(self, receipt_scan_id: str) -> dict:
    """Stage 2 only, run standalone on an extraction-cache hit (spec 6.4):
    the route already copied stage 1's output (header + line items)
    synchronously from the cache source, so this task's whole job is
    `_run_categorization` -- no image load, no vision call. Kept a separate
    task (rather than a flag on `extract_receipt_task`) so a cache hit never
    even enqueues the expensive path."""
    db = SessionLocal()
    try:
        try:
            scan_uuid = UUID(receipt_scan_id)
        except (ValueError, AttributeError, TypeError):
            logger.warning(
                "categorize_receipt_task: %r is not a valid receipt scan id",
                receipt_scan_id,
            )
            return {"status": "not_found", "receipt_scan_id": receipt_scan_id}

        receipt_scan = db.query(ReceiptScan).filter(ReceiptScan.id == scan_uuid).first()
        if receipt_scan is None:
            logger.warning("categorize_receipt_task: receipt scan %s not found", receipt_scan_id)
            return {"status": "not_found", "receipt_scan_id": receipt_scan_id}

        _run_categorization(db, receipt_scan)
        return {"status": receipt_scan.status, "receipt_scan_id": receipt_scan_id}
    finally:
        db.close()


@shared_task(
    bind=True,
    name="tasks.receipt_tasks.extract_receipt_task",
    max_retries=2,
)
def extract_receipt_task(self, receipt_scan_id: str) -> dict:
    db = SessionLocal()
    try:
        try:
            scan_uuid = UUID(receipt_scan_id)
        except (ValueError, AttributeError, TypeError):
            # Malformed id -- there is no row to fail, so this is "not
            # found", not an unexpected-failure path (and querying a UUID
            # column with a non-UUID string would raise inside SQLAlchemy
            # on some dialects rather than simply returning no rows).
            logger.warning(
                "extract_receipt_task: %r is not a valid receipt scan id",
                receipt_scan_id,
            )
            return {"status": "not_found", "receipt_scan_id": receipt_scan_id}

        receipt_scan = db.query(ReceiptScan).filter(ReceiptScan.id == scan_uuid).first()
        if receipt_scan is None:
            logger.warning("extract_receipt_task: receipt scan %s not found", receipt_scan_id)
            return {"status": "not_found", "receipt_scan_id": receipt_scan_id}

        try:
            image_bytes, content_type = _load_receipt_image(receipt_scan)
        except FileNotFoundError as exc:
            logger.warning(
                "extract_receipt_task: no stored image for scan %s: %s",
                receipt_scan_id,
                exc,
            )
            receipt_scan.status = "failed"
            receipt_scan.error_message = str(exc)[:2000]
            db.commit()
            return {"status": "failed", "receipt_scan_id": receipt_scan_id}

        try:
            extracted = extract_receipt(image_bytes, content_type, db)
        except Exception as exc:
            if _is_transient_extraction_error(exc) and self.request.retries < self.max_retries:
                logger.warning(
                    "extract_receipt_task: transient failure for %s (attempt %s/%s): %s",
                    receipt_scan_id,
                    self.request.retries + 1,
                    self.max_retries,
                    exc,
                )
                raise self.retry(exc=exc, countdown=30)

            logger.exception("extract_receipt_task: extraction failed for %s", receipt_scan_id)
            receipt_scan.status = "failed"
            receipt_scan.error_message = str(exc)[:2000]
            db.commit()
            return {"status": "failed", "receipt_scan_id": receipt_scan_id}

        _apply_legacy_engine_defaults(db, receipt_scan, extracted)
        errors = validate(extracted)
        _persist_extraction(db, receipt_scan, extracted, errors)
        db.commit()

        if not errors:
            _run_categorization(db, receipt_scan)

        return {"status": receipt_scan.status, "receipt_scan_id": receipt_scan_id}
    except Retry:
        # `self.retry(...)` above raises this to hand control back to Celery
        # so it can actually schedule the retry -- must propagate untouched,
        # not be treated as the task's own failure.
        raise
    except Exception as exc:
        db.rollback()
        logger.exception("extract_receipt_task: unexpected failure for %s", receipt_scan_id)
        try:
            receipt_scan = (
                db.query(ReceiptScan).filter(ReceiptScan.id == UUID(receipt_scan_id)).first()
            )
            if receipt_scan is not None:
                receipt_scan.status = "failed"
                receipt_scan.error_message = str(exc)[:2000]
                db.commit()
        except Exception:
            db.rollback()
        return {"status": "failed", "receipt_scan_id": receipt_scan_id}
    finally:
        db.close()
