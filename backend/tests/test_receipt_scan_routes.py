"""Integration tests for the /api/receipt-scan endpoints (Phase 4: the
extract endpoint is now async -- see
docs/specs/receipt-ingestion-implementation.md 4.4).

Extraction itself (the Celery task, the vision/tesseract engines) is tested
separately in test_receipt_tasks.py and test_receipt_extract.py. These tests
only exercise the HTTP surface: the extract endpoint stores the image and
enqueues without running extraction inline (`extract_receipt_task.delay` is
mocked), the GET endpoint reflects whatever the task has persisted (line
items and validation_errors are seeded directly via the DB fixture, standing
in for a completed task run), and confirm/image are unaffected by the async
change and continue to operate on a scan row set up directly rather than via
a live extract call.
"""

import base64
import hashlib
import hmac
import json
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import patch
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import DefaultClause, create_engine, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.database import get_db
from app.main import app
from app.models import (
    AppSetting,
    Account,
    Category,
    ReceiptLineItem,
    ReceiptScan,
    Transaction,
    User,
)
from app.services import receipt_storage


# Account.alias_patterns is a plain (Postgres) JSONB column, unrelated to
# receipt ingestion, that predates this file and that SQLite's DDL compiler
# cannot render at all -- table creation below raises `CompileError` without
# this shim, independent of anything Phase 1 touches. Scoped to this test
# module rather than fixed in app/models.py, which is out of this phase's
# scope.
@compiles(JSONB, "sqlite")
def _jsonb_as_text_on_sqlite(element, compiler, **kw):
    return "TEXT"


@contextmanager
def _sqlite_safe_server_defaults(*models):
    """`alias_patterns`'s server_default is `'[]'::jsonb` -- valid Postgres,
    not valid SQLite (`::` isn't a token it knows). Temporarily strips the
    Postgres cast from any such default on the given models' tables so
    `Table.create()` succeeds on the in-memory SQLite engine, then restores
    it -- these are the shared, globally-mapped Table objects, not copies."""
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


INTERNAL_AUTH_SECRET = "test-internal-secret"

TINY_PNG_B64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)
TINY_PNG_BYTES = base64.b64decode(TINY_PNG_B64)


def _extract_path(account_id, content_type: str = "image/png") -> str:
    return f"/api/receipt-scan/extract?account_id={account_id}&content_type={content_type}"


def _signed_headers(
    method: str, path_with_query: str, user_id: str = "u1", body: bytes = b""
) -> dict:
    timestamp = str(int(time.time()))
    payload = "\n".join(
        [method.upper(), path_with_query, user_id, timestamp, hashlib.sha256(body).hexdigest()]
    )
    signature = hmac.new(
        INTERNAL_AUTH_SECRET.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256
    ).hexdigest()
    return {
        "x-syllogic-user-id": user_id,
        "x-syllogic-timestamp": timestamp,
        "x-syllogic-signature": signature,
    }


class SigningClient:
    def __init__(self, client: TestClient):
        self._client = client

    def request(self, method: str, url: str, **kwargs):
        headers = dict(kwargs.pop("headers", {}) or {})
        body = b""
        if "json" in kwargs:
            body = json.dumps(kwargs.pop("json"), separators=(",", ":")).encode("utf-8")
            kwargs["content"] = body
            headers["content-type"] = "application/json"
        elif "content" in kwargs and kwargs["content"] is not None:
            content = kwargs["content"]
            body = content if isinstance(content, bytes) else str(content).encode("utf-8")
            headers.setdefault("content-type", "application/octet-stream")
        headers.update(_signed_headers(method, url, body=body))
        return self._client.request(method, url, headers=headers, **kwargs)

    def get(self, url, **kw):
        return self.request("GET", url, **kw)

    def post(self, url, **kw):
        return self.request("POST", url, **kw)

    def patch(self, url, **kw):
        return self.request("PATCH", url, **kw)


@pytest.fixture
def db():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    models = (User, Account, Category, ReceiptScan, Transaction, ReceiptLineItem, AppSetting)
    with _sqlite_safe_server_defaults(*models):
        for model in models:
            model.__table__.create(bind=engine)
    with Session(engine, expire_on_commit=False) as session:
        yield session


@pytest.fixture
def client(db, monkeypatch, tmp_path):
    monkeypatch.setenv("INTERNAL_AUTH_SECRET", INTERNAL_AUTH_SECRET)
    # receipt_storage.put/get write to real disk; keep it in a scratch dir so
    # tests never touch (or depend on) a real uploads tree.
    monkeypatch.setenv("LOCAL_STORAGE_PATH", str(tmp_path))
    db.add(User(id="u1", email="u@example.com", functional_currency="EUR"))
    db.add(User(id="u2", email="other@example.com", functional_currency="EUR"))
    db.commit()
    app.dependency_overrides[get_db] = lambda: db
    # Mirrors the pattern used elsewhere (e.g. test_accounts.py): the route's
    # bare `user_id` parameter is picked up by FastAPI as a query param, so a
    # test can spoof "the other user" by passing `?user_id=...` explicitly --
    # every other call defaults through to "u1".
    monkeypatch.setattr("app.routes.receipt_scan.get_user_id", lambda x=None: x or "u1")
    yield SigningClient(TestClient(app))
    app.dependency_overrides.clear()


@pytest.fixture
def account(db):
    acc = Account(
        id=uuid4(), user_id="u1", name="Checking", account_type="checking", currency="EUR"
    )
    db.add(acc)
    db.commit()
    return acc


def _seed_scan(db, account, **overrides) -> ReceiptScan:
    """Creates a ReceiptScan row directly, bypassing a live extract call --
    confirm/image/get don't depend on how the scan reached its current
    status, so seeding it directly decouples these HTTP-surface tests from
    the extraction pipeline (covered separately in test_receipt_tasks.py)."""
    stored = receipt_storage.put("u1", TINY_PNG_BYTES, "image/png")
    defaults = dict(
        id=uuid4(),
        user_id="u1",
        account_id=account.id,
        status="processed",
        file_path=stored.file_path,
        file_path_ciphertext=stored.file_path_ciphertext,
    )
    defaults.update(overrides)
    scan = ReceiptScan(**defaults)
    db.add(scan)
    db.commit()
    return scan


# ---------------------------------------------------------------------------
# POST /extract -- async: 202, pending, enqueues, no items
# ---------------------------------------------------------------------------


def test_extract_returns_202_pending_and_enqueues_the_task(client, db, account):
    with patch("tasks.receipt_tasks.extract_receipt_task.delay") as mock_delay:
        r = client.post(_extract_path(account.id), content=TINY_PNG_BYTES)

    assert r.status_code == 202, r.text
    body = r.json()
    assert body["status"] == "pending"
    assert body["items"] == []
    assert body["validation_errors"] == []

    scan = db.query(ReceiptScan).one()
    assert scan.status == "pending"
    assert scan.account_id == account.id
    # Bug 0.1: the storage handle must land on the row, not be discarded.
    assert scan.file_path is not None
    assert scan.file_path_ciphertext is not None
    assert scan.file_path.startswith("receipt-scans/u1/")
    assert scan.file_sha256 is not None

    mock_delay.assert_called_once_with(str(scan.id))
    assert body["receipt_scan_id"] == str(scan.id)


def test_extract_rejects_unknown_account(client):
    with patch("tasks.receipt_tasks.extract_receipt_task.delay"):
        r = client.post(_extract_path(uuid4()), content=TINY_PNG_BYTES)
    assert r.status_code == 404


def test_extract_rejects_empty_body(client, account):
    with patch("tasks.receipt_tasks.extract_receipt_task.delay"):
        r = client.post(_extract_path(account.id), content=b"")
    assert r.status_code == 400


def test_extract_rejects_oversized_body(client, account):
    import app.routes.receipt_scan as receipt_scan_route

    with patch.object(receipt_scan_route, "MAX_IMAGE_BYTES", 10):
        with patch("tasks.receipt_tasks.extract_receipt_task.delay"):
            r = client.post(_extract_path(account.id), content=TINY_PNG_BYTES)
    assert r.status_code == 413


# ---------------------------------------------------------------------------
# GET /{id} -- reflects whatever the task has persisted so far
# ---------------------------------------------------------------------------


def test_get_pending_scan_has_no_items(client, db, account):
    scan = _seed_scan(db, account, status="pending")
    r = client.get(f"/api/receipt-scan/{scan.id}")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "pending"
    assert body["items"] == []


def test_get_processed_scan_returns_real_line_items(client, db, account):
    scan = _seed_scan(
        db,
        account,
        status="processed",
        merchant_name="Maxima",
        currency="EUR",
        receipt_total=Decimal("3.49"),
    )
    db.add(
        ReceiptLineItem(
            id=uuid4(),
            receipt_scan_id=scan.id,
            line_ref="L1",
            position=0,
            raw_text="Milk 2L 3.49",
            name="Milk 2L",
            net_amount=Decimal("3.49"),
            gross_amount=Decimal("3.49"),
            discount_amount=Decimal("0"),
            kind="item",
        )
    )
    db.commit()

    r = client.get(f"/api/receipt-scan/{scan.id}")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "processed"
    assert body["merchant_name"] == "Maxima"
    assert body["currency"] == "EUR"
    assert len(body["items"]) == 1
    item = body["items"][0]
    assert item["name"] == "Milk 2L"
    assert item["line_ref"] == "L1"
    # Legacy aliasing (schemas.py) must still mirror name/net_amount onto
    # description/amount for the current frontend.
    assert item["description"] == "Milk 2L"
    assert Decimal(str(item["amount"])) == Decimal("3.49")
    assert body["validation_errors"] == []


def test_get_needs_review_scan_returns_validation_errors(client, db, account):
    scan = _seed_scan(
        db,
        account,
        status="needs_review",
        validation_errors=[
            {
                "code": "total_mismatch",
                "message": "sum(net_amount) != printed_total",
                "line_refs": ["L1"],
            }
        ],
    )
    db.add(
        ReceiptLineItem(
            id=uuid4(),
            receipt_scan_id=scan.id,
            line_ref="L1",
            position=0,
            name="Milk 2L",
            net_amount=Decimal("3.50"),
            kind="item",
        )
    )
    db.commit()

    r = client.get(f"/api/receipt-scan/{scan.id}")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "needs_review"
    assert len(body["validation_errors"]) == 1
    assert body["validation_errors"][0]["code"] == "total_mismatch"
    assert body["validation_errors"][0]["line_refs"] == ["L1"]


def test_get_failed_scan_surfaces_error_message(client, db, account):
    scan = _seed_scan(db, account, status="failed", error_message="Receipt image file not found")
    r = client.get(f"/api/receipt-scan/{scan.id}")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "failed"
    assert body["error_message"] == "Receipt image file not found"


def test_get_rejects_unknown_scan(client):
    r = client.get(f"/api/receipt-scan/{uuid4()}")
    assert r.status_code == 404


def test_get_rejects_non_owner(client, db, account):
    scan = _seed_scan(db, account)
    r = client.get(f"/api/receipt-scan/{scan.id}?user_id=u2")
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# POST /{id}/confirm -- Phase 6: takes groups, not lines. Re-runs `resolve`
# server-side and refuses a submission it doesn't match (spec 6.2).
# ---------------------------------------------------------------------------


def _category(db, name="Groceries") -> Category:
    cat = Category(id=uuid4(), user_id="u1", name=name, category_type="expense")
    db.add(cat)
    db.commit()
    return cat


def _seed_scan_with_lines(db, account, lines, **scan_overrides):
    """`lines` is a list of (line_ref, net_amount, category_id) tuples."""
    printed_total = scan_overrides.pop(
        "printed_total", sum((amount for _, amount, _ in lines), Decimal("0"))
    )
    scan = _seed_scan(
        db,
        account,
        printed_total=printed_total,
        receipt_total=printed_total,
        merchant_name=scan_overrides.pop("merchant_name", "Rimi"),
        receipt_date=scan_overrides.pop(
            "receipt_date", datetime(2026, 8, 18, 10, 0, tzinfo=timezone.utc)
        ),
        **scan_overrides,
    )
    for position, (line_ref, amount, category_id) in enumerate(lines):
        db.add(
            ReceiptLineItem(
                id=uuid4(),
                receipt_scan_id=scan.id,
                line_ref=line_ref,
                position=position,
                name=f"Item {line_ref}",
                net_amount=amount,
                gross_amount=amount,
                discount_amount=Decimal("0"),
                kind="item",
                category_id=category_id,
            )
        )
    db.commit()
    return scan


def test_confirm_creates_one_transaction_per_group(client, db, account):
    groceries = _category(db, "Groceries")
    dining = _category(db, "Dining")
    scan = _seed_scan_with_lines(
        db,
        account,
        [
            ("L1", Decimal("3.49"), groceries.id),
            ("L2", Decimal("2.99"), groceries.id),
            ("L3", Decimal("4.00"), dining.id),
        ],
        merchant_name="Some Cafe",  # not a configured grocery merchant -- no collapse
    )

    r = client.post(
        f"/api/receipt-scan/{scan.id}/confirm",
        json={
            "groups": [
                {
                    "category_id": str(groceries.id),
                    "amount": "6.48",
                    "description": "Groceries",
                    "line_refs": ["L1", "L2"],
                },
                {
                    "category_id": str(dining.id),
                    "amount": "4.00",
                    "description": "Dining",
                    "line_refs": ["L3"],
                },
            ],
        },
    )

    assert r.status_code == 200, r.text
    body = r.json()
    assert body["already_booked"] is False
    transactions = body["transactions"]
    assert len(transactions) == 2
    assert {Decimal(str(t["amount"])) for t in transactions} == {Decimal("6.48"), Decimal("4.00")}
    assert {t["category_id"] for t in transactions} == {str(groceries.id), str(dining.id)}

    db_transactions = db.query(Transaction).filter(Transaction.receipt_scan_id == scan.id).all()
    assert len(db_transactions) == 2
    assert all(t.external_id and t.external_id.startswith("receipt:") for t in db_transactions)

    # booked_at defaulted from the scan's own receipt_date. SQLite's
    # DateTime(timezone=True) doesn't actually round-trip tzinfo, so compare
    # naive -- the point of this assertion is the *value*, not the tzinfo.
    expected_booked_at = scan.receipt_date.replace(tzinfo=None)
    assert all(t.booked_at.replace(tzinfo=None) == expected_booked_at for t in db_transactions)

    # booked_transaction_id written back onto every line (spec 6.2).
    lines = db.query(ReceiptLineItem).filter(ReceiptLineItem.receipt_scan_id == scan.id).all()
    assert all(line.booked_transaction_id is not None for line in lines)

    reloaded = db.query(ReceiptScan).filter(ReceiptScan.id == scan.id).one()
    assert reloaded.status == "completed"
    assert reloaded.completed_at is not None


def test_confirm_rejects_grouping_that_does_not_match_resolve(client, db, account):
    groceries = _category(db, "Groceries")
    scan = _seed_scan_with_lines(
        db,
        account,
        [("L1", Decimal("3.49"), groceries.id)],
        merchant_name="Some Cafe",
    )

    r = client.post(
        f"/api/receipt-scan/{scan.id}/confirm",
        json={
            "groups": [
                {
                    "category_id": str(groceries.id),
                    # Wrong amount: resolve() will compute 3.49 from the
                    # actual line items, not this.
                    "amount": "99.00",
                    "description": "Groceries",
                    "line_refs": ["L1"],
                },
            ],
        },
    )
    assert r.status_code == 409, r.text
    assert "resolved" in r.json()["detail"]

    # Nothing was booked.
    assert db.query(Transaction).filter(Transaction.receipt_scan_id == scan.id).count() == 0


def test_confirm_applies_category_edit_marks_user_edited_and_regroups(client, db, account):
    groceries = _category(db, "Groceries")
    dining = _category(db, "Dining")
    scan = _seed_scan_with_lines(
        db,
        account,
        # Both lines start out categorized as groceries...
        [("L1", Decimal("20.00"), groceries.id), ("L2", Decimal("4.00"), groceries.id)],
        merchant_name="Some Cafe",
    )

    # ...but the user recategorizes L2 as Dining before confirming.
    r = client.post(
        f"/api/receipt-scan/{scan.id}/confirm",
        json={
            "groups": [
                {
                    "category_id": str(groceries.id),
                    "amount": "20.00",
                    "description": "Groceries",
                    "line_refs": ["L1"],
                },
                {
                    "category_id": str(dining.id),
                    "amount": "4.00",
                    "description": "Dining",
                    "line_refs": ["L2"],
                },
            ],
        },
    )
    assert r.status_code == 200, r.text

    l2 = (
        db.query(ReceiptLineItem)
        .filter(ReceiptLineItem.receipt_scan_id == scan.id, ReceiptLineItem.line_ref == "L2")
        .one()
    )
    assert l2.category_id == dining.id
    assert l2.user_edited is True

    l1 = (
        db.query(ReceiptLineItem)
        .filter(ReceiptLineItem.receipt_scan_id == scan.id, ReceiptLineItem.line_ref == "L1")
        .one()
    )
    assert l1.user_edited is False


def test_confirm_collapses_treats_into_groceries_at_configured_merchant(
    client, db, account, monkeypatch
):
    groceries = _category(db, "Groceries")
    dining = _category(db, "Dining")
    monkeypatch.setenv("RECEIPT_GROCERY_MERCHANTS", "rimi")
    monkeypatch.setenv("RECEIPT_GROCERY_CATEGORY_ID", str(groceries.id))
    monkeypatch.setenv("RECEIPT_TREAT_SPLIT_THRESHOLD", "5.00")

    scan = _seed_scan_with_lines(
        db,
        account,
        [("L1", Decimal("20.00"), groceries.id), ("L2", Decimal("5.00"), dining.id)],
        merchant_name="Rimi",
    )

    r = client.post(
        f"/api/receipt-scan/{scan.id}/confirm",
        json={
            "groups": [
                {
                    "category_id": str(groceries.id),
                    "amount": "25.00",
                    "description": "Rimi",
                    "line_refs": ["L1", "L2"],
                },
            ],
        },
    )
    assert r.status_code == 200, r.text
    transactions = r.json()["transactions"]
    assert len(transactions) == 1
    assert Decimal(str(transactions[0]["amount"])) == Decimal("25.00")
    assert transactions[0]["category_id"] == str(groceries.id)


def test_confirm_is_idempotent_on_resubmission(client, db, account):
    groceries = _category(db, "Groceries")
    scan = _seed_scan_with_lines(
        db, account, [("L1", Decimal("3.49"), groceries.id)], merchant_name="Some Cafe"
    )
    body = {
        "groups": [
            {
                "category_id": str(groceries.id),
                "amount": "3.49",
                "description": "Groceries",
                "line_refs": ["L1"],
            },
        ],
    }

    first = client.post(f"/api/receipt-scan/{scan.id}/confirm", json=body)
    assert first.status_code == 200, first.text
    assert first.json()["already_booked"] is False
    first_transaction_id = first.json()["transactions"][0]["id"]

    second = client.post(f"/api/receipt-scan/{scan.id}/confirm", json=body)
    assert second.status_code == 200, second.text
    assert second.json()["already_booked"] is True
    assert second.json()["transactions"][0]["id"] == first_transaction_id

    # Exactly one transaction exists -- the unique constraint on
    # (account_id, external_id) caught the duplicate insert (spec 6.3), not
    # an application-level check.
    assert db.query(Transaction).filter(Transaction.receipt_scan_id == scan.id).count() == 1


def test_confirm_is_idempotent_across_two_scans_of_the_same_receipt(client, db, account):
    """The realistic case spec 6.3 targets: two separate uploads of the same
    physical receipt (two different `ReceiptScan` rows, e.g. because the
    file_sha256 cache didn't cover it, or a retry produced a fresh scan) --
    `external_id` is computed from receipt content (fiscal_code/receipt_no,
    merchant, printed_total, category), not from `receipt_scan.id`, so it
    collides across scans just as it does across a single scan's
    resubmission."""
    groceries = _category(db, "Groceries")
    shared_fields = dict(
        merchant_name="Rimi",
        fiscal_code="FC-123",
        receipt_no="R-001",
    )
    scan_a = _seed_scan_with_lines(
        db, account, [("L1", Decimal("3.49"), groceries.id)], **shared_fields
    )
    scan_b = _seed_scan_with_lines(
        db, account, [("L1", Decimal("3.49"), groceries.id)], **shared_fields
    )

    body = {
        "groups": [
            {
                "category_id": str(groceries.id),
                "amount": "3.49",
                "description": "Groceries",
                "line_refs": ["L1"],
            },
        ],
    }

    first = client.post(f"/api/receipt-scan/{scan_a.id}/confirm", json=body)
    assert first.status_code == 200, first.text
    assert first.json()["already_booked"] is False

    second = client.post(f"/api/receipt-scan/{scan_b.id}/confirm", json=body)
    assert second.status_code == 200, second.text
    assert second.json()["already_booked"] is True
    assert second.json()["transactions"][0]["id"] == first.json()["transactions"][0]["id"]

    assert db.query(Transaction).filter(Transaction.account_id == account.id).count() == 1


def test_confirm_rejects_unknown_receipt_scan(client):
    r = client.post(
        f"/api/receipt-scan/{uuid4()}/confirm",
        json={
            "groups": [
                {"description": "x", "amount": "1.00", "line_refs": []},
            ],
            "booked_at": "2026-08-18T10:00:00Z",
        },
    )
    assert r.status_code == 404


def test_confirm_rejects_empty_groups(client, db, account):
    scan = _seed_scan(db, account)
    r = client.post(
        f"/api/receipt-scan/{scan.id}/confirm",
        json={"groups": [], "booked_at": "2026-08-18T10:00:00Z"},
    )
    assert r.status_code == 400


def test_confirm_rejects_unknown_line_ref(client, db, account):
    groceries = _category(db, "Groceries")
    scan = _seed_scan_with_lines(
        db, account, [("L1", Decimal("3.49"), groceries.id)], merchant_name="Some Cafe"
    )
    r = client.post(
        f"/api/receipt-scan/{scan.id}/confirm",
        json={
            "groups": [
                {
                    "category_id": str(groceries.id),
                    "amount": "3.49",
                    "description": "Groceries",
                    "line_refs": ["L999"],
                },
            ],
        },
    )
    assert r.status_code == 400


# ---------------------------------------------------------------------------
# GET /{id}/image -- unaffected by the async change
# ---------------------------------------------------------------------------


def test_image_endpoint_returns_bytes_for_owner(client, db, account):
    scan = _seed_scan(db, account)
    r = client.get(f"/api/receipt-scan/{scan.id}/image")
    assert r.status_code == 200, r.text
    assert r.content == TINY_PNG_BYTES
    assert r.headers["content-type"] == "image/png"


def test_image_endpoint_rejects_non_owner(client, db, account):
    scan = _seed_scan(db, account)
    r = client.get(f"/api/receipt-scan/{scan.id}/image?user_id=u2")
    assert r.status_code == 404


def test_image_endpoint_rejects_unknown_scan(client):
    r = client.get(f"/api/receipt-scan/{uuid4()}/image")
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# PATCH /{id}/lines -- Phase 6.5: the only way to correct a needs_review scan
# ---------------------------------------------------------------------------


def test_patch_lines_corrects_amount_and_flips_needs_review_to_processed(client, db, account):
    scan = _seed_scan_with_lines(
        db,
        account,
        [("L1", Decimal("9.99"), None)],
        status="needs_review",
        printed_total=Decimal("10.00"),
        currency="EUR",
        validation_errors=[{"code": "total_mismatch", "message": "mismatch", "line_refs": ["L1"]}],
    )

    r = client.patch(
        f"/api/receipt-scan/{scan.id}/lines",
        json={"edits": [{"line_ref": "L1", "net_amount": "10.00"}], "inserts": [], "deletes": []},
    )

    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "processed"
    assert body["validation_errors"] == []

    line = db.query(ReceiptLineItem).filter(ReceiptLineItem.receipt_scan_id == scan.id).one()
    assert line.net_amount == Decimal("10.00")
    # gross recomputed automatically since only net_amount was corrected.
    assert line.gross_amount == Decimal("10.00")
    assert line.user_edited is True

    reloaded = db.query(ReceiptScan).filter(ReceiptScan.id == scan.id).one()
    assert reloaded.status == "processed"
    assert reloaded.validation_errors is None


def test_patch_lines_flips_processed_back_to_needs_review_on_bad_edit(client, db, account):
    scan = _seed_scan_with_lines(
        db,
        account,
        [("L1", Decimal("10.00"), None)],
        status="processed",
        printed_total=Decimal("10.00"),
        currency="EUR",
    )

    r = client.patch(
        f"/api/receipt-scan/{scan.id}/lines",
        json={"edits": [{"line_ref": "L1", "net_amount": "9.00"}], "inserts": [], "deletes": []},
    )

    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "needs_review"
    assert any(e["code"] == "total_mismatch" for e in body["validation_errors"])

    reloaded = db.query(ReceiptScan).filter(ReceiptScan.id == scan.id).one()
    assert reloaded.status == "needs_review"


def test_patch_lines_rejects_completed_scan(client, db, account):
    scan = _seed_scan_with_lines(
        db,
        account,
        [("L1", Decimal("10.00"), None)],
        status="completed",
        printed_total=Decimal("10.00"),
        currency="EUR",
    )

    r = client.patch(
        f"/api/receipt-scan/{scan.id}/lines",
        json={"edits": [{"line_ref": "L1", "net_amount": "9.00"}], "inserts": [], "deletes": []},
    )
    assert r.status_code == 409


def test_patch_lines_insert_assigns_line_ref_server_side_and_reconciles(client, db, account):
    scan = _seed_scan_with_lines(
        db,
        account,
        [("L1", Decimal("9.00"), None)],
        status="needs_review",
        printed_total=Decimal("10.00"),
        currency="EUR",
    )

    r = client.patch(
        f"/api/receipt-scan/{scan.id}/lines",
        json={
            "edits": [],
            "inserts": [{"name": "Missed item", "net_amount": "1.00"}],
            "deletes": [],
        },
    )

    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "processed"
    refs = {item["line_ref"] for item in body["items"]}
    assert refs == {"L1", "L2"}
    inserted = next(item for item in body["items"] if item["line_ref"] == "L2")
    assert inserted["name"] == "Missed item"
    assert Decimal(str(inserted["net_amount"])) == Decimal("1.00")
    assert inserted["user_edited"] is True

    # A client cannot pick its own line_ref -- it is never accepted as input
    # in the first place (ReceiptLineInsertSchema has no such field), so the
    # server-assignment guarantee is structural, not just behavioural.


def test_patch_lines_delete_cascades_onto_orphaned_deposit(client, db, account):
    scan = _seed_scan_with_lines(
        db,
        account,
        [("L1", Decimal("8.00"), None)],
        status="processed",
        printed_total=Decimal("10.00"),
        currency="EUR",
    )
    db.add(
        ReceiptLineItem(
            id=uuid4(),
            receipt_scan_id=scan.id,
            line_ref="L2",
            position=1,
            name="Bottle deposit",
            net_amount=Decimal("2.00"),
            gross_amount=Decimal("2.00"),
            discount_amount=Decimal("0"),
            kind="deposit",
            parent_line_ref="L1",
        )
    )
    db.commit()

    r = client.patch(
        f"/api/receipt-scan/{scan.id}/lines",
        json={"edits": [], "inserts": [], "deletes": ["L1"]},
    )

    assert r.status_code == 200, r.text
    body = r.json()
    refs = {item["line_ref"] for item in body["items"]}
    assert refs == set()  # both L1 (deleted directly) and L2 (cascaded) gone

    remaining = db.query(ReceiptLineItem).filter(ReceiptLineItem.receipt_scan_id == scan.id).all()
    assert remaining == []


def test_patch_lines_rejects_edit_and_delete_of_same_line_ref(client, db, account):
    scan = _seed_scan_with_lines(
        db,
        account,
        [("L1", Decimal("10.00"), None)],
        status="processed",
        printed_total=Decimal("10.00"),
        currency="EUR",
    )

    r = client.patch(
        f"/api/receipt-scan/{scan.id}/lines",
        json={
            "edits": [{"line_ref": "L1", "net_amount": "5.00"}],
            "inserts": [],
            "deletes": ["L1"],
        },
    )
    assert r.status_code == 400


def test_patch_lines_rejects_unknown_line_ref_on_edit(client, db, account):
    scan = _seed_scan_with_lines(
        db,
        account,
        [("L1", Decimal("10.00"), None)],
        status="processed",
        printed_total=Decimal("10.00"),
        currency="EUR",
    )
    r = client.patch(
        f"/api/receipt-scan/{scan.id}/lines",
        json={"edits": [{"line_ref": "L9", "net_amount": "5.00"}], "inserts": [], "deletes": []},
    )
    assert r.status_code == 404


def test_patch_lines_rejects_unknown_line_ref_on_delete(client, db, account):
    scan = _seed_scan_with_lines(
        db,
        account,
        [("L1", Decimal("10.00"), None)],
        status="processed",
        printed_total=Decimal("10.00"),
        currency="EUR",
    )
    r = client.patch(
        f"/api/receipt-scan/{scan.id}/lines",
        json={"edits": [], "inserts": [], "deletes": ["L9"]},
    )
    assert r.status_code == 404


def test_patch_lines_rejects_insert_with_unknown_parent(client, db, account):
    scan = _seed_scan_with_lines(
        db,
        account,
        [("L1", Decimal("10.00"), None)],
        status="processed",
        printed_total=Decimal("10.00"),
        currency="EUR",
    )
    r = client.patch(
        f"/api/receipt-scan/{scan.id}/lines",
        json={
            "edits": [],
            "inserts": [
                {
                    "name": "Deposit",
                    "net_amount": "1.00",
                    "kind": "deposit",
                    "parent_line_ref": "L9",
                }
            ],
            "deletes": [],
        },
    )
    assert r.status_code == 400


def test_patch_lines_rejects_non_owner(client, db, account):
    scan = _seed_scan_with_lines(
        db,
        account,
        [("L1", Decimal("10.00"), None)],
        status="processed",
        printed_total=Decimal("10.00"),
        currency="EUR",
    )
    r = client.patch(
        f"/api/receipt-scan/{scan.id}/lines?user_id=u2",
        json={"edits": [{"line_ref": "L1", "net_amount": "5.00"}], "inserts": [], "deletes": []},
    )
    assert r.status_code == 404


def test_needs_review_correction_to_processed_to_confirm_round_trip(client, db, account):
    """The single most important behaviour this phase adds: a scan that
    lands in needs_review because its lines sum to printed_total - 0.01 can
    be corrected, flips to processed, and then books successfully end to
    end -- the exact round trip the pre-6.5 dead end made impossible."""
    groceries = _category(db, "Groceries")
    scan = _seed_scan_with_lines(
        db,
        account,
        [("L1", Decimal("9.99"), groceries.id)],
        status="needs_review",
        printed_total=Decimal("10.00"),
        currency="EUR",
        merchant_name="Some Cafe",
        validation_errors=[{"code": "total_mismatch", "message": "mismatch", "line_refs": ["L1"]}],
    )

    patch_r = client.patch(
        f"/api/receipt-scan/{scan.id}/lines",
        json={"edits": [{"line_ref": "L1", "net_amount": "10.00"}], "inserts": [], "deletes": []},
    )
    assert patch_r.status_code == 200, patch_r.text
    assert patch_r.json()["status"] == "processed"

    confirm_r = client.post(
        f"/api/receipt-scan/{scan.id}/confirm",
        json={
            "groups": [
                {
                    "category_id": str(groceries.id),
                    "amount": "10.00",
                    "description": "Groceries",
                    "line_refs": ["L1"],
                },
            ],
        },
    )
    assert confirm_r.status_code == 200, confirm_r.text
    body = confirm_r.json()
    assert body["already_booked"] is False
    assert len(body["transactions"]) == 1
    assert Decimal(str(body["transactions"][0]["amount"])) == Decimal("10.00")

    reloaded = db.query(ReceiptScan).filter(ReceiptScan.id == scan.id).one()
    assert reloaded.status == "completed"
