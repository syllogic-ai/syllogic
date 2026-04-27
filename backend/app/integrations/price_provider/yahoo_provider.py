from __future__ import annotations
import logging
from datetime import date, timedelta
from decimal import Decimal
from .base import PriceProvider, PriceQuote, SymbolMatch

try:
    import yfinance as yf
except ImportError:  # pragma: no cover
    yf = None

logger = logging.getLogger(__name__)


class YahooPriceProvider:
    name = "yahoo"

    def _currency_for(self, symbol: str) -> str:
        try:
            info = yf.Ticker(symbol).info or {}
            return (info.get("currency") or "USD").upper()
        except Exception:
            return "USD"

    def get_daily_close(self, symbol: str, on: date) -> PriceQuote | None:
        if yf is None:
            raise RuntimeError("yfinance is not installed")
        start = on - timedelta(days=5)
        end = on + timedelta(days=1)
        df = yf.Ticker(symbol).history(start=start.isoformat(), end=end.isoformat(), auto_adjust=False)
        if df is None or df.empty:
            return None
        df = df[df.index.date <= on]
        if df.empty:
            return None
        row = df.iloc[-1]
        return PriceQuote(
            symbol=symbol,
            currency=self._currency_for(symbol),
            date=df.index[-1].date(),
            close=Decimal(str(row["Close"])),
        )

    def get_daily_closes(self, symbols: list[str], on: date) -> dict[str, PriceQuote]:
        if not symbols:
            return {}
        if yf is None:
            raise RuntimeError("yfinance is not installed")
        start = on - timedelta(days=5)
        end = on + timedelta(days=1)
        data = yf.download(
            tickers=" ".join(symbols),
            start=start.isoformat(),
            end=end.isoformat(),
            group_by="column",
            auto_adjust=False,
            progress=False,
            threads=True,
        )
        out: dict[str, PriceQuote] = {}
        if data is None or data.empty:
            return out
        # yfinance returns a MultiIndex when multiple tickers are requested,
        # but a flat columns Index when only one is requested.
        is_multi = hasattr(data.columns, "get_level_values") and getattr(
            data.columns, "nlevels", 1
        ) > 1
        if is_multi:
            if "Close" not in data.columns.get_level_values(0):
                return out
            closes = data["Close"]
        else:
            if "Close" not in data.columns:
                return out
            # Single-symbol response: build a one-column frame keyed by the symbol.
            import pandas as pd  # local import — already a transitive dep of yfinance
            closes = pd.DataFrame({symbols[0]: data["Close"]})
        for sym in symbols:
            if sym not in closes.columns:
                continue
            series = closes[sym].dropna()
            series = series[series.index.date <= on]
            if series.empty:
                continue
            out[sym] = PriceQuote(
                symbol=sym,
                currency=self._currency_for(sym),
                date=series.index[-1].date(),
                close=Decimal(str(series.iloc[-1])),
            )
        return out

    def get_daily_closes_range(
        self, symbol: str, start: date, end: date
    ) -> list[PriceQuote]:
        """Fetch all daily closes for `symbol` in [start, end] (inclusive on
        both ends). Returns one PriceQuote per trading day; weekends/holidays
        are absent (caller forward-fills)."""
        if yf is None:
            raise RuntimeError("yfinance is not installed")
        if start > end:
            return []
        # yfinance treats `end` as exclusive; bump by 1 day to include it.
        end_excl = end + timedelta(days=1)
        df = yf.Ticker(symbol).history(
            start=start.isoformat(), end=end_excl.isoformat(), auto_adjust=False
        )
        if df is None or df.empty:
            return []
        currency = self._currency_for(symbol)
        out: list[PriceQuote] = []
        for ts, row in df.iterrows():
            d = ts.date()
            if d < start or d > end:
                continue
            out.append(PriceQuote(
                symbol=symbol,
                currency=currency,
                date=d,
                close=Decimal(str(row["Close"])),
            ))
        return out

    def search_symbols(self, query: str) -> list[SymbolMatch]:
        try:
            from yfinance import Search  # type: ignore
            results = Search(query, max_results=10).quotes or []
            return [
                SymbolMatch(
                    symbol=r.get("symbol", ""),
                    name=r.get("shortname") or r.get("longname") or r.get("symbol", ""),
                    exchange=r.get("exchDisp"),
                    currency=None,
                )
                for r in results
                if r.get("symbol")
            ]
        except Exception:
            return [SymbolMatch(symbol=query.upper(), name=query.upper(), exchange=None, currency=None)]
