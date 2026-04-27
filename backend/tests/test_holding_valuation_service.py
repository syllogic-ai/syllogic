from datetime import date, datetime
from decimal import Decimal
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.models import (
    Account, Holding, PriceSnapshot, HoldingValuation,
    AccountBalance, User,
)
from app.services.holding_valuation_service import HoldingValuationService


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    # Create only tables we need — Base.metadata.create_all chokes on JSONB elsewhere.
    User.__table__.create(bind=engine)
    Account.__table__.create(bind=engine)
    Holding.__table__.create(bind=engine)
    PriceSnapshot.__table__.create(bind=engine)
    HoldingValuation.__table__.create(bind=engine)
    AccountBalance.__table__.create(bind=engine)
    with Session(engine) as session:
        yield session


def _make_user(db, currency="EUR"):
    user = User(id="u1", email="u@example.com", functional_currency=currency)
    db.add(user)
    db.commit()
    return user


def _make_account(db, user_id, currency="EUR", account_type="investment_manual"):
    a = Account(id=uuid4(), user_id=user_id, name="Brokerage", account_type=account_type, currency=currency)
    db.add(a); db.commit()
    return a


def test_computes_valuation_for_equity_in_user_currency(db):
    user = _make_user(db, currency="EUR")
    acc = _make_account(db, user.id, currency="EUR")
    h = Holding(id=uuid4(), user_id=user.id, account_id=acc.id, symbol="AAPL",
                currency="USD", instrument_type="equity",
                quantity=Decimal("10"), source="manual")
    db.add(h)
    db.add(PriceSnapshot(symbol="AAPL", currency="USD", date=date(2026, 4, 18),
                         close=Decimal("234.56"), provider="yahoo"))
    db.commit()

    fx = MagicMock()
    fx.convert.return_value = Decimal("2199.07")
    svc = HoldingValuationService(db=db, fx=fx)
    svc.compute(account_id=acc.id, on=date(2026, 4, 18))

    val = db.query(HoldingValuation).filter_by(holding_id=h.id, date=date(2026, 4, 18)).one()
    assert val.value_user_currency == Decimal("2199.07")
    assert val.is_stale is False

    bal = db.query(AccountBalance).filter_by(account_id=acc.id).one()
    assert bal.balance_in_functional_currency == Decimal("2199.07")
    assert bal.balance_in_account_currency == Decimal("2199.07")  # account currency == functional


def test_cash_holding_skips_price_lookup(db):
    user = _make_user(db, currency="EUR")
    acc = _make_account(db, user.id, currency="EUR")
    h = Holding(id=uuid4(), user_id=user.id, account_id=acc.id, symbol="USD",
                currency="USD", instrument_type="cash",
                quantity=Decimal("1500"), source="ibkr_flex")
    db.add(h); db.commit()

    fx = MagicMock()
    fx.convert.return_value = Decimal("1380.00")
    svc = HoldingValuationService(db=db, fx=fx)
    svc.compute(account_id=acc.id, on=date(2026, 4, 18))

    val = db.query(HoldingValuation).filter_by(holding_id=h.id).one()
    assert val.price == Decimal("1")
    assert val.value_user_currency == Decimal("1380.00")


def test_does_not_mark_stale_within_freshness_window(db):
    """Snapshot from up to 3 days ago is fresh — covers weekend / 1-day holiday."""
    user = _make_user(db, currency="EUR")
    acc = _make_account(db, user.id, currency="EUR")
    h = Holding(id=uuid4(), user_id=user.id, account_id=acc.id, symbol="AAPL",
                currency="USD", instrument_type="equity",
                quantity=Decimal("10"), source="manual")
    db.add(h)
    # Snapshot 3 days before `on` — on the boundary, still fresh.
    db.add(PriceSnapshot(symbol="AAPL", currency="USD", date=date(2026, 4, 15),
                         close=Decimal("230.00"), provider="yahoo"))
    db.commit()
    fx = MagicMock(); fx.convert.return_value = Decimal("2100.00")
    HoldingValuationService(db=db, fx=fx).compute(account_id=acc.id, on=date(2026, 4, 18))
    val = db.query(HoldingValuation).filter_by(holding_id=h.id, date=date(2026, 4, 18)).one()
    assert val.is_stale is False


def test_marks_stale_when_snapshot_older_than_window(db):
    """Snapshot more than 3 days old is stale."""
    user = _make_user(db, currency="EUR")
    acc = _make_account(db, user.id, currency="EUR")
    h = Holding(id=uuid4(), user_id=user.id, account_id=acc.id, symbol="AAPL",
                currency="USD", instrument_type="equity",
                quantity=Decimal("10"), source="manual")
    db.add(h)
    # Snapshot 4 days before `on` — outside the freshness window.
    db.add(PriceSnapshot(symbol="AAPL", currency="USD", date=date(2026, 4, 14),
                         close=Decimal("230.00"), provider="yahoo"))
    db.commit()
    fx = MagicMock(); fx.convert.return_value = Decimal("2100.00")
    HoldingValuationService(db=db, fx=fx).compute(account_id=acc.id, on=date(2026, 4, 18))
    val = db.query(HoldingValuation).filter_by(holding_id=h.id, date=date(2026, 4, 18)).one()
    assert val.is_stale is True
