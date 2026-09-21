from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from app.models import Account, User


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


def test_daily_sync_enumerates_active_manual_accounts_and_fans_out(db, monkeypatch):
    user = User(id="u1", email="u@example.com", functional_currency="EUR")
    a1 = Account(
        id=uuid4(),
        user_id="u1",
        name="Manual",
        account_type="investment_manual",
        currency="EUR",
        is_active=True,
    )
    a2 = Account(
        id=uuid4(),
        user_id="u1",
        name="Bank",
        account_type="checking",
        currency="EUR",
        is_active=True,
    )
    a3 = Account(
        id=uuid4(),
        user_id="u1",
        name="Old Manual",
        account_type="investment_manual",
        currency="EUR",
        is_active=False,
    )
    # Parents first: these models declare foreign keys but no relationships,
    # so the flush order is not dependency-sorted for us.
    db.add(user)
    db.flush()
    db.add_all([a1, a2, a3])
    db.commit()

    enqueued: list[str] = []
    with (
        patch("tasks.investment_tasks.SessionLocal", return_value=db),
        patch(
            "tasks.investment_tasks.sync_investment_account.delay",
            side_effect=lambda aid: enqueued.append(str(aid)),
        ),
    ):
        from tasks.investment_tasks import daily_investment_sync_all

        daily_investment_sync_all.run()

    assert sorted(enqueued) == sorted([str(a1.id)])


def test_sync_investment_account_calls_service(db, monkeypatch):
    user = User(id="u1", email="u@example.com", functional_currency="EUR")
    acc = Account(
        id=uuid4(),
        user_id="u1",
        name="Manual",
        account_type="investment_manual",
        currency="EUR",
        is_active=True,
    )
    # Parents first: these models declare foreign keys but no relationships,
    # so the flush order is not dependency-sorted for us.
    db.add(user)
    db.flush()
    db.add(acc)
    db.commit()

    fake_svc = MagicMock()
    with (
        patch("tasks.investment_tasks.SessionLocal", return_value=db),
        patch("tasks.investment_tasks.InvestmentSyncService", return_value=fake_svc),
    ):
        from tasks.investment_tasks import sync_investment_account

        sync_investment_account.run(str(acc.id))
    fake_svc.sync_account.assert_called_once()
