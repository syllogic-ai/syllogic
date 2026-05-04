import hashlib
import hmac
import time
from datetime import date
from decimal import Decimal
from unittest.mock import patch
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app.models import User, Account, Holding, BrokerConnection, HoldingValuation, AccountBalance


INTERNAL_AUTH_SECRET = "test-internal-secret"


def _signed_headers(method: str, path_with_query: str, user_id: str = "u1") -> dict:
    timestamp = str(int(time.time()))
    payload = "\n".join([method.upper(), path_with_query, user_id, timestamp])
    signature = hmac.new(
        INTERNAL_AUTH_SECRET.encode("utf-8"),
        payload.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return {
        "x-syllogic-user-id": user_id,
        "x-syllogic-timestamp": timestamp,
        "x-syllogic-signature": signature,
    }


class SigningClient:
    def __init__(self, client: TestClient):
        self._client = client

    def _path_with_query(self, url: str) -> str:
        return url

    def request(self, method: str, url: str, **kwargs):
        headers = dict(kwargs.pop("headers", {}) or {})
        headers.update(_signed_headers(method, url))
        return self._client.request(method, url, headers=headers, **kwargs)

    def get(self, url, **kw):
        return self.request("GET", url, **kw)

    def post(self, url, **kw):
        return self.request("POST", url, **kw)

    def patch(self, url, **kw):
        return self.request("PATCH", url, **kw)

    def delete(self, url, **kw):
        return self.request("DELETE", url, **kw)


@pytest.fixture
def db():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    for model in (User, Account, BrokerConnection, Holding, HoldingValuation, AccountBalance):
        model.__table__.create(bind=engine)
    with Session(engine) as session:
        yield session


@pytest.fixture
def client(db, monkeypatch):
    from app.services import credentials_crypto
    monkeypatch.setenv("SYLLOGIC_SECRET_KEY", credentials_crypto.generate_key())
    monkeypatch.setenv("INTERNAL_AUTH_SECRET", INTERNAL_AUTH_SECRET)
    db.add(User(id="u1", email="u@example.com", functional_currency="EUR")); db.commit()
    app.dependency_overrides[get_db] = lambda: db
    monkeypatch.setattr("app.routes.investments.get_user_id", lambda x=None: "u1")
    yield SigningClient(TestClient(app))
    app.dependency_overrides.clear()


def test_create_manual_account_and_holding(client, db):
    r = client.post("/api/investments/manual-accounts", json={"name": "Etoro", "base_currency": "EUR"})
    assert r.status_code == 200, r.text
    account_id = r.json()["account_id"]

    with patch("app.routes.investments.get_price_provider") as gp:
        provider = gp.return_value
        provider.search_symbols.return_value = [
            type("S", (), {"symbol": "AAPL", "name": "Apple", "exchange": "NASDAQ", "currency": "USD"})()
        ]
        with patch("app.routes.investments.sync_investment_account"):
            r = client.post(
                f"/api/investments/manual-accounts/{account_id}/holdings",
                json={"symbol": "AAPL", "quantity": "10", "instrument_type": "equity",
                      "currency": "USD", "as_of_date": "2026-04-01"},
            )
    assert r.status_code == 200, r.text
    holdings = db.query(Holding).all()
    assert holdings[0].symbol == "AAPL"
    assert holdings[0].source == "manual"


def test_create_broker_connection_encrypts_credentials(client, db):
    with patch("app.routes.investments.sync_investment_account") as task:
        r = client.post("/api/investments/broker-connections", json={
            "provider": "ibkr_flex", "flex_token": "TOKEN_X",
            "query_id_positions": "111", "query_id_trades": "222",
            "account_name": "IBKR", "base_currency": "EUR",
        })
    assert r.status_code == 200, r.text
    body = r.json()
    assert "connection_id" in body and "account_id" in body
    conn = db.query(BrokerConnection).one()
    assert "TOKEN_X" not in conn.credentials_encrypted
    task.delay.assert_called_once()


def test_delete_holding_only_for_manual(client, db):
    acc = Account(id=uuid4(), user_id="u1", name="m", account_type="investment_manual", currency="EUR")
    h = Holding(id=uuid4(), user_id="u1", account_id=acc.id, symbol="AAPL", currency="USD",
                instrument_type="equity", quantity=Decimal("1"), source="ibkr_flex")
    db.add_all([acc, h]); db.commit()
    r = client.delete(f"/api/investments/holdings/{h.id}")
    assert r.status_code == 400
    h.source = "manual"; db.commit()
    r = client.delete(f"/api/investments/holdings/{h.id}")
    assert r.status_code == 204
