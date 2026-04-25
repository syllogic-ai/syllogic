from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock, patch
import pandas as pd

from app.integrations.price_provider.yahoo_provider import YahooPriceProvider


def _df(rows):
    return pd.DataFrame(rows).set_index("Date")


def test_get_daily_close_returns_quote():
    fake = _df([{"Date": pd.Timestamp("2026-04-18"), "Close": 234.56}])
    with patch("app.integrations.price_provider.yahoo_provider.yf") as yf_mod:
        ticker = MagicMock()
        ticker.history.return_value = fake
        ticker.info = {"currency": "USD"}
        yf_mod.Ticker.return_value = ticker
        q = YahooPriceProvider().get_daily_close("AAPL", date(2026, 4, 18))
    assert q is not None
    assert q.symbol == "AAPL"
    assert q.currency == "USD"
    assert q.close == Decimal("234.56")
    assert q.date == date(2026, 4, 18)


def test_get_daily_close_returns_none_when_no_data():
    with patch("app.integrations.price_provider.yahoo_provider.yf") as yf_mod:
        ticker = MagicMock()
        ticker.history.return_value = pd.DataFrame()
        yf_mod.Ticker.return_value = ticker
        assert YahooPriceProvider().get_daily_close("ZZZZ", date(2026, 4, 18)) is None


def test_get_daily_closes_batches_symbols():
    # Build a proper MultiIndex DataFrame as yf.download returns
    tuples = [("Close", "AAPL"), ("Close", "MSFT")]
    mi = pd.MultiIndex.from_tuples(tuples)
    df = pd.DataFrame(
        [[234.56, 410.10]],
        index=pd.DatetimeIndex([pd.Timestamp("2026-04-18")], name="Date"),
        columns=mi,
    )
    with patch("app.integrations.price_provider.yahoo_provider.yf") as yf_mod:
        yf_mod.download.return_value = df
        yf_mod.Ticker.return_value = MagicMock(info={"currency": "USD"})
        result = YahooPriceProvider().get_daily_closes(["AAPL", "MSFT"], date(2026, 4, 18))
    assert set(result.keys()) == {"AAPL", "MSFT"}
    assert result["AAPL"].close == Decimal("234.56")
