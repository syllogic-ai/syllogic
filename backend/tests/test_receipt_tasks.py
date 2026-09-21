"""Tests for `tasks.receipt_tasks.extract_receipt_task` (Phase 4 of the
receipt-ingestion rework). See
docs/specs/receipt-ingestion-implementation.md 4.3 and its "Phase 4
checkpoint".

The vision/LLM call itself is mocked throughout via `extract_receipt` --
these tests exercise the task's own logic (load -> extract -> validate ->
persist -> status), not a real model. `receipt_storage` is used for real
(against a tmp_path storage root) rather than mocked, since it's cheap and
exercising the real encrypt/decrypt round trip on `file_path_ciphertext` is
exactly the path this task depends on.
"""

from contextlib import contextmanager
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import DefaultClause, create_engine, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from unittest.mock import patch

from app.models import Account, Category, ReceiptLineItem, ReceiptScan, User
from app.services import receipt_storage
from app.services.receipt_extract import ExtractedLine, ExtractedReceipt
from tasks.receipt_tasks import (
    _is_transient_extraction_error,
    extract_receipt_task,
)


@compiles(JSONB, "sqlite")
def _jsonb_as_text_on_sqlite(element, compiler, **kw):
    return "TEXT"


@contextmanager
def _sqlite_safe_server_defaults(*models):
    originals = []
    for model in models:
        for column in model.__table__.columns:
            default = column.server_default
            raw = getattr(getattr(default, "arg", None), "text", None)
            if raw and "::" in raw:
                originals.append((column, default))
                column.server_default = DefaultClause(text(raw.split("::", 1)[0]))
    try:
        yield
    finally:
        for column, original in originals:
            column.server_default = original


@pytest.fixture
def db():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    models = (User, Account, Category, ReceiptScan, ReceiptLineItem)
    with _sqlite_safe_server_defaults(*models):
        for model in models:
            model.__table__.create(bind=engine)
    # expire_on_commit=False: the task under test patches `SessionLocal` to
    # return this same session and calls `db.close()` in its own `finally`.
    # With the default expire-on-commit, every attribute (including `id`) is
    # marked stale after the task's commit and requires a lazy reload on next
    # access -- which raises `DetachedInstanceError` once the session that
    # would service that reload has already been closed. Since it's the same
    # session/object identity throughout, the task's mutations are visible on
    # `scan` directly without needing to survive a reload at all.
    with Session(engine, expire_on_commit=False) as session:
        yield session


@pytest.fixture(autouse=True)
def _storage_root(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCAL_STORAGE_PATH", str(tmp_path))
    yield tmp_path


@pytest.fixture
def scan(db):
    db.add(User(id="u1", email="u@example.com", functional_currency="EUR"))
    db.commit()
    account = Account(
        id=uuid4(), user_id="u1", name="Checking", account_type="checking", currency="EUR"
    )
    db.add(account)
    db.commit()

    stored = receipt_storage.put("u1", b"fake-jpeg-bytes", "image/jpeg")
    receipt_scan = ReceiptScan(
        id=uuid4(),
        user_id="u1",
        account_id=account.id,
        status="pending",
        file_path=stored.file_path,
        file_path_ciphertext=stored.file_path_ciphertext,
    )
    db.add(receipt_scan)
    db.commit()
    return receipt_scan


def _clean_receipt(model="gpt-4o-mini") -> ExtractedReceipt:
    return ExtractedReceipt(
        merchant_name="Test Store",
        merchant_legal_name=None,
        merchant_address=None,
        receipt_no=None,
        fiscal_code=None,
        vat_id=None,
        booked_at="2026-08-18T10:00:00",
        currency="EUR",
        payment_method="card",
        card_last4="1234",
        printed_total=Decimal("3.49"),
        printed_discount_total=None,
        lines=[
            ExtractedLine(
                id="L1",
                raw_text="Milk 2L 3.49",
                name="Milk 2L",
                quantity=Decimal("1"),
                gross_amount=Decimal("3.49"),
                discount_amount=Decimal("0"),
                net_amount=Decimal("3.49"),
                kind="item",
                parent_id=None,
            )
        ],
        extraction_model=model,
    )


def _run(db, receipt_scan_id):
    """Runs the task through `.apply()` (Celery's synchronous/eager path)
    rather than `.run()`. This matters specifically for the retry tests:
    `.run()` sets `request.called_directly = True`, under which
    `self.retry(exc=exc)` just re-raises `exc` immediately instead of
    exercising Celery's actual (eager) retry loop -- `.apply()` drives the
    real retry machinery synchronously, including incrementing
    `self.request.retries` across attempts, which is what
    `extract_receipt_task` actually depends on."""
    with patch("tasks.receipt_tasks.SessionLocal", return_value=db):
        return extract_receipt_task.apply(args=[str(receipt_scan_id)]).get()


def _reload(db, scan) -> ReceiptScan:
    """The task's own `finally: db.close()` runs against this same shared
    session (patched via `SessionLocal`), which expunges `scan` from the
    identity map -- `db.refresh(scan)` on a detached instance raises
    `InvalidRequestError`. A fresh query against the same session (closing
    doesn't prevent reuse, only the *object* is detached) gets the
    post-commit row instead."""
    return db.query(ReceiptScan).filter(ReceiptScan.id == scan.id).one()


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


def test_clean_receipt_is_processed_with_lines_persisted(db, scan):
    with patch("tasks.receipt_tasks.extract_receipt", return_value=_clean_receipt()):
        result = _run(db, scan.id)

    assert result["status"] == "processed"

    scan = _reload(db, scan)
    assert scan.status == "processed"
    assert scan.merchant_name == "Test Store"
    assert scan.printed_total == Decimal("3.49")
    assert scan.receipt_total == Decimal("3.49")  # generated alias, spec 2.1
    assert scan.currency == "EUR"
    assert scan.extraction_model == "gpt-4o-mini"
    assert scan.validation_errors is None
    assert scan.receipt_date is not None

    lines = db.query(ReceiptLineItem).filter_by(receipt_scan_id=scan.id).all()
    assert len(lines) == 1
    assert lines[0].name == "Milk 2L"
    assert lines[0].net_amount == Decimal("3.49")
    assert lines[0].line_ref == "L1"


def test_sum_of_net_amounts_equals_printed_total_on_a_clean_receipt(db, scan):
    receipt = ExtractedReceipt(
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
        printed_total=Decimal("6.48"),
        printed_discount_total=None,
        lines=[
            ExtractedLine(
                "L1",
                "Milk 2L 3.49",
                "Milk 2L",
                None,
                Decimal("3.49"),
                Decimal("0"),
                Decimal("3.49"),
                "item",
                None,
            ),
            ExtractedLine(
                "L2",
                "Bread 2.99",
                "Bread",
                None,
                Decimal("2.99"),
                Decimal("0"),
                Decimal("2.99"),
                "item",
                None,
            ),
        ],
        extraction_model="gpt-4o-mini",
    )
    with patch("tasks.receipt_tasks.extract_receipt", return_value=receipt):
        result = _run(db, scan.id)

    assert result["status"] == "processed"
    lines = (
        db.query(ReceiptLineItem)
        .filter_by(receipt_scan_id=scan.id)
        .order_by(ReceiptLineItem.position)
        .all()
    )
    total = sum((line.net_amount for line in lines), Decimal("0"))
    assert total == Decimal("6.48")


# ---------------------------------------------------------------------------
# A receipt that doesn't reconcile -> needs_review, nothing lost
# ---------------------------------------------------------------------------


def test_line_manually_corrupted_is_needs_review_with_the_bad_line_flagged(db, scan):
    receipt = _clean_receipt()
    # Corrupt the single line: net_amount no longer matches printed_total.
    receipt.lines[0].net_amount = Decimal("3.50")

    with patch("tasks.receipt_tasks.extract_receipt", return_value=receipt):
        result = _run(db, scan.id)

    assert result["status"] == "needs_review"
    scan = _reload(db, scan)
    assert scan.status == "needs_review"
    assert scan.validation_errors is not None
    codes = {e["code"] for e in scan.validation_errors}
    assert "total_mismatch" in codes

    # The line itself is still persisted for review, not dropped.
    lines = db.query(ReceiptLineItem).filter_by(receipt_scan_id=scan.id).all()
    assert len(lines) == 1
    assert lines[0].net_amount == Decimal("3.50")


def test_orphan_deposit_is_flagged_in_persisted_validation_errors(db, scan):
    receipt = ExtractedReceipt(
        merchant_name="Store",
        merchant_legal_name=None,
        merchant_address=None,
        receipt_no=None,
        fiscal_code=None,
        vat_id=None,
        booked_at="2026-08-18T10:00:00",
        currency="EUR",
        payment_method="card",
        card_last4=None,
        printed_total=Decimal("0.50"),
        printed_discount_total=None,
        lines=[
            ExtractedLine(
                "L1",
                "Deposit",
                "Deposit",
                None,
                Decimal("0.50"),
                Decimal("0"),
                Decimal("0.50"),
                "deposit",
                "L99",
            ),
        ],
        extraction_model="gpt-4o-mini",
    )
    with patch("tasks.receipt_tasks.extract_receipt", return_value=receipt):
        result = _run(db, scan.id)

    assert result["status"] == "needs_review"
    scan = _reload(db, scan)
    codes = {e["code"] for e in scan.validation_errors}
    assert "orphan_deposit" in codes
    assert scan.validation_errors[
        [e["code"] for e in scan.validation_errors].index("orphan_deposit")
    ]["line_refs"] == ["L1"]


# ---------------------------------------------------------------------------
# Legacy (tesseract) engine defaults: only applied when extraction_model is None
# ---------------------------------------------------------------------------


def test_legacy_engine_backfills_currency_from_account_and_date_from_scan(db, scan):
    receipt = _clean_receipt(model=None)
    receipt.currency = None
    receipt.booked_at = None

    with patch("tasks.receipt_tasks.extract_receipt", return_value=receipt):
        result = _run(db, scan.id)

    scan = _reload(db, scan)
    assert scan.currency == "EUR"  # backfilled from the account
    assert scan.receipt_date is not None
    # Still reconciles (single clean line matching printed_total), so this
    # doesn't by itself force needs_review.
    assert result["status"] == "processed"


def test_vision_engine_null_currency_is_never_backfilled(db, scan):
    # extraction_model set -> this is the vision engine's own "illegible,
    # don't guess" null (spec 1.3) -- backfilling it would defeat validation.
    receipt = _clean_receipt(model="gpt-4o-mini")
    receipt.currency = None

    with patch("tasks.receipt_tasks.extract_receipt", return_value=receipt):
        result = _run(db, scan.id)

    scan = _reload(db, scan)
    assert scan.currency is None
    assert result["status"] == "needs_review"
    codes = {e["code"] for e in scan.validation_errors}
    assert "bad_currency" in codes


# ---------------------------------------------------------------------------
# Failure modes
# ---------------------------------------------------------------------------


def test_unknown_receipt_scan_id_returns_not_found_without_raising(db):
    result = _run(db, uuid4())
    assert result["status"] == "not_found"


def test_missing_stored_file_marks_the_scan_failed(db, scan):
    receipt_storage.delete(scan.file_path)
    result = _run(db, scan.id)

    assert result["status"] == "failed"
    scan = _reload(db, scan)
    assert scan.status == "failed"
    assert scan.error_message


def test_non_transient_extraction_error_marks_the_scan_failed_without_retry(db, scan):
    with patch(
        "tasks.receipt_tasks.extract_receipt",
        side_effect=RuntimeError("the model refused to answer"),
    ):
        result = _run(db, scan.id)

    assert result["status"] == "failed"
    scan = _reload(db, scan)
    assert scan.status == "failed"
    assert "refused" in scan.error_message


def test_transient_extraction_error_retries_then_fails_after_max_retries(db, scan):
    # `.apply()` drives Celery's real (eager) retry loop synchronously --
    # `max_retries=2` means 3 total attempts (the original call plus 2
    # retries) before the task gives up.
    with patch(
        "tasks.receipt_tasks.extract_receipt",
        side_effect=TimeoutError("Request timed out after 60s"),
    ) as mock_extract:
        result = _run(db, scan.id)

    assert mock_extract.call_count == 3
    assert result["status"] == "failed"
    scan = _reload(db, scan)
    assert scan.status == "failed"
    assert "timed out" in scan.error_message.lower()


def test_transient_extraction_error_succeeds_after_one_retry(db, scan):
    # First attempt times out; the retry (still the same task invocation,
    # via `.apply()`'s eager retry loop) succeeds -- the scan should end up
    # `processed`, not `failed`, and nothing about the earlier timeout should
    # leak into the persisted row.
    with patch(
        "tasks.receipt_tasks.extract_receipt",
        side_effect=[TimeoutError("Request timed out after 60s"), _clean_receipt()],
    ) as mock_extract:
        result = _run(db, scan.id)

    assert mock_extract.call_count == 2
    assert result["status"] == "processed"
    scan = _reload(db, scan)
    assert scan.status == "processed"
    # This fixture seeds no Category rows, so stage 2 legitimately reports that
    # it had nothing to assign to. What must not appear is the earlier timeout:
    # the retry succeeded, so the extraction failure is not the user's problem.
    assert "timed out" not in (scan.error_message or "").lower()


# ---------------------------------------------------------------------------
# _is_transient_extraction_error
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "message",
    [
        "Connection timed out",
        "429 Too Many Requests",
        "rate limit exceeded, please retry",
        "503 Service Unavailable",
        "upstream connect error",
    ],
)
def test_transient_error_messages_are_recognized(message):
    assert _is_transient_extraction_error(RuntimeError(message)) is True


@pytest.mark.parametrize(
    "message",
    [
        "the model refused the request",
        "$: missing required field(s) ['name']",
        "401 Unauthorized: invalid API key",
    ],
)
def test_non_transient_error_messages_are_not_retried(message):
    assert _is_transient_extraction_error(RuntimeError(message)) is False


def test_no_capable_provider_error_is_never_transient():
    from app.services.llm_client import NoCapableProviderError

    assert _is_transient_extraction_error(NoCapableProviderError("no vision provider")) is False


def test_transient_error_is_detected_from_the_chained_cause():
    from app.services.llm_structured import StructuredCallError

    try:
        raise TimeoutError("connection timed out")
    except TimeoutError as inner:
        wrapped = StructuredCallError("failed on every configured provider")
        wrapped.__cause__ = inner

    assert _is_transient_extraction_error(wrapped) is True
