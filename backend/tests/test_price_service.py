from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.database import Base
from app.models import PriceSnapshot
from app.services.price_service import PriceService
from app.integrations.price_provider.base import PriceQuote


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    # Only create tables that work with SQLite (no JSONB etc.)
    PriceSnapshot.__table__.create(bind=engine)
    with Session(engine) as session:
        yield session


def test_returns_cached_snapshot_without_calling_provider(db):
    db.add(PriceSnapshot(symbol="AAPL", currency="USD", date=date(2026, 4, 18),
                         close=Decimal("234.56"), provider="yahoo"))
    db.commit()
    provider = MagicMock()
    svc = PriceService(db=db, provider=provider)
    out = svc.get_or_fetch(["AAPL"], date(2026, 4, 18))
    assert out["AAPL"].close == Decimal("234.56")
    provider.get_daily_closes.assert_not_called()


def test_fetches_missing_and_persists(db):
    provider = MagicMock()
    provider.get_daily_closes.return_value = {
        "MSFT": PriceQuote("MSFT", "USD", date(2026, 4, 18), Decimal("410.10")),
    }
    provider.name = "yahoo"
    svc = PriceService(db=db, provider=provider)
    out = svc.get_or_fetch(["MSFT"], date(2026, 4, 18))
    assert out["MSFT"].close == Decimal("410.10")
    persisted = db.query(PriceSnapshot).filter_by(symbol="MSFT").one()
    assert persisted.close == Decimal("410.10")
    assert persisted.provider == "yahoo"


def test_partial_miss(db):
    db.add(PriceSnapshot(symbol="AAPL", currency="USD", date=date(2026, 4, 18),
                         close=Decimal("234.56"), provider="yahoo"))
    db.commit()
    provider = MagicMock()
    provider.get_daily_closes.return_value = {
        "MSFT": PriceQuote("MSFT", "USD", date(2026, 4, 18), Decimal("410.10")),
    }
    provider.name = "yahoo"
    svc = PriceService(db=db, provider=provider)
    out = svc.get_or_fetch(["AAPL", "MSFT"], date(2026, 4, 18))
    assert set(out.keys()) == {"AAPL", "MSFT"}
    provider.get_daily_closes.assert_called_once_with(["MSFT"], date(2026, 4, 18))
