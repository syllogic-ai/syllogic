from __future__ import annotations
from datetime import date, datetime
from decimal import Decimal
from typing import Callable
from uuid import UUID
import logging
from sqlalchemy.orm import Session

from app.models import (
    Account, BrokerConnection, Holding, BrokerTrade, PriceSnapshot,
)
from app.services.credentials_crypto import decrypt
from app.services.holding_valuation_service import HoldingValuationService, FxConverter
from app.services.price_service import PriceService
from app.integrations.ibkr_flex_adapter import (
    IBKRFlexAdapter, FlexAuthError, FlexStatementNotReady, FlexError,
)

logger = logging.getLogger(__name__)

AdapterFactory = Callable[[dict], IBKRFlexAdapter]


def _default_factory(creds: dict) -> IBKRFlexAdapter:
    return IBKRFlexAdapter(
        token=creds["flex_token"],
        query_id_positions=creds["query_id_positions"],
        query_id_trades=creds["query_id_trades"],
    )


class InvestmentSyncService:
    def __init__(self, db: Session, fx: FxConverter,
                 adapter_factory: AdapterFactory | None = None,
                 price_service: PriceService | None = None,
                 valuation_service: HoldingValuationService | None = None):
        self.db = db
        self.fx = fx
        self.adapter_factory = adapter_factory or _default_factory
        self.price_service = price_service or PriceService(db=db)
        self.valuation_service = valuation_service or HoldingValuationService(db=db, fx=fx, price_service=self.price_service)

    def sync_account(self, account_id: UUID, on: date | None = None) -> None:
        on = on or date.today()
        account = self.db.query(Account).filter_by(id=account_id).one()
        if account.account_type == "investment_brokerage":
            self._sync_brokerage(account, on)
        elif account.account_type == "investment_manual":
            self._sync_manual(account, on)
        else:
            raise ValueError(f"Account {account_id} is not an investment account")

    def _sync_brokerage(self, account: Account, on: date) -> None:
        conn = self.db.query(BrokerConnection).filter_by(account_id=account.id).one()
        creds = decrypt(conn.credentials_encrypted)
        adapter = self.adapter_factory(creds)
        try:
            ref_positions = adapter.request_statement(creds["query_id_positions"])
            positions_xml = adapter.fetch_statement(ref_positions)
            ref_trades = adapter.request_statement(creds["query_id_trades"])
            trades_xml = adapter.fetch_statement(ref_trades)
        except FlexAuthError as e:
            conn.last_sync_status = "needs_reauth"
            conn.last_sync_error = str(e)
            self.db.commit()
            raise
        except FlexStatementNotReady:
            conn.last_sync_status = "pending"
            self.db.commit()
            raise
        except FlexError as e:
            conn.last_sync_status = "error"
            conn.last_sync_error = str(e)
            self.db.commit()
            raise

        statement = adapter.parse_positions_xml(positions_xml)
        trades = adapter.parse_trades_xml(trades_xml)
        self._upsert_positions(account, statement.positions)
        self._upsert_cash(account, statement.cash)
        self._upsert_trades(account, trades)
        self.valuation_service.compute(account_id=account.id, on=on)

        conn.last_sync_status = "ok"
        conn.last_sync_error = None
        conn.last_sync_at = datetime.utcnow()
        self.db.commit()

    def _sync_manual(self, account: Account, on: date) -> None:
        holdings = self.db.query(Holding).filter_by(account_id=account.id).all()
        symbols = sorted({h.symbol for h in holdings if h.instrument_type != "cash"})
        if symbols:
            self.price_service.get_or_fetch(symbols, on)
        self.valuation_service.compute(account_id=account.id, on=on)
        account.last_synced_at = datetime.utcnow()
        self.db.commit()

    def _upsert_positions(self, account: Account, positions) -> None:
        seen = set()
        for p in positions:
            seen.add((p.symbol, p.instrument_type))
            row = self.db.query(Holding).filter_by(
                account_id=account.id, symbol=p.symbol, instrument_type=p.instrument_type
            ).one_or_none()
            if row is None:
                row = Holding(
                    user_id=account.user_id, account_id=account.id, symbol=p.symbol,
                    name=p.name, currency=p.currency, instrument_type=p.instrument_type,
                    quantity=p.quantity, avg_cost=p.avg_cost, source="ibkr_flex",
                )
                self.db.add(row)
            else:
                row.quantity = p.quantity
                row.avg_cost = p.avg_cost
                row.name = p.name
                row.currency = p.currency
        for h in list(self.db.query(Holding).filter_by(account_id=account.id, source="ibkr_flex").all()):
            if (h.symbol, h.instrument_type) not in seen and h.instrument_type != "cash":
                self.db.delete(h)

    def _upsert_cash(self, account: Account, cash) -> None:
        seen = set()
        for c in cash:
            seen.add(c.currency)
            row = self.db.query(Holding).filter_by(
                account_id=account.id, symbol=c.currency, instrument_type="cash"
            ).one_or_none()
            if row is None:
                row = Holding(
                    user_id=account.user_id, account_id=account.id, symbol=c.currency,
                    name=f"Cash ({c.currency})", currency=c.currency,
                    instrument_type="cash", quantity=c.balance, source="ibkr_flex",
                )
                self.db.add(row)
            else:
                row.quantity = c.balance
        for h in self.db.query(Holding).filter_by(account_id=account.id, source="ibkr_flex", instrument_type="cash").all():
            if h.symbol not in seen:
                self.db.delete(h)

    def _upsert_trades(self, account: Account, trades) -> None:
        existing = {
            t.external_id for t in
            self.db.query(BrokerTrade.external_id).filter_by(account_id=account.id).all()
        }
        for t in trades:
            if t.external_id in existing:
                continue
            self.db.add(BrokerTrade(
                account_id=account.id, symbol=t.symbol, trade_date=t.trade_date,
                side=t.side, quantity=t.quantity, price=t.price,
                currency=t.currency, external_id=t.external_id,
            ))
