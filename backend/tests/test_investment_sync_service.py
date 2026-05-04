from datetime import date, datetime
from decimal import Decimal
from unittest.mock import MagicMock
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.models import (
    Account, BrokerConnection, Holding, BrokerTrade, PriceSnapshot,
    HoldingValuation, AccountBalance, User,
)
from app.services.investment_sync_service import InvestmentSyncService
from app.services.credentials_crypto import encrypt

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture(autouse=True)
def crypto_key(monkeypatch):
    from app.services import credentials_crypto
    monkeypatch.setenv("SYLLOGIC_SECRET_KEY", credentials_crypto.generate_key())


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    for model in (User, Account, BrokerConnection, Holding, BrokerTrade,
                  PriceSnapshot, HoldingValuation, AccountBalance):
        model.__table__.create(bind=engine)
    with Session(engine) as session:
        yield session


def test_sync_brokerage_upserts_holdings_trades_and_cash(db):
    user = User(id="u1", email="u@example.com", functional_currency="EUR")
    acc = Account(id=uuid4(), user_id="u1", name="IBKR", account_type="investment_brokerage", currency="EUR")
    conn = BrokerConnection(id=uuid4(), user_id="u1", account_id=acc.id, provider="ibkr_flex",
                            credentials_encrypted=encrypt({"flex_token": "t",
                                                           "query_id_positions": "qp",
                                                           "query_id_trades": "qt"}))
    db.add_all([user, acc, conn]); db.commit()

    adapter = MagicMock()
    adapter.request_statement.side_effect = ["REF_POS", "REF_TR"]
    adapter.fetch_statement.side_effect = [
        (FIXTURES / "ibkr_flex_positions.xml").read_text(),
        (FIXTURES / "ibkr_flex_trades.xml").read_text(),
    ]
    from app.integrations.ibkr_flex_adapter import IBKRFlexAdapter as Real
    real = Real(token="t", query_id_positions="qp", query_id_trades="qt")
    adapter.parse_positions_xml.side_effect = real.parse_positions_xml
    adapter.parse_trades_xml.side_effect = real.parse_trades_xml

    fx = MagicMock(); fx.convert.side_effect = lambda amt, src, dst, on: amt

    svc = InvestmentSyncService(db=db, adapter_factory=lambda creds: adapter, fx=fx)
    svc.sync_account(acc.id, on=date(2026, 4, 18))

    holdings = {h.symbol: h for h in db.query(Holding).filter_by(account_id=acc.id).all()}
    assert holdings["AAPL"].quantity == Decimal("10")
    assert holdings["VWCE"].instrument_type == "etf"
    assert holdings["USD"].instrument_type == "cash" and holdings["USD"].quantity == Decimal("1500.00")
    assert holdings["EUR"].quantity == Decimal("320.50")
    trades = db.query(BrokerTrade).filter_by(account_id=acc.id).all()
    assert {t.external_id for t in trades} == {"T1", "T2"}

    db.refresh(conn)
    assert conn.last_sync_status == "ok"
    assert conn.last_sync_at is not None


def test_sync_marks_needs_reauth_on_auth_error(db):
    user = User(id="u1", email="u@example.com", functional_currency="EUR")
    acc = Account(id=uuid4(), user_id="u1", name="IBKR", account_type="investment_brokerage", currency="EUR")
    conn = BrokerConnection(id=uuid4(), user_id="u1", account_id=acc.id, provider="ibkr_flex",
                            credentials_encrypted=encrypt({"flex_token": "t", "query_id_positions": "qp", "query_id_trades": "qt"}))
    db.add_all([user, acc, conn]); db.commit()

    from app.integrations.ibkr_flex_adapter import FlexAuthError
    adapter = MagicMock()
    adapter.request_statement.side_effect = FlexAuthError("token bad")
    fx = MagicMock(); fx.convert.side_effect = lambda *a, **kw: Decimal("0")

    svc = InvestmentSyncService(db=db, adapter_factory=lambda creds: adapter, fx=fx)
    with pytest.raises(FlexAuthError):
        svc.sync_account(acc.id, on=date(2026, 4, 18))
    db.refresh(conn)
    assert conn.last_sync_status == "needs_reauth"
    assert "token bad" in (conn.last_sync_error or "")
