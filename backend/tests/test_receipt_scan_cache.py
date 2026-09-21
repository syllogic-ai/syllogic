"""Tests for the `file_sha256` extraction cache (Phase 6.4). See
docs/specs/receipt-ingestion-implementation.md 6.4 and its Phase 6
checkpoint:

- the same file uploaded twice produces one processed extraction, and the
  second upload skips stage 1 entirely (asserted on the `extract_receipt`
  provider-call mock's call count, and on which Celery task got enqueued);
- a hash match belonging to a different user must NOT hit the cache.

These run the real Celery tasks synchronously via `.apply()` (matching
`test_receipt_tasks.py`'s pattern) against the extract route's own
in-memory sqlite session, so the skip is proven end-to-end rather than by
asserting on the route's internals alone. `receipt_extract.extract_receipt`
(stage 1's vision/provider call) is mocked throughout -- no real model call
is made or could be, there is no API key in this environment. Stage 2
(categorization) is exercised for real logic (`categorize_receipt_lines`)
but the test users have no categories, so it fails fast on the
"no expense categories" check before ever reaching the LLM client -- no
categorization provider call happens in this file either.
"""

import base64
import hashlib
import hmac
import json
import time
from contextlib import contextmanager
from decimal import Decimal
from unittest.mock import patch
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import DefaultClause, create_engine, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.database import get_db
from app.main import app
from app.models import Account, Category, ReceiptLineItem, ReceiptScan, Transaction, User
from app.services.receipt_extract import ExtractedLine, ExtractedReceipt
from tasks.receipt_tasks import categorize_receipt_task, extract_receipt_task


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


INTERNAL_AUTH_SECRET = "test-internal-secret"

TINY_PNG_B64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)
TINY_PNG_BYTES = base64.b64decode(TINY_PNG_B64)


def _extract_path(account_id, content_type: str = "image/png", user_id: str | None = None) -> str:
    path = f"/api/receipt-scan/extract?account_id={account_id}&content_type={content_type}"
    if user_id:
        path += f"&user_id={user_id}"
    return path


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


@pytest.fixture
def db():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    models = (User, Account, Category, ReceiptScan, Transaction, ReceiptLineItem)
    with _sqlite_safe_server_defaults(*models):
        for model in models:
            model.__table__.create(bind=engine)
    with Session(engine, expire_on_commit=False) as session:
        yield session


@pytest.fixture
def client(db, monkeypatch, tmp_path):
    monkeypatch.setenv("INTERNAL_AUTH_SECRET", INTERNAL_AUTH_SECRET)
    monkeypatch.setenv("LOCAL_STORAGE_PATH", str(tmp_path))
    db.add(User(id="u1", email="u1@example.com", functional_currency="EUR"))
    db.add(User(id="u2", email="u2@example.com", functional_currency="EUR"))
    db.commit()
    app.dependency_overrides[get_db] = lambda: db
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


@pytest.fixture
def account_u2(db):
    acc = Account(
        id=uuid4(), user_id="u2", name="Checking", account_type="checking", currency="EUR"
    )
    db.add(acc)
    db.commit()
    return acc


def _clean_receipt() -> ExtractedReceipt:
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
        extraction_model="gpt-4o-mini",
    )


def _run_extract_task(db, receipt_scan_id):
    with patch("tasks.receipt_tasks.SessionLocal", return_value=db):
        return extract_receipt_task.apply(args=[str(receipt_scan_id)]).get()


def _run_categorize_task(db, receipt_scan_id):
    with patch("tasks.receipt_tasks.SessionLocal", return_value=db):
        return categorize_receipt_task.apply(args=[str(receipt_scan_id)]).get()


def test_second_upload_of_same_file_skips_stage_one(client, db, account):
    # Captured before any task runs: the task's own `finally: db.close()`
    # (patched to run against this same shared session) detaches every
    # object still attached to it, `account` included -- see
    # test_receipt_tasks.py's `_reload` docstring for the same gotcha.
    account_id = account.id

    with patch(
        "tasks.receipt_tasks.extract_receipt", return_value=_clean_receipt()
    ) as mock_extract:
        # First upload: no cache source yet -- stage 1 is enqueued for real.
        with patch("tasks.receipt_tasks.extract_receipt_task.delay") as mock_extract_delay:
            first = client.post(_extract_path(account_id), content=TINY_PNG_BYTES)
        assert first.status_code == 202, first.text
        mock_extract_delay.assert_called_once()
        first_scan_id = first.json()["receipt_scan_id"]

        # Actually run stage 1 (synchronously, via .apply()) so the scan
        # reaches `processed` and becomes a valid cache source.
        _run_extract_task(db, first_scan_id)
        first_scan = db.query(ReceiptScan).filter(ReceiptScan.id == UUID(first_scan_id)).one()
        assert first_scan.status == "processed"
        assert mock_extract.call_count == 1

        # Second upload of the exact same bytes, same user: must hit the
        # cache -- extract_receipt_task is never enqueued, only
        # categorize_receipt_task is.
        with (
            patch("tasks.receipt_tasks.extract_receipt_task.delay") as mock_extract_delay_2,
            patch("tasks.receipt_tasks.categorize_receipt_task.delay") as mock_categorize_delay,
        ):
            second = client.post(_extract_path(account_id), content=TINY_PNG_BYTES)
        assert second.status_code == 202, second.text
        mock_extract_delay_2.assert_not_called()
        mock_categorize_delay.assert_called_once()

        second_body = second.json()
        second_scan_id = second_body["receipt_scan_id"]
        assert second_scan_id != first_scan_id
        # Header + lines were copied synchronously -- already reflected in
        # the response, no polling needed.
        assert second_body["status"] == "processed"
        assert second_body["merchant_name"] == "Test Store"
        assert len(second_body["items"]) == 1
        assert second_body["items"][0]["name"] == "Milk 2L"

        # Copied lines start uncategorized -- stage 2 hasn't run yet.
        assert second_body["items"][0]["category_id"] is None

        # Running stage 2 for real must not touch stage 1 at all.
        _run_categorize_task(db, second_scan_id)
        assert mock_extract.call_count == 1

    db_transactions_count = db.query(ReceiptLineItem).count()
    # 1 line copied onto each of the two scans.
    assert db_transactions_count == 2


def test_hash_match_for_different_user_does_not_hit_cache(client, db, account, account_u2):
    account_id = account.id
    account_u2_id = account_u2.id

    with patch("tasks.receipt_tasks.extract_receipt", return_value=_clean_receipt()):
        with patch("tasks.receipt_tasks.extract_receipt_task.delay"):
            u2_response = client.post(
                _extract_path(account_u2_id, user_id="u2"), content=TINY_PNG_BYTES
            )
        assert u2_response.status_code == 202, u2_response.text
        u2_scan_id = u2_response.json()["receipt_scan_id"]
        _run_extract_task(db, u2_scan_id)
        u2_scan = db.query(ReceiptScan).filter(ReceiptScan.id == UUID(u2_scan_id)).one()
        assert u2_scan.status == "processed"
        assert u2_scan.file_sha256 == hashlib.sha256(TINY_PNG_BYTES).hexdigest()

        # u1 uploads the exact same bytes -- same file_sha256, different
        # user. Must NOT hit u2's cached extraction.
        with (
            patch("tasks.receipt_tasks.extract_receipt_task.delay") as mock_extract_delay,
            patch("tasks.receipt_tasks.categorize_receipt_task.delay") as mock_categorize_delay,
        ):
            u1_response = client.post(
                _extract_path(account_id, user_id="u1"), content=TINY_PNG_BYTES
            )
        assert u1_response.status_code == 202, u1_response.text
        mock_extract_delay.assert_called_once()
        mock_categorize_delay.assert_not_called()

        body = u1_response.json()
        assert body["status"] == "pending"
        assert body["items"] == []
