import hashlib
import hmac
import json
import time
from decimal import Decimal
from unittest.mock import patch
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.database import get_db
from app.main import app
from app.models import User, Account, Holding, Transaction


INTERNAL_AUTH_SECRET = "test-internal-secret"


def _signed_headers(
    method: str, path_with_query: str, user_id: str = "u1", body: bytes = b""
) -> dict:
    timestamp = str(int(time.time()))
    payload = "\n".join(
        [method.upper(), path_with_query, user_id, timestamp, hashlib.sha256(body).hexdigest()]
    )
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
        body = b""
        if "json" in kwargs:
            body = json.dumps(kwargs.pop("json"), separators=(",", ":")).encode("utf-8")
            kwargs["content"] = body
            headers["content-type"] = "application/json"
        elif isinstance(kwargs.get("content"), bytes):
            body = kwargs["content"]
        headers.update(_signed_headers(method, url, body=body))
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
def db(db_session):
    """The shared Postgres session from conftest.

    These tests used to build their own in-memory SQLite schema from a
    hand-picked subset of models. That stopped working once the models grew
    JSONB and UUID columns SQLite cannot compile, and it tested against a
    schema that was never the real one. conftest truncates between tests, so
    the shared session is just as isolated.
    """
    return db_session


@pytest.fixture
def client(db, monkeypatch):
    from app.services import credentials_crypto

    monkeypatch.setenv("SYLLOGIC_SECRET_KEY", credentials_crypto.generate_key())
    monkeypatch.setenv("INTERNAL_AUTH_SECRET", INTERNAL_AUTH_SECRET)
    db.add(User(id="u1", email="u@example.com", functional_currency="EUR"))
    db.commit()
    app.dependency_overrides[get_db] = lambda: db
    monkeypatch.setattr("app.routes.investments.get_user_id", lambda x=None: "u1")
    yield SigningClient(TestClient(app))
    app.dependency_overrides.clear()


def test_create_manual_account_and_holding(client, db):
    cash = Account(
        id=uuid4(), user_id="u1", name="Checking", account_type="checking", currency="USD"
    )
    db.add(cash)
    db.commit()

    r = client.post(
        "/api/investments/manual-accounts", json={"name": "Etoro", "base_currency": "EUR"}
    )
    assert r.status_code == 200, r.text
    account_id = r.json()["account_id"]

    with patch("app.routes.investments.get_price_provider") as gp:
        provider = gp.return_value
        provider.search_symbols.return_value = [
            type(
                "S",
                (),
                {"symbol": "AAPL", "name": "Apple", "exchange": "NASDAQ", "currency": "USD"},
            )()
        ]
        with patch("app.routes.investments._run_sync_in_process"):
            r = client.post(
                f"/api/investments/manual-accounts/{account_id}/holdings",
                json={
                    "symbol": "AAPL",
                    "quantity": "10",
                    "avg_cost": "150",
                    "instrument_type": "equity",
                    "currency": "USD",
                    "as_of_date": "2026-04-01",
                    "funding_account_id": str(cash.id),
                },
            )
    assert r.status_code == 200, r.text
    holdings = db.query(Holding).all()
    assert holdings[0].symbol == "AAPL"
    assert holdings[0].source == "manual"

    funding_txn = db.query(Transaction).filter_by(account_id=cash.id).one()
    assert funding_txn.amount == Decimal("-1500")


def test_create_manual_holding_rejects_investment_funding_account(client, db):
    r = client.post(
        "/api/investments/manual-accounts", json={"name": "Etoro", "base_currency": "EUR"}
    )
    account_id = r.json()["account_id"]

    r = client.post(
        f"/api/investments/manual-accounts/{account_id}/holdings",
        json={
            "symbol": "AAPL",
            "quantity": "10",
            "avg_cost": "150",
            "instrument_type": "equity",
            "currency": "EUR",
            "as_of_date": "2026-04-01",
            "funding_account_id": account_id,
        },
    )
    assert r.status_code == 400, r.text


def test_delete_holding_only_for_manual(client, db):
    acc = Account(
        id=uuid4(), user_id="u1", name="m", account_type="investment_manual", currency="EUR"
    )
    h = Holding(
        id=uuid4(),
        user_id="u1",
        account_id=acc.id,
        symbol="AAPL",
        currency="USD",
        instrument_type="equity",
        quantity=Decimal("1"),
        source="ibkr_flex",
    )
    # Parents first: these models declare foreign keys but no relationships,
    # so the flush order is not dependency-sorted for us.
    db.add(acc)
    db.flush()
    db.add(h)
    db.commit()
    r = client.delete(f"/api/investments/holdings/{h.id}")
    assert r.status_code == 400
    h.source = "manual"
    db.commit()
    r = client.delete(f"/api/investments/holdings/{h.id}")
    assert r.status_code == 204
