"""Tests for ExchangeRateService.get_exchange_rate_with_fallback."""
from datetime import date
from decimal import Decimal
from unittest.mock import patch

import pytest

from app.models import ExchangeRate
from app.services.exchange_rate_service import ExchangeRateService


@pytest.fixture(autouse=True)
def _isolate_fx_rates(db_session):
    """ExchangeRate rows are committed in these tests; isolate per-test."""
    db_session.query(ExchangeRate).delete()
    db_session.commit()
    yield
    db_session.query(ExchangeRate).delete()
    db_session.commit()


@pytest.fixture
def fx_svc(db_session):
    return ExchangeRateService(db=db_session)


def _put_rate(db_session, base, target, on, value):
    from datetime import datetime
    db_session.add(
        ExchangeRate(
            date=datetime.combine(on, datetime.min.time()),
            base_currency=base,
            target_currency=target,
            rate=Decimal(str(value)),
        )
    )
    db_session.commit()


def test_fallback_returns_db_rate_when_present(fx_svc, db_session):
    _put_rate(db_session, "USD", "EUR", date(2024, 1, 3), "0.91")
    got = fx_svc.get_exchange_rate_with_fallback("USD", "EUR", date(2024, 1, 3))
    assert got == Decimal("0.91")


def test_fallback_uses_yfinance_when_db_missing_at_as_of_date(fx_svc, db_session):
    """When the DB has no rate for the target date, we fetch from yfinance and store it."""
    target = date(2024, 1, 3)

    fake_fetch = {
        target: {"EUR": Decimal("0.9123")},
    }

    with patch.object(fx_svc, "fetch_exchange_rates_batch", return_value=fake_fetch) as m:
        got = fx_svc.get_exchange_rate_with_fallback("USD", "EUR", target)

    assert got == Decimal("0.9123")
    m.assert_called_once()
    # And it was stored.
    stored = (
        db_session.query(ExchangeRate)
        .filter(ExchangeRate.base_currency == "USD", ExchangeRate.target_currency == "EUR")
        .all()
    )
    assert len(stored) == 1
    assert stored[0].rate == Decimal("0.9123")


def test_fallback_uses_today_when_db_and_yfinance_miss_target_date(fx_svc, db_session):
    """If yfinance returns nothing for the target date, use today's rate."""
    today = date.today()
    target = date(2020, 6, 1)  # ancient date, no DB row, no yfinance result

    _put_rate(db_session, "USD", "EUR", today, "0.88")

    with patch.object(fx_svc, "fetch_exchange_rates_batch", return_value={}):
        got = fx_svc.get_exchange_rate_with_fallback("USD", "EUR", target)

    assert got == Decimal("0.88")


def test_fallback_returns_none_when_everything_misses(fx_svc, db_session):
    """If all paths fail (no DB, no yfinance, no current rate), return None."""
    with patch.object(fx_svc, "fetch_exchange_rates_batch", return_value={}), \
         patch.object(fx_svc, "fetch_current_exchange_rates", return_value={}):
        got = fx_svc.get_exchange_rate_with_fallback("USD", "EUR", date(2020, 6, 1))

    assert got is None


def test_fallback_short_circuits_when_currencies_equal(fx_svc):
    got = fx_svc.get_exchange_rate_with_fallback("USD", "USD", date(2024, 1, 3))
    assert got == Decimal("1.0")
