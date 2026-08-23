"""The mobile widget needs an account logo; the balances endpoint must expose it."""
import uuid
from decimal import Decimal

import pytest

from app.db_helpers import clear_request_user_id, set_request_user_id
from app.models import Account, CompanyLogo, User


@pytest.fixture
def make_user(db_session):
    """
    Minimal `make_user` fixture for this test file.

    `backend/tests/conftest.py` provides `db_session` but no `make_user`
    fixture; the neighbouring `test_people_filter.py` creates `User` rows
    directly instead of using a shared helper, so this mirrors that pattern
    locally and cleans up (cascade-deleting the user's accounts) on teardown.
    """
    created_user_ids = []

    def _make_user():
        user = User(id=str(uuid.uuid4()), email=f"{uuid.uuid4()}@test.com")
        db_session.add(user)
        db_session.flush()
        created_user_ids.append(user.id)
        return user

    yield _make_user

    if created_user_ids:
        db_session.query(User).filter(User.id.in_(created_user_ids)).delete(synchronize_session=False)
        db_session.commit()


def test_account_balances_includes_logo_url(db_session, make_user):
    user = make_user()
    logo = CompanyLogo(
        id=uuid.uuid4(),
        domain="ing.nl",
        company_name="ING",
        logo_url="https://logo.example/ing.png",
        status="found",
    )
    db_session.add(logo)
    db_session.flush()

    try:
        account = Account(
            id=uuid.uuid4(),
            user_id=user.id,
            name="Main Checking",
            account_type="checking",
            currency="EUR",
            is_active=True,
            functional_balance=Decimal("7425.00"),
            logo_id=logo.id,
            institution="ING",
        )
        db_session.add(account)
        db_session.commit()

        from app.routes.analytics import get_account_balances

        # get_account_balances resolves the caller via a request-scoped
        # contextvar (app.db_helpers.get_request_user_id), not the user_id
        # kwarg alone, so it must be set here the same way
        # tests/test_account_sync_encryption.py and
        # tests/test_account_iban_dedupe.py do for other route/service
        # functions called directly outside of a real request.
        # from_date/to_date default to FastAPI `Query(None)` marker objects
        # (which are truthy) rather than plain None when the route function
        # is called directly instead of through FastAPI's dependency
        # injection, so they must be passed explicitly here to hit the
        # "no filters" branch.
        token = set_request_user_id(user.id)
        try:
            rows = get_account_balances(from_date=None, to_date=None, user_id=user.id, db=db_session)
        finally:
            clear_request_user_id(token)
        row = next(r for r in rows if r["account_id"] == str(account.id))

        assert row["logo_url"] == "https://logo.example/ing.png"
        assert row["institution"] == "ING"
    finally:
        # `company_logos.domain` is unique, so the logo row must always be
        # cleaned up (even on assertion failure) or a re-run collides on it.
        db_session.rollback()
        db_session.query(CompanyLogo).filter(CompanyLogo.id == logo.id).delete(synchronize_session=False)
        db_session.commit()


def test_account_balances_logo_url_is_none_without_logo(db_session, make_user):
    user = make_user()
    account = Account(
        id=uuid.uuid4(),
        user_id=user.id,
        name="Cash",
        account_type="checking",
        currency="EUR",
        is_active=True,
        functional_balance=Decimal("10.00"),
        logo_id=None,
    )
    db_session.add(account)
    db_session.commit()

    from app.routes.analytics import get_account_balances

    # from_date/to_date default to FastAPI `Query(None)` marker objects (which
    # are truthy) rather than plain None when the route function is called
    # directly instead of through FastAPI's dependency injection, so they
    # must be passed explicitly here to hit the "no filters" branch.
    token = set_request_user_id(user.id)
    try:
        rows = get_account_balances(from_date=None, to_date=None, user_id=user.id, db=db_session)
    finally:
        clear_request_user_id(token)
    row = next(r for r in rows if r["account_id"] == str(account.id))

    assert row["logo_url"] is None
    assert row["institution"] is None
