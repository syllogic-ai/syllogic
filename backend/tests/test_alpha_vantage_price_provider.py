from datetime import date
from decimal import Decimal
from unittest.mock import patch, MagicMock

from app.integrations.price_provider.alpha_vantage_provider import (
    AlphaVantagePriceProvider,
)


def _ts_daily_response(rows):
    """Build a fake TIME_SERIES_DAILY response. rows = [(YYYY-MM-DD, close)]"""
    return {
        "Meta Data": {"2. Symbol": "AAPL"},
        "Time Series (Daily)": {
            d: {
                "1. open": "0",
                "2. high": "0",
                "3. low": "0",
                "4. close": str(c),
                "5. volume": "0",
            }
            for d, c in rows
        },
    }


def _overview_response(currency="USD"):
    return {"Symbol": "AAPL", "Currency": currency}


def test_get_daily_close_returns_quote_for_exact_date():
    ts = _ts_daily_response([("2026-04-18", "234.56")])
    overview = _overview_response("USD")
    with patch(
        "app.integrations.price_provider.alpha_vantage_provider.httpx.get"
    ) as get:
        get.side_effect = [
            MagicMock(json=lambda: ts, raise_for_status=lambda: None),
            MagicMock(json=lambda: overview, raise_for_status=lambda: None),
        ]
        q = AlphaVantagePriceProvider(api_key="X").get_daily_close(
            "AAPL", date(2026, 4, 18)
        )
    assert q is not None
    assert q.symbol == "AAPL"
    assert q.currency == "USD"
    assert q.close == Decimal("234.56")
    assert q.date == date(2026, 4, 18)
