"""IBKR Flex Web Service adapter.

Two-step flow:
  1. SendRequest with token + query_id → returns reference code
  2. GetStatement with token + reference code → returns XML statement
     (or status=Warn/ErrorCode=1019 if still generating).
"""
from __future__ import annotations
import logging
import time
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Iterable
import xml.etree.ElementTree as ET

import httpx

logger = logging.getLogger(__name__)

BASE = "https://gdcdyn.interactivebrokers.com/Universal/servlet"
SEND_URL = f"{BASE}/FlexStatementService.SendRequest"
GET_URL = f"{BASE}/FlexStatementService.GetStatement"

FLEX_NOT_READY_CODES = {"1019"}
FLEX_AUTH_ERROR_CODES = {"1012", "1003"}
# 1001 = "Statement could not be generated at this time. Please try again shortly."
# Distinct from 1019 (still generating after a successful SendRequest) and 1018
# (rate limit: 1 req/sec, 10 req/min per token — see IBKR Flex v3 error docs).
# Default retry schedule (5s, 15s, 45s) stays well under both limits.
FLEX_TRANSIENT_CODES = {"1001"}


class FlexError(RuntimeError):
    pass


class FlexStatementNotReady(FlexError):
    pass


class FlexAuthError(FlexError):
    pass


class FlexTransientError(FlexError):
    pass


_ASSET_CATEGORY_MAP = {"STK": "equity", "ETF": "etf"}


@dataclass(frozen=True)
class ParsedPosition:
    symbol: str
    name: str
    quantity: Decimal
    currency: str
    instrument_type: str
    avg_cost: Decimal | None
    mark_price: Decimal | None


@dataclass(frozen=True)
class ParsedCash:
    currency: str
    balance: Decimal


@dataclass(frozen=True)
class ParsedStatement:
    positions: list[ParsedPosition]
    cash: list[ParsedCash]


@dataclass(frozen=True)
class ParsedTrade:
    external_id: str
    symbol: str
    side: str
    quantity: Decimal
    price: Decimal
    currency: str
    trade_date: date


class IBKRFlexAdapter:
    def __init__(
        self,
        token: str,
        query_id_positions: str,
        query_id_trades: str,
        *,
        client: httpx.Client | None = None,
        transient_retries: int = 3,
        transient_backoff_seconds: float = 5.0,
        sleep: callable = time.sleep,
    ):
        self.token = token
        self.query_id_positions = query_id_positions
        self.query_id_trades = query_id_trades
        self._client = client or httpx.Client(timeout=30.0)
        self._transient_retries = transient_retries
        self._transient_backoff = transient_backoff_seconds
        self._sleep = sleep

    def request_statement(self, query_id: str) -> str:
        last_exc: FlexTransientError | None = None
        for attempt in range(self._transient_retries + 1):
            try:
                resp = self._client.get(SEND_URL, params={"v": "3", "t": self.token, "q": query_id}, timeout=30.0)
                root = ET.fromstring(resp.text)
                status = (root.findtext("Status") or "").strip()
                if status != "Success":
                    self._raise_for_error(root)
                return (root.findtext("ReferenceCode") or "").strip()
            except FlexTransientError as e:
                last_exc = e
                if attempt >= self._transient_retries:
                    break
                delay = self._transient_backoff * (3 ** attempt)
                logger.warning(
                    "IBKR Flex transient error on SendRequest (q=%s), retry %d/%d in %.1fs: %s",
                    query_id, attempt + 1, self._transient_retries, delay, e,
                )
                self._sleep(delay)
        assert last_exc is not None
        raise last_exc

    def fetch_statement(self, reference_code: str) -> str:
        resp = self._client.get(GET_URL, params={"v": "3", "t": self.token, "q": reference_code}, timeout=60.0)
        if "<FlexQueryResponse" in resp.text:
            return resp.text
        root = ET.fromstring(resp.text)
        self._raise_for_error(root)
        return resp.text

    def _raise_for_error(self, root: ET.Element) -> None:
        code = (root.findtext("ErrorCode") or "").strip()
        message = (root.findtext("ErrorMessage") or "").strip() or "Unknown Flex error"
        if code in FLEX_NOT_READY_CODES:
            raise FlexStatementNotReady(message)
        if code in FLEX_AUTH_ERROR_CODES:
            raise FlexAuthError(message)
        if code in FLEX_TRANSIENT_CODES:
            raise FlexTransientError(f"{code}: {message}")
        raise FlexError(f"{code}: {message}")

    def parse_positions_xml(self, xml: str) -> ParsedStatement:
        root = ET.fromstring(xml)
        positions: list[ParsedPosition] = []
        for op in root.iter("OpenPosition"):
            asset = (op.get("assetCategory") or "").upper()
            instrument_type = _ASSET_CATEGORY_MAP.get(asset)
            if instrument_type is None:
                continue
            positions.append(ParsedPosition(
                symbol=op.get("symbol", "").strip(),
                name=op.get("description", "").strip(),
                quantity=Decimal(op.get("position", "0")),
                currency=op.get("currency", "USD").strip().upper(),
                instrument_type=instrument_type,
                avg_cost=_dec(op.get("costBasisPrice")),
                mark_price=_dec(op.get("markPrice")),
            ))
        cash: list[ParsedCash] = []
        for c in root.iter("CashReportCurrency"):
            cur = (c.get("currency") or "").upper()
            if not cur or cur == "BASE_SUMMARY":
                continue
            cash.append(ParsedCash(currency=cur, balance=Decimal(c.get("endingCash", "0"))))
        return ParsedStatement(positions=positions, cash=cash)

    def parse_trades_xml(self, xml: str) -> list[ParsedTrade]:
        root = ET.fromstring(xml)
        trades: list[ParsedTrade] = []
        for t in root.iter("Trade"):
            asset = (t.get("assetCategory") or "").upper()
            if asset not in _ASSET_CATEGORY_MAP:
                continue
            trades.append(ParsedTrade(
                external_id=t.get("tradeID", "").strip(),
                symbol=t.get("symbol", "").strip(),
                side="buy" if t.get("buySell", "BUY").upper() == "BUY" else "sell",
                quantity=Decimal(t.get("quantity", "0")),
                price=Decimal(t.get("tradePrice", "0")),
                currency=t.get("currency", "USD").strip().upper(),
                trade_date=datetime.strptime(t.get("tradeDate", ""), "%Y%m%d").date(),
            ))
        return trades


def _dec(value: str | None) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        return Decimal(value)
    except Exception:
        return None
