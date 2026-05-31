from decimal import Decimal
from datetime import date
from pathlib import Path
from unittest.mock import patch
import pytest
import httpx

from app.integrations.ibkr_flex_adapter import (
    IBKRFlexAdapter,
    FlexStatementNotReady,
    FlexAuthError,
    FlexTransientError,
)

FIXTURES = Path(__file__).parent / "fixtures"


def _read(name: str) -> str:
    return (FIXTURES / name).read_text()


def test_parse_positions_extracts_holdings_and_cash():
    adapter = IBKRFlexAdapter(token="t", query_id_positions="qp", query_id_trades="qt")
    parsed = adapter.parse_positions_xml(_read("ibkr_flex_positions.xml"))
    by_sym = {p.symbol: p for p in parsed.positions}
    assert by_sym["AAPL"].quantity == Decimal("10")
    assert by_sym["AAPL"].currency == "USD"
    assert by_sym["AAPL"].instrument_type == "equity"
    assert by_sym["VWCE"].instrument_type == "etf"
    assert {c.currency: c.balance for c in parsed.cash} == {"USD": Decimal("1500.00"), "EUR": Decimal("320.50")}


def test_parse_positions_aggregates_per_lot_rows():
    """IBKR Flex Queries configured at lot granularity emit one OpenPosition
    per lot. The parser must aggregate them — quantities sum, avg_cost is
    quantity-weighted, lots without costBasisPrice are excluded from the
    weighted average."""
    adapter = IBKRFlexAdapter(token="t", query_id_positions="qp", query_id_trades="qt")
    parsed = adapter.parse_positions_xml(_read("ibkr_flex_positions_lots.xml"))
    by_sym = {p.symbol: p for p in parsed.positions}

    # Three PPC lots: 100@18 + 50@19 + 50@20 = 3750 over 200 shares → 18.75
    assert by_sym["PPC"].quantity == Decimal("200")
    assert by_sym["PPC"].avg_cost == Decimal("18.75")
    assert by_sym["PPC"].instrument_type == "equity"

    # Single-lot positions still parse correctly
    assert by_sym["AAPL"].quantity == Decimal("10")
    assert by_sym["AAPL"].avg_cost == Decimal("180.00")

    # Two VWCE lots; the second lacks costBasisPrice. Weighted avg = 100.00
    # over the 20 shares that have a price; the 22-share lot still
    # contributes to total quantity.
    assert by_sym["VWCE"].quantity == Decimal("42")
    assert by_sym["VWCE"].avg_cost == Decimal("100.00")
    assert by_sym["VWCE"].instrument_type == "etf"

    # No duplicate (symbol, instrument_type) pairs in the output — this is
    # exactly what the holdings_account_symbol_type_uq constraint enforces.
    keys = [(p.symbol, p.instrument_type) for p in parsed.positions]
    assert len(keys) == len(set(keys))


def test_parse_trades_extracts_trades():
    adapter = IBKRFlexAdapter(token="t", query_id_positions="qp", query_id_trades="qt")
    trades = adapter.parse_trades_xml(_read("ibkr_flex_trades.xml"))
    assert len(trades) == 2
    t1 = trades[0]
    assert t1.external_id == "T1"
    assert t1.symbol == "AAPL"
    assert t1.side == "buy"
    assert t1.quantity == Decimal("10")
    assert t1.price == Decimal("180.00")
    assert t1.trade_date == date(2026, 1, 15)


def test_request_statement_returns_reference_code(monkeypatch):
    adapter = IBKRFlexAdapter(token="t", query_id_positions="qp", query_id_trades="qt")

    def fake_get(url, params, timeout):
        assert "FlexStatementService.SendRequest" in url
        return httpx.Response(200, text='<FlexStatementResponse><Status>Success</Status><ReferenceCode>REF1</ReferenceCode><Url>https://x</Url></FlexStatementResponse>')

    with patch.object(adapter._client, "get", side_effect=fake_get):
        ref = adapter.request_statement("qp")
    assert ref == "REF1"


def test_fetch_statement_raises_not_ready(monkeypatch):
    adapter = IBKRFlexAdapter(token="t", query_id_positions="qp", query_id_trades="qt")
    response_xml = '<FlexStatementResponse><Status>Warn</Status><ErrorCode>1019</ErrorCode><ErrorMessage>Statement generation in progress</ErrorMessage></FlexStatementResponse>'
    with patch.object(adapter._client, "get", return_value=httpx.Response(200, text=response_xml)):
        with pytest.raises(FlexStatementNotReady):
            adapter.fetch_statement("REF1")


def test_fetch_statement_raises_auth_error():
    adapter = IBKRFlexAdapter(token="t", query_id_positions="qp", query_id_trades="qt")
    response_xml = '<FlexStatementResponse><Status>Fail</Status><ErrorCode>1012</ErrorCode><ErrorMessage>Token invalid</ErrorMessage></FlexStatementResponse>'
    with patch.object(adapter._client, "get", return_value=httpx.Response(200, text=response_xml)):
        with pytest.raises(FlexAuthError):
            adapter.fetch_statement("REF1")


def test_request_statement_retries_on_1001_then_succeeds():
    sleeps: list[float] = []
    adapter = IBKRFlexAdapter(
        token="t", query_id_positions="qp", query_id_trades="qt",
        transient_retries=3, transient_backoff_seconds=1.0,
        sleep=sleeps.append,
    )
    transient = '<FlexStatementResponse><Status>Fail</Status><ErrorCode>1001</ErrorCode><ErrorMessage>Statement could not be generated at this time. Please try again shortly.</ErrorMessage></FlexStatementResponse>'
    success = '<FlexStatementResponse><Status>Success</Status><ReferenceCode>REF1</ReferenceCode></FlexStatementResponse>'
    responses = [
        httpx.Response(200, text=transient),
        httpx.Response(200, text=transient),
        httpx.Response(200, text=success),
    ]
    with patch.object(adapter._client, "get", side_effect=responses):
        ref = adapter.request_statement("qp")
    assert ref == "REF1"
    assert sleeps == [1.0, 3.0]


def test_request_statement_raises_after_exhausting_retries_on_1001():
    sleeps: list[float] = []
    adapter = IBKRFlexAdapter(
        token="t", query_id_positions="qp", query_id_trades="qt",
        transient_retries=2, transient_backoff_seconds=1.0,
        sleep=sleeps.append,
    )
    transient = '<FlexStatementResponse><Status>Fail</Status><ErrorCode>1001</ErrorCode><ErrorMessage>Statement could not be generated at this time. Please try again shortly.</ErrorMessage></FlexStatementResponse>'
    with patch.object(adapter._client, "get", return_value=httpx.Response(200, text=transient)):
        with pytest.raises(FlexTransientError):
            adapter.request_statement("qp")
    assert sleeps == [1.0, 3.0]
