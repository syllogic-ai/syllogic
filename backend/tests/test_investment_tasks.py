from datetime import date
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.models import Account, BrokerConnection, User


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    for model in (User, Account, BrokerConnection):
        model.__table__.create(bind=engine)
    with Session(engine) as session:
        yield session


def test_daily_sync_enumerates_active_accounts_and_fans_out(db, monkeypatch):
    user = User(id="u1", email="u@example.com", functional_currency="EUR")
    a1 = Account(id=uuid4(), user_id="u1", name="IBKR", account_type="investment_brokerage", currency="EUR", is_active=True)
    a2 = Account(id=uuid4(), user_id="u1", name="Manual", account_type="investment_manual", currency="EUR", is_active=True)
    a3 = Account(id=uuid4(), user_id="u1", name="Bank", account_type="checking", currency="EUR", is_active=True)
    a4 = Account(id=uuid4(), user_id="u1", name="Old IBKR", account_type="investment_brokerage", currency="EUR", is_active=False)
    db.add_all([user, a1, a2, a3, a4])
    db.add(BrokerConnection(id=uuid4(), user_id="u1", account_id=a1.id, provider="ibkr_flex",
                            credentials_encrypted="x", last_sync_status="ok"))
    db.commit()

    enqueued: list[str] = []
    with patch("tasks.investment_tasks.SessionLocal", return_value=db), \
         patch("tasks.investment_tasks.sync_investment_account.delay", side_effect=lambda aid: enqueued.append(str(aid))):
        from tasks.investment_tasks import daily_investment_sync_all
        daily_investment_sync_all.run()

    assert sorted(enqueued) == sorted([str(a1.id), str(a2.id)])


def test_sync_investment_account_calls_service(db, monkeypatch):
    user = User(id="u1", email="u@example.com", functional_currency="EUR")
    acc = Account(id=uuid4(), user_id="u1", name="Manual", account_type="investment_manual", currency="EUR", is_active=True)
    db.add_all([user, acc]); db.commit()

    fake_svc = MagicMock()
    with patch("tasks.investment_tasks.SessionLocal", return_value=db), \
         patch("tasks.investment_tasks.InvestmentSyncService", return_value=fake_svc):
        from tasks.investment_tasks import sync_investment_account
        sync_investment_account.run(str(acc.id))
    fake_svc.sync_account.assert_called_once()
