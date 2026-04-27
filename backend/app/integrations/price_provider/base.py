from __future__ import annotations
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Protocol


@dataclass(frozen=True)
class PriceQuote:
    symbol: str
    currency: str
    date: date
    close: Decimal


@dataclass(frozen=True)
class SymbolMatch:
    symbol: str
    name: str
    exchange: str | None
    currency: str | None


class PriceProvider(Protocol):
    name: str

    def get_daily_close(self, symbol: str, on: date) -> PriceQuote | None: ...
    def get_daily_closes(self, symbols: list[str], on: date) -> dict[str, PriceQuote]: ...
    def get_daily_closes_range(
        self, symbol: str, start: date, end: date
    ) -> list[PriceQuote]: ...
    def search_symbols(self, query: str) -> list[SymbolMatch]: ...
