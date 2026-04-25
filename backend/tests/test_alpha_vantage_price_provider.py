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


def test_get_daily_close_falls_back_to_most_recent_prior_close():
    ts = _ts_daily_response([
        ("2026-04-15", "230.00"),
        ("2026-04-16", "231.00"),
        ("2026-04-17", "232.00"),
    ])
    with patch(
        "app.integrations.price_provider.alpha_vantage_provider.httpx.get"
    ) as get:
        get.side_effect = [
            MagicMock(json=lambda: ts, raise_for_status=lambda: None),
            MagicMock(json=lambda: _overview_response("USD"), raise_for_status=lambda: None),
        ]
        # Asking for Saturday — should pick Friday 2026-04-17
        q = AlphaVantagePriceProvider(api_key="X").get_daily_close(
            "AAPL", date(2026, 4, 18)
        )
    assert q is not None
    assert q.date == date(2026, 4, 17)
    assert q.close == Decimal("232.00")


def test_get_daily_close_returns_none_when_no_data():
    with patch(
        "app.integrations.price_provider.alpha_vantage_provider.httpx.get"
    ) as get:
        get.return_value = MagicMock(
            json=lambda: {"Time Series (Daily)": {}},
            raise_for_status=lambda: None,
        )
        q = AlphaVantagePriceProvider(api_key="X").get_daily_close(
            "ZZZZ", date(2026, 4, 18)
        )
    assert q is None


def test_get_daily_close_returns_none_on_rate_limit():
    with patch(
        "app.integrations.price_provider.alpha_vantage_provider.httpx.get"
    ) as get:
        get.return_value = MagicMock(
            json=lambda: {"Note": "Rate limit reached"},
            raise_for_status=lambda: None,
        )
        q = AlphaVantagePriceProvider(api_key="X").get_daily_close(
            "AAPL", date(2026, 4, 18)
        )
    assert q is None


def test_currency_cached_across_calls():
    ts = _ts_daily_response([("2026-04-18", "100.00")])
    with patch(
        "app.integrations.price_provider.alpha_vantage_provider.httpx.get"
    ) as get:
        # 4 calls expected: TS, OVERVIEW, TS, (no second OVERVIEW because cached)
        get.side_effect = [
            MagicMock(json=lambda: ts, raise_for_status=lambda: None),
            MagicMock(json=lambda: _overview_response("EUR"), raise_for_status=lambda: None),
            MagicMock(json=lambda: ts, raise_for_status=lambda: None),
        ]
        provider = AlphaVantagePriceProvider(api_key="X")
        q1 = provider.get_daily_close("AAPL", date(2026, 4, 18))
        q2 = provider.get_daily_close("AAPL", date(2026, 4, 18))
    assert q1 is not None and q2 is not None
    assert q1.currency == "EUR" and q2.currency == "EUR"
    assert get.call_count == 3  # not 4 — OVERVIEW called only once


def test_search_symbols_returns_matches():
    response = {
        "bestMatches": [
            {
                "1. symbol": "AAPL",
                "2. name": "Apple Inc",
                "4. region": "United States",
                "8. currency": "USD",
            },
            {
                "1. symbol": "AAPL.LON",
                "2. name": "Apple Inc",
                "4. region": "United Kingdom",
                "8. currency": "GBP",
            },
        ]
    }
    with patch(
        "app.integrations.price_provider.alpha_vantage_provider.httpx.get"
    ) as get:
        get.return_value = MagicMock(json=lambda: response, raise_for_status=lambda: None)
        out = AlphaVantagePriceProvider(api_key="X").search_symbols("apple")
    assert [m.symbol for m in out] == ["AAPL", "AAPL.LON"]
    assert out[0].currency == "USD"
    assert out[1].exchange == "United Kingdom"


def test_search_symbols_empty():
    with patch(
        "app.integrations.price_provider.alpha_vantage_provider.httpx.get"
    ) as get:
        get.return_value = MagicMock(
            json=lambda: {"bestMatches": []}, raise_for_status=lambda: None
        )
        assert AlphaVantagePriceProvider(api_key="X").search_symbols("zzz") == []


def test_get_daily_closes_loops_per_symbol():
    ts_aapl = _ts_daily_response([("2026-04-18", "234.56")])
    ts_msft = _ts_daily_response([("2026-04-18", "410.10")])
    with patch(
        "app.integrations.price_provider.alpha_vantage_provider.httpx.get"
    ) as get:
        get.side_effect = [
            MagicMock(json=lambda: ts_aapl, raise_for_status=lambda: None),
            MagicMock(json=lambda: _overview_response("USD"), raise_for_status=lambda: None),
            MagicMock(json=lambda: ts_msft, raise_for_status=lambda: None),
            MagicMock(json=lambda: _overview_response("USD"), raise_for_status=lambda: None),
        ]
        out = AlphaVantagePriceProvider(api_key="X").get_daily_closes(
            ["AAPL", "MSFT"], date(2026, 4, 18)
        )
    assert set(out.keys()) == {"AAPL", "MSFT"}
    assert out["AAPL"].close == Decimal("234.56")
    assert out["MSFT"].close == Decimal("410.10")
