from __future__ import annotations
from datetime import date
from decimal import Decimal
import logging
from sqlalchemy.orm import Session
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.models import PriceSnapshot
from app.integrations.price_provider import get_price_provider
from app.integrations.price_provider.base import PriceProvider, PriceQuote

logger = logging.getLogger(__name__)


class PriceService:
    def __init__(self, db: Session, provider: PriceProvider | None = None):
        self.db = db
        self.provider = provider or get_price_provider()

    def get_or_fetch(self, symbols: list[str], on: date) -> dict[str, PriceQuote]:
        if not symbols:
            return {}

        # A past trading day's close is immutable once recorded, so it's
        # safe to treat as a permanent cache. Today's "close" isn't final
        # until the market shuts — a run before that only gets the provider's
        # last-available price (commonly yesterday's), so today is never
        # served from cache: every call re-fetches and overwrites, letting a
        # later same-day run replace an earlier placeholder once the real
        # close publishes.
        is_current_day = on >= date.today()

        cached: dict[str, PriceQuote] = {}
        if not is_current_day:
            cached_rows = (
                self.db.query(PriceSnapshot)
                .filter(PriceSnapshot.symbol.in_(symbols), PriceSnapshot.date == on)
                .all()
            )
            cached = {
                r.symbol: PriceQuote(
                    symbol=r.symbol, currency=r.currency, date=on, close=Decimal(r.close)
                )
                for r in cached_rows
            }

        missing = [s for s in symbols if s not in cached]
        if missing:
            try:
                fetched = self.provider.get_daily_closes(missing, on)
            except Exception as e:
                logger.warning(
                    "price provider %s failed for %s on %s: %s", self.provider.name, missing, on, e
                )
                fetched = {}
            for sym, quote in fetched.items():
                # Key the cache row on the requested date (`on`), not the
                # provider's returned quote.date — the two commonly differ
                # before `on`'s own market close (or over a weekend), and
                # storing under quote.date would make `on` a permanent
                # cache-miss, forcing a re-fetch on every call for that day.
                stmt = pg_insert(PriceSnapshot).values(
                    symbol=quote.symbol,
                    currency=quote.currency,
                    date=on,
                    close=quote.close,
                    provider=self.provider.name,
                )
                stmt = stmt.on_conflict_do_update(
                    index_elements=["symbol", "date"],
                    set_={
                        "close": stmt.excluded.close,
                        "currency": stmt.excluded.currency,
                        "provider": stmt.excluded.provider,
                    },
                )
                self.db.execute(stmt)
                cached[sym] = PriceQuote(
                    symbol=quote.symbol, currency=quote.currency, date=on, close=quote.close
                )
            self.db.commit()
        return cached

    def latest_snapshot(self, symbol: str, on: date) -> PriceSnapshot | None:
        return (
            self.db.query(PriceSnapshot)
            .filter(PriceSnapshot.symbol == symbol, PriceSnapshot.date <= on)
            .order_by(PriceSnapshot.date.desc())
            .first()
        )
