from __future__ import annotations

from .base import PriceProvider, PriceQuote, SymbolMatch
from datetime import date


class AlphaVantagePriceProvider:
    name = "alpha_vantage"

    def __init__(self, api_key: str):
        self.api_key = api_key

    def get_daily_close(self, symbol: str, on: date) -> PriceQuote | None:
        raise NotImplementedError("AlphaVantagePriceProvider not implemented in v1")

    def get_daily_closes(self, symbols, on):  # type: ignore[override]
        raise NotImplementedError

    def search_symbols(self, query: str):
        raise NotImplementedError
