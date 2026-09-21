"""Tests for Phase 2 of the receipt-ingestion rework -- see
docs/specs/receipt-ingestion-implementation.md "Phase 2 -- Schema".

Covers the ReceiptLineItem model's cascade behaviour at the ORM level and the
ReceiptLineItemSchema description/amount <-> name/net_amount aliasing that
keeps the frontend's toReceiptLineItem parsing for one more release.

Uses a minimal SQLite in-memory engine (only the tables under test), the same
pattern as test_receipt_scan_routes.py -- these models don't carry a JSONB
column that needs the sqlite compile shim from that file.
"""

from contextlib import contextmanager
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import DefaultClause, create_engine, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.models import Account, Category, ReceiptLineItem, ReceiptScan, Transaction, User
from app.schemas import ReceiptLineItemSchema


# Account.alias_patterns is a plain (Postgres) JSONB column, unrelated to
# receipt ingestion, that SQLite's DDL compiler cannot render at all -- table
# creation raises `CompileError` without this shim. Same fix as
# test_receipt_scan_routes.py, duplicated here rather than shared: it's a
# per-module workaround for a pre-existing column, not part of this phase.
@compiles(JSONB, "sqlite")
def _jsonb_as_text_on_sqlite(element, compiler, **kw):
    return "TEXT"


@contextmanager
def _sqlite_safe_server_defaults(*models):
    """Strip `'[]'::jsonb`-style Postgres casts from server defaults so
    `Table.create()` succeeds on the in-memory SQLite engine."""
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


def _make_session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    models = (User, Account, Category, ReceiptScan, Transaction, ReceiptLineItem)
    with _sqlite_safe_server_defaults(*models):
        for model in models:
            model.__table__.create(bind=engine)
    return Session(engine)


def _seed_scan(db):
    db.add(User(id="u1", email="u@example.com", functional_currency="EUR"))
    db.commit()
    account = Account(
        id=uuid4(), user_id="u1", name="Checking", account_type="checking", currency="EUR"
    )
    db.add(account)
    db.commit()
    scan = ReceiptScan(id=uuid4(), user_id="u1", account_id=account.id, status="processed")
    db.add(scan)
    db.commit()
    return scan


def test_deleting_a_scan_deletes_its_line_items():
    db = _make_session()
    scan = _seed_scan(db)
    scan.line_items.append(
        ReceiptLineItem(
            id=uuid4(), line_ref="L1", position=0, name="Milk", net_amount=Decimal("3.49")
        )
    )
    scan.line_items.append(
        ReceiptLineItem(
            id=uuid4(), line_ref="L2", position=1, name="Bread", net_amount=Decimal("2.99")
        )
    )
    db.commit()

    scan_id = scan.id
    assert db.query(ReceiptLineItem).filter_by(receipt_scan_id=scan_id).count() == 2

    db.delete(scan)
    db.commit()

    assert db.query(ReceiptLineItem).filter_by(receipt_scan_id=scan_id).count() == 0


def test_line_items_are_ordered_by_position():
    db = _make_session()
    scan = _seed_scan(db)
    scan.line_items.append(ReceiptLineItem(id=uuid4(), line_ref="L2", position=1, name="Bread"))
    scan.line_items.append(ReceiptLineItem(id=uuid4(), line_ref="L1", position=0, name="Milk"))
    db.commit()
    db.refresh(scan)

    assert [item.name for item in scan.line_items] == ["Milk", "Bread"]


def test_schema_description_amount_are_aliases_of_name_net_amount():
    # Phase 4 extraction is expected to set name/net_amount; description/amount
    # must still come through for the frontend's toReceiptLineItem.
    item = ReceiptLineItemSchema(name="Milk 2L", net_amount=Decimal("3.49"))
    assert item.description == "Milk 2L"
    assert item.amount == Decimal("3.49")


def test_schema_name_net_amount_are_aliases_of_description_amount():
    # A pre-Phase-4 caller setting the legacy description/amount fields directly.
    item = ReceiptLineItemSchema(description="Milk 2L", amount=Decimal("3.49"))
    assert item.name == "Milk 2L"
    assert item.net_amount == Decimal("3.49")


def test_schema_explicit_values_are_not_overwritten():
    item = ReceiptLineItemSchema(
        name="Milk 2L", net_amount=Decimal("3.49"), description="Milk", amount=Decimal("3.50")
    )
    assert item.description == "Milk"
    assert item.amount == Decimal("3.50")
