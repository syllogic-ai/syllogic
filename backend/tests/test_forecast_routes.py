"""Route-level tests for /api/forecast/cashflow.

Run with:
    cd backend && .venv/bin/pytest tests/test_forecast_routes.py -v
"""

import hashlib
import hmac
import json
import time
from datetime import date, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from app.database import get_db
from app.db_helpers import get_current_user_id
from app.main import app
from app.models import Account, AccountBalance, Category, RecurringTransaction, Transaction, User

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

    def request(self, method: str, url: str, **kwargs):
        headers = dict(kwargs.pop("headers", {}) or {})
        body = b""
        if "json" in kwargs:
            body = json.dumps(kwargs.pop("json"), separators=(",", ":")).encode("utf-8")
            kwargs["content"] = body
            headers["content-type"] = "application/json"
        headers.update(_signed_headers(method, url, body=body))
        return self._client.request(method, url, headers=headers, **kwargs)

    def get(self, url, **kw):
        return self.request("GET", url, **kw)


@pytest.fixture
def db(db_session):
    """The shared Postgres session from conftest.

    These tests need Postgres-only column types (JSONB with `::jsonb` server
    defaults) that SQLite cannot render, and used to skip themselves unless
    FORECAST_TEST_DATABASE_URL named a database they could drop and rebuild.
    The whole suite now runs against a migrated scratch database that conftest
    truncates between tests, so they just use it.
    """
    return db_session


@pytest.fixture
def client(db, monkeypatch):
    monkeypatch.setenv("INTERNAL_AUTH_SECRET", INTERNAL_AUTH_SECRET)
    db.add(User(id="u1", email="u@example.com", functional_currency="EUR"))
    db.commit()
    app.dependency_overrides[get_db] = lambda: db
    # The route resolves its caller through Depends(get_current_user_id); it
    # used to be patched by name on the route module, which stopped existing.
    app.dependency_overrides[get_current_user_id] = lambda: "u1"
    yield SigningClient(TestClient(app))
    app.dependency_overrides.clear()


def test_cashflow_forecast_uses_current_balance_and_recurring(client, db):
    account = Account(
        id=uuid4(),
        user_id="u1",
        name="Checking",
        account_type="checking",
        currency="EUR",
        functional_balance=Decimal("1000"),
        is_active=True,
    )
    db.add(account)
    db.add(
        RecurringTransaction(
            id=uuid4(),
            user_id="u1",
            account_id=account.id,
            name="Rent",
            amount=Decimal("500"),
            frequency="monthly",
            is_active=True,
            next_due_date=date.today() + timedelta(days=5),
        )
    )
    db.commit()

    r = client.get("/api/forecast/cashflow?horizon_days=30")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["startingBalance"] == 1000.0
    assert body["projectedBalanceAtHorizon"] == 500.0
    assert len(body["series"]) == 31
    assert body["series"][0]["projectedBalance"] == 1000.0


def test_cashflow_forecast_excludes_recurring_linked_transactions_from_variable_leg(client, db):
    account = Account(
        id=uuid4(),
        user_id="u1",
        name="Checking",
        account_type="checking",
        currency="EUR",
        functional_balance=Decimal("0"),
        is_active=True,
    )
    recurring = RecurringTransaction(
        id=uuid4(),
        user_id="u1",
        account_id=account.id,
        name="Netflix",
        amount=Decimal("15"),
        frequency="monthly",
        is_active=True,
        next_due_date=date.today() + timedelta(days=60),
    )
    db.add(account)
    db.add(recurring)
    db.commit()

    # A materialized recurring transaction: must not also be counted in the
    # trailing variable-spend average, or it would be double-counted.
    db.add(
        Transaction(
            id=uuid4(),
            user_id="u1",
            account_id=account.id,
            transaction_type="debit",
            amount=Decimal("-15"),
            functional_amount=Decimal("-15"),
            include_in_analytics=True,
            recurring_transaction_id=recurring.id,
            booked_at=datetime.utcnow() - timedelta(days=1),
        )
    )
    db.commit()

    r = client.get("/api/forecast/cashflow?horizon_days=1")
    assert r.status_code == 200, r.text
    body = r.json()
    # No non-recurring-linked transactions and horizon too short to hit the
    # recurring occurrence at day 60, so balance should stay flat at 0.
    assert body["projectedBalanceAtHorizon"] == 0.0


def test_cashflow_forecast_recurring_income_is_an_inflow(client, db):
    account = Account(
        id=uuid4(),
        user_id="u1",
        name="Checking",
        account_type="checking",
        currency="EUR",
        functional_balance=Decimal("1000"),
        is_active=True,
    )
    income_category = Category(id=uuid4(), user_id="u1", name="Salary", category_type="income")
    db.add(account)
    db.add(income_category)
    db.add(
        RecurringTransaction(
            id=uuid4(),
            user_id="u1",
            account_id=account.id,
            category_id=income_category.id,
            name="Salary",
            amount=Decimal("2000"),
            frequency="monthly",
            is_active=True,
            next_due_date=date.today() + timedelta(days=5),
        )
    )
    db.commit()

    r = client.get("/api/forecast/cashflow?horizon_days=30")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["projectedBalanceAtHorizon"] == 3000.0
    assert body["projectedIncome"] == 2000.0
    assert body["projectedExpenses"] == 0.0


def test_cashflow_forecast_excludes_growth_account_transactions_from_cash_leg(client, db):
    # A stray transaction posted against an investment account must not
    # leak into the cash leg's flat trailing average - it's the growth
    # leg's job to account for that account's balance movement, not the
    # transaction-based leg (double-counting otherwise).
    cash_account = Account(
        id=uuid4(),
        user_id="u1",
        name="Checking",
        account_type="checking",
        currency="EUR",
        functional_balance=Decimal("0"),
        is_active=True,
    )
    investment_account = Account(
        id=uuid4(),
        user_id="u1",
        name="Brokerage",
        account_type="investment_manual",
        currency="EUR",
        functional_balance=Decimal("0"),
        is_active=True,
    )
    db.add(cash_account)
    db.add(investment_account)
    db.add(
        Transaction(
            id=uuid4(),
            user_id="u1",
            account_id=investment_account.id,
            transaction_type="credit",
            amount=Decimal("1000"),
            functional_amount=Decimal("1000"),
            include_in_analytics=True,
            booked_at=datetime.utcnow() - timedelta(days=1),
        )
    )
    db.commit()

    r = client.get("/api/forecast/cashflow?horizon_days=10")
    assert r.status_code == 200, r.text
    body = r.json()
    # No AccountBalance history for the investment account either, so its
    # growth leg falls back to flat (0%). Combined with the transaction
    # being excluded from the cash leg, the whole forecast should stay flat.
    assert body["startingBalance"] == 0.0
    assert body["projectedBalanceAtHorizon"] == 0.0


def test_cashflow_forecast_excludes_recurring_on_growth_account_from_cash_leg(client, db):
    # A recurring contribution scheduled against an investment account must
    # not subtract from the cash leg - the growth leg (driven by
    # AccountBalance history, not recurring definitions) owns that account.
    investment_account = Account(
        id=uuid4(),
        user_id="u1",
        name="Brokerage",
        account_type="investment_manual",
        currency="EUR",
        functional_balance=Decimal("500"),
        is_active=True,
    )
    db.add(investment_account)
    db.add(
        RecurringTransaction(
            id=uuid4(),
            user_id="u1",
            account_id=investment_account.id,
            name="Monthly contribution",
            amount=Decimal("100"),
            frequency="monthly",
            is_active=True,
            next_due_date=date.today() + timedelta(days=5),
        )
    )
    db.commit()

    r = client.get("/api/forecast/cashflow?horizon_days=30")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["cashStartingBalance"] == 0.0
    assert body["growthStartingBalance"] == 500.0
    # No history to derive a growth rate from -> flat, and the recurring
    # contribution must not have subtracted from anything.
    assert body["projectedBalanceAtHorizon"] == 500.0


def test_cashflow_forecast_growth_leg_compounds_from_balance_history(client, db):
    investment_account = Account(
        id=uuid4(),
        user_id="u1",
        name="Brokerage",
        account_type="investment_manual",
        currency="EUR",
        functional_balance=Decimal("1000"),
        is_active=True,
    )
    db.add(investment_account)
    db.commit()

    # 31 daily snapshots growing from 900 to 1000 over 30 days -> a clear
    # positive historical daily rate, comfortably above the 5-row minimum.
    for i in range(31):
        snapshot_date = datetime.utcnow() - timedelta(days=30 - i)
        balance = Decimal("900") + (Decimal("100") * i / 30)
        db.add(
            AccountBalance(
                id=uuid4(),
                account_id=investment_account.id,
                date=snapshot_date,
                balance_in_account_currency=balance,
                balance_in_functional_currency=balance,
            )
        )
    db.commit()

    r = client.get("/api/forecast/cashflow?horizon_days=10")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["growthStartingBalance"] == 1000.0
    # Positive historical growth -> projected balance must exceed the flat
    # starting balance after 10 days of compounding.
    assert body["projectedBalanceAtHorizon"] > 1000.0
    assert body["growthProjectedChange"] > 0.0


def test_cashflow_forecast_growth_leg_falls_back_to_flat_with_sparse_history(client, db):
    investment_account = Account(
        id=uuid4(),
        user_id="u1",
        name="Brokerage",
        account_type="investment_manual",
        currency="EUR",
        functional_balance=Decimal("1000"),
        is_active=True,
    )
    db.add(investment_account)
    db.commit()

    # Only 3 snapshots - below the 5-row minimum, so the rate must fall
    # back to 0% rather than extrapolating from too little data.
    for i in range(3):
        snapshot_date = datetime.utcnow() - timedelta(days=3 - i)
        db.add(
            AccountBalance(
                id=uuid4(),
                account_id=investment_account.id,
                date=snapshot_date,
                balance_in_account_currency=Decimal("500"),
                balance_in_functional_currency=Decimal("500"),
            )
        )
    db.commit()

    r = client.get("/api/forecast/cashflow?horizon_days=10")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["projectedBalanceAtHorizon"] == 1000.0
    assert body["growthProjectedChange"] == 0.0
