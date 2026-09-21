from datetime import date
from decimal import Decimal
from uuid import uuid4

import pytest

from app.models import (
    User,
    Account,
    Holding,
    HoldingValuation,
)
from app.mcp.tools import investments as inv_tools


@pytest.fixture
def db(db_session):
    """The shared Postgres session from conftest.

    These tests used to build their own in-memory SQLite schema from a
    hand-picked subset of models. That stopped working once the models grew
    JSONB and UUID columns SQLite cannot compile, and it tested against a
    schema that was never the real one. conftest truncates between tests, so
    the shared session is just as isolated.
    """
    return db_session


def test_list_holdings_returns_per_account_holdings(db):
    user = User(id="u1", email="u@example.com", functional_currency="EUR")
    acc = Account(
        id=uuid4(), user_id="u1", name="m", account_type="investment_manual", currency="EUR"
    )
    h = Holding(
        id=uuid4(),
        user_id="u1",
        account_id=acc.id,
        symbol="AAPL",
        currency="USD",
        instrument_type="equity",
        quantity=Decimal("10"),
        source="manual",
    )
    # Parents first: these models declare foreign keys but no relationships,
    # so the flush order is not dependency-sorted for us.
    db.add(user)
    db.flush()
    db.add(acc)
    db.flush()
    db.add(h)
    db.flush()
    db.add(
        HoldingValuation(
            holding_id=h.id,
            date=date(2026, 4, 18),
            quantity=Decimal("10"),
            price=Decimal("234.56"),
            value_user_currency=Decimal("2199.07"),
            is_stale=False,
        )
    )
    db.commit()
    out = inv_tools.list_holdings_impl(db=db, user_id="u1")
    assert len(out) == 1
    assert out[0]["symbol"] == "AAPL"
    assert out[0]["current_value_user_currency"] == "2199.07"


def test_get_portfolio_summary_aggregates(db):
    user = User(id="u1", email="u@example.com", functional_currency="EUR")
    a1 = Account(
        id=uuid4(),
        user_id="u1",
        name="m",
        account_type="investment_manual",
        currency="EUR",
        is_active=True,
    )
    a2 = Account(
        id=uuid4(),
        user_id="u1",
        name="b",
        account_type="investment_manual",
        currency="EUR",
        is_active=True,
    )
    h1 = Holding(
        id=uuid4(),
        user_id="u1",
        account_id=a1.id,
        symbol="X",
        currency="EUR",
        instrument_type="equity",
        quantity=Decimal("1"),
        source="manual",
    )
    h2 = Holding(
        id=uuid4(),
        user_id="u1",
        account_id=a2.id,
        symbol="Y",
        currency="EUR",
        instrument_type="equity",
        quantity=Decimal("1"),
        source="manual",
    )
    # Parents first: these models declare foreign keys but no relationships,
    # so the flush order is not dependency-sorted for us.
    db.add(user)
    db.flush()
    db.add_all([a1, a2])
    db.flush()
    db.add_all([h1, h2])
    db.flush()
    db.add(
        HoldingValuation(
            holding_id=h1.id,
            date=date(2026, 4, 18),
            quantity=Decimal("1"),
            price=Decimal("100"),
            value_user_currency=Decimal("100"),
        )
    )
    db.add(
        HoldingValuation(
            holding_id=h2.id,
            date=date(2026, 4, 18),
            quantity=Decimal("1"),
            price=Decimal("200"),
            value_user_currency=Decimal("200"),
        )
    )
    db.commit()
    out = inv_tools.get_portfolio_summary_impl(db=db, user_id="u1")
    assert Decimal(out["total_value"]) == Decimal("300")
    assert out["currency"] == "EUR"
