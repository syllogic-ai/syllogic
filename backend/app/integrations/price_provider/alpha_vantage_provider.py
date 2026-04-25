from __future__ import annotations

import logging
from datetime import date
from decimal import Decimal

import httpx

from .base import PriceProvider, PriceQuote, SymbolMatch

logger = logging.getLogger(__name__)

ALPHA_VANTAGE_BASE_URL = "https://www.alphavantage.co/query"


class AlphaVantagePriceProvider:
    """Alpha Vantage implementation of the PriceProvider Protocol.

    Note on rate limits: free tier = 25 req/day, premium = 75 req/min.
    Missing quotes from rate-limit responses are returned as None and logged.
    Currency is resolved per-symbol via OVERVIEW and cached on the instance
    for the lifetime of the process.
    """

    name = "alpha_vantage"

    def __init__(self, api_key: str):
        if not api_key:
            raise ValueError("api_key is required")
        self.api_key = api_key
        self._currency_cache: dict[str, str] = {}

    def _get(self, params: dict) -> dict | None:
        params = {**params, "apikey": self.api_key}
        try:
            resp = httpx.get(ALPHA_VANTAGE_BASE_URL, params=params, timeout=15.0)
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            logger.warning("Alpha Vantage request failed (%s): %s", params.get("function"), e)
            return None
        if "Note" in data or "Information" in data:
            logger.warning("Alpha Vantage rate-limited: %s", data.get("Note") or data.get("Information"))
            return None
        if "Error Message" in data:
            logger.warning("Alpha Vantage error: %s", data["Error Message"])
            return None
        return data

    def _currency_for(self, symbol: str) -> str:
        cached = self._currency_cache.get(symbol)
        if cached:
            return cached
        data = self._get({"function": "OVERVIEW", "symbol": symbol})
        currency = (data or {}).get("Currency") or "USD"
        currency = currency.upper()
        self._currency_cache[symbol] = currency
        return currency

    def get_daily_close(self, symbol: str, on: date) -> PriceQuote | None:
        data = self._get({
            "function": "TIME_SERIES_DAILY",
            "symbol": symbol,
            "outputsize": "compact",
        })
        if not data:
            return None
        series = data.get("Time Series (Daily)") or {}
        if not series:
            return None
        # Filter to dates <= `on`, take the most recent.
        eligible = sorted((d for d in series if d <= on.isoformat()), reverse=True)
        if not eligible:
            return None
        picked = eligible[0]
        close_str = series[picked].get("4. close")
        if close_str is None:
            return None
        return PriceQuote(
            symbol=symbol,
            currency=self._currency_for(symbol),
            date=date.fromisoformat(picked),
            close=Decimal(close_str),
        )

    def get_daily_closes(
        self, symbols: list[str], on: date
    ) -> dict[str, PriceQuote]:
        out: dict[str, PriceQuote] = {}
        for sym in symbols:
            q = self.get_daily_close(sym, on)
            if q is not None:
                out[sym] = q
        return out

    def search_symbols(self, query: str) -> list[SymbolMatch]:
        data = self._get({"function": "SYMBOL_SEARCH", "keywords": query})
        if not data:
            return []
        matches = data.get("bestMatches") or []
        out: list[SymbolMatch] = []
        for m in matches:
            sym = m.get("1. symbol")
            if not sym:
                continue
            out.append(
                SymbolMatch(
                    symbol=sym,
                    name=m.get("2. name") or sym,
                    exchange=m.get("4. region"),
                    currency=(m.get("8. currency") or None),
                )
            )
        return out
