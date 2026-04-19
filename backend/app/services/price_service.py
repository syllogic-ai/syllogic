from __future__ import annotations
from datetime import date
from decimal import Decimal
import logging
from sqlalchemy.orm import Session

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
        cached_rows = (
            self.db.query(PriceSnapshot)
            .filter(PriceSnapshot.symbol.in_(symbols), PriceSnapshot.date == on)
            .all()
        )
        cached = {
            r.symbol: PriceQuote(symbol=r.symbol, currency=r.currency, date=on, close=Decimal(r.close))
            for r in cached_rows
        }
        missing = [s for s in symbols if s not in cached]
        if missing:
            try:
                fetched = self.provider.get_daily_closes(missing, on)
            except Exception as e:
                logger.warning("price provider %s failed for %s on %s: %s", self.provider.name, missing, on, e)
                fetched = {}
            for sym, quote in fetched.items():
                self.db.add(PriceSnapshot(
                    symbol=quote.symbol,
                    currency=quote.currency,
                    date=quote.date,
                    close=quote.close,
                    provider=self.provider.name,
                ))
                cached[sym] = quote
            self.db.commit()
        return cached

    def latest_snapshot(self, symbol: str, on: date) -> PriceSnapshot | None:
        return (
            self.db.query(PriceSnapshot)
            .filter(PriceSnapshot.symbol == symbol, PriceSnapshot.date <= on)
            .order_by(PriceSnapshot.date.desc())
            .first()
        )
