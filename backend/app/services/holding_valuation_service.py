from __future__ import annotations
from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP
import logging
from typing import Protocol
from uuid import UUID
from sqlalchemy.orm import Session

from app.models import Account, Holding, HoldingValuation, AccountBalance, User
from app.services.price_service import PriceService

logger = logging.getLogger(__name__)


class FxConverter(Protocol):
    def convert(self, amount: Decimal, src: str, dst: str, on: date) -> Decimal: ...


class HoldingValuationService:
    def __init__(self, db: Session, fx: FxConverter, price_service: PriceService | None = None):
        self.db = db
        self.fx = fx
        self.price_service = price_service or PriceService(db=db)

    def compute(self, account_id: UUID, on: date) -> Decimal:
        account = self.db.query(Account).filter_by(id=account_id).one()
        user = self.db.query(User).filter_by(id=account.user_id).one()
        user_currency = (getattr(user, "functional_currency", None) or account.currency or "EUR").upper()
        account_currency = (account.currency or user_currency).upper()
        holdings = self.db.query(Holding).filter_by(account_id=account_id).all()

        total_user = Decimal("0")
        total_account_ccy = Decimal("0")
        for h in holdings:
            price, currency, is_stale = self._price_for(h, on)
            value_native = (Decimal(h.quantity) * price).quantize(Decimal("0.00000001"))
            value_user = self.fx.convert(value_native, currency, user_currency, on)
            value_user = Decimal(value_user).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            value_acct = self.fx.convert(value_native, currency, account_currency, on)
            value_acct = Decimal(value_acct).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            self._upsert_valuation(h.id, on, Decimal(h.quantity), price, value_user, is_stale)
            total_user += value_user
            total_account_ccy += value_acct

        self._upsert_account_balance(account, on, total_account_ccy, total_user)
        self.db.commit()
        return total_user

    # Number of days between `on` and the latest snapshot beyond which we
    # consider the price stale. 3 days covers normal weekend gaps (Friday
    # close → Monday morning lookup) and most one-off holidays without
    # producing constant false-positive stale flags.
    STALE_AFTER_DAYS = 3

    def _price_for(self, h: Holding, on: date) -> tuple[Decimal, str, bool]:
        if h.instrument_type == "cash":
            return Decimal("1"), h.currency, False
        lookup_symbol = h.provider_symbol or h.symbol
        snap = self.price_service.latest_snapshot(lookup_symbol, on)
        if snap is None:
            return Decimal("0"), h.currency, True
        gap_days = (on - snap.date).days
        is_stale = gap_days > self.STALE_AFTER_DAYS
        return Decimal(snap.close), snap.currency, is_stale

    def _upsert_valuation(self, holding_id, on: date, qty: Decimal, price: Decimal,
                          value_user: Decimal, is_stale: bool) -> None:
        row = self.db.query(HoldingValuation).filter_by(holding_id=holding_id, date=on).one_or_none()
        if row is None:
            row = HoldingValuation(holding_id=holding_id, date=on, quantity=qty,
                                   price=price, value_user_currency=value_user, is_stale=is_stale)
            self.db.add(row)
        else:
            row.quantity = qty
            row.price = price
            row.value_user_currency = value_user
            row.is_stale = is_stale

    def _upsert_account_balance(self, account: Account, on: date, total_account_ccy: Decimal,
                                total_user: Decimal) -> None:
        row = self.db.query(AccountBalance).filter_by(account_id=account.id, date=on).one_or_none()
        if row is None:
            row = AccountBalance(
                account_id=account.id,
                date=on,
                balance_in_account_currency=total_account_ccy,
                balance_in_functional_currency=total_user,
            )
            self.db.add(row)
        else:
            row.balance_in_account_currency = total_account_ccy
            row.balance_in_functional_currency = total_user
        account.balance_available = total_account_ccy
        account.last_synced_at = datetime.utcnow()
