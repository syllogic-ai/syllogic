"""IBAN-based account dedupe across bank re-authorizations.

Enable Banking mints a NEW account uid (external_id) every time a consent is
re-authorized, so matching on external_id alone makes the same real account
come back unrecognized and get inserted a second time. That is how duplicate
"ABN AMRO Giannis" rows were created in production.

The IBAN is stable across re-consents and globally unique, so it is the
correct identity fallback when external_id misses.

Run with:
    cd backend && pytest tests/test_account_iban_dedupe.py -v
"""
import base64
import os
import sys
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import Base, SessionLocal, engine  # noqa: E402
from app.db_helpers import (  # noqa: E402
    clear_request_user_id,
    get_or_create_system_user,
    set_request_user_id,
)
from app.integrations.base import AccountData, BankAdapter, TransactionData  # noqa: E402
from app.models import Account  # noqa: E402
from app.security.data_encryption import reset_encryption_config_cache  # noqa: E402
from app.services.sync_service import SyncService  # noqa: E402

PROVIDER = "iban-dedupe-test"


def _set_encryption_env() -> dict[str, Optional[str]]:
    """Enable encryption, returning the prior env so it can be restored.

    Leaking this key into the process env and the config cache would change
    how sibling tests in the same pytest session hash their values.
    """
    previous = {
        k: os.environ.get(k)
        for k in (
            "DATA_ENCRYPTION_KEY_CURRENT",
            "DATA_ENCRYPTION_KEY_ID",
            "DATA_ENCRYPTION_KEY_PREVIOUS",
        )
    }
    key = base64.urlsafe_b64encode(b"a" * 32).decode("utf-8").rstrip("=")
    os.environ["DATA_ENCRYPTION_KEY_CURRENT"] = key
    os.environ["DATA_ENCRYPTION_KEY_ID"] = "k-test"
    os.environ.pop("DATA_ENCRYPTION_KEY_PREVIOUS", None)
    reset_encryption_config_cache()
    return previous


def _restore_encryption_env(previous: dict[str, Optional[str]]) -> None:
    for name, value in previous.items():
        if value is None:
            os.environ.pop(name, None)
        else:
            os.environ[name] = value
    reset_encryption_config_cache()


class _Adapter(BankAdapter):
    """Adapter returning a caller-supplied set of accounts."""

    def __init__(self, accounts: list[AccountData]):
        self._accounts = accounts

    def fetch_accounts(self) -> list[AccountData]:
        return self._accounts

    def fetch_transactions(
        self,
        account_external_id: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> list[TransactionData]:
        return []

    def normalize_transaction(self, raw: dict) -> TransactionData:
        raise NotImplementedError


def _account(
    external_id: str,
    iban: Optional[str],
    name: str = "Current Account",
    balance_available: Optional[Decimal] = Decimal("10.00"),
) -> AccountData:
    return AccountData(
        external_id=external_id,
        name=name,
        account_type="checking",
        institution="Test Bank",
        currency="EUR",
        iban=iban,
        balance_available=balance_available,
    )


def _sync(db, user_id: str, accounts: list[AccountData]) -> None:
    token = set_request_user_id(user_id)
    try:
        SyncService(db, user_id=user_id).sync_accounts(_Adapter(accounts), provider=PROVIDER)
    finally:
        clear_request_user_id(token)


def _rows(db, user_id: str) -> list[Account]:
    return (
        db.query(Account)
        .filter(Account.user_id == user_id, Account.provider == PROVIDER)
        .all()
    )


def _cleanup(db, user_id: str) -> None:
    db.query(Account).filter(
        Account.user_id == user_id, Account.provider == PROVIDER
    ).delete()
    db.commit()


def test_reconsent_with_new_external_id_reuses_account_via_iban():
    """The regression: a re-consent must NOT duplicate the account."""
    _prev_env = _set_encryption_env()
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    user_id = None
    try:
        user_id = str(get_or_create_system_user(db).id)
        _cleanup(db, user_id)

        iban = f"NL91ABNA{uuid.uuid4().hex[:10].upper()}"

        # Initial authorization.
        _sync(db, user_id, [_account("eb-uid-first", iban)])
        assert len(_rows(db, user_id)) == 1

        # Consent expires; user re-authorizes. Same real account, NEW uid.
        _sync(db, user_id, [_account("eb-uid-second", iban)])

        rows = _rows(db, user_id)
        assert len(rows) == 1, (
            f"Re-consent duplicated the account: {len(rows)} rows. "
            "external_id changed but the IBAN is the same account."
        )
        # The stale uid must be refreshed so later syncs match on external_id again.
        assert rows[0].external_id == "eb-uid-second"
    finally:
        if user_id:
            _cleanup(db, user_id)
        db.close()
        _restore_encryption_env(_prev_env)


def test_resync_without_balance_keeps_existing_balance():
    """A sync that carries no balance must not null the stored one.

    None in AccountData.balance_available means "not provided", never
    "clear". The live sync_accounts caller (the Revolut CSV import via
    sync_all) never sets a balance, so before the guard every re-import
    wiped the stored value; adapters that fetch balances separately
    (e.g. Enable Banking) rely on the same contract.
    """
    _prev_env = _set_encryption_env()
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    user_id = None
    try:
        user_id = str(get_or_create_system_user(db).id)
        _cleanup(db, user_id)

        iban = f"NL91ABNA{uuid.uuid4().hex[:10].upper()}"

        _sync(db, user_id, [_account("uid-bal", iban, balance_available=Decimal("42.50"))])
        rows = _rows(db, user_id)
        assert len(rows) == 1 and rows[0].balance_available == Decimal("42.50")

        # Re-sync with no balance in the payload.
        _sync(db, user_id, [_account("uid-bal", iban, balance_available=None)])
        rows = _rows(db, user_id)
        assert len(rows) == 1
        assert rows[0].balance_available == Decimal("42.50"), (
            "sync_accounts nulled balance_available when the adapter "
            "provided no balance; it must keep the stored value."
        )

        # A sync that does carry a balance still updates it.
        _sync(db, user_id, [_account("uid-bal", iban, balance_available=Decimal("13.37"))])
        rows = _rows(db, user_id)
        assert len(rows) == 1 and rows[0].balance_available == Decimal("13.37")

        # A genuine zero is an update too — pins `is not None` against a
        # truthiness refactor, which would silently keep the stale 13.37.
        _sync(db, user_id, [_account("uid-bal", iban, balance_available=Decimal("0.00"))])
        rows = _rows(db, user_id)
        assert len(rows) == 1 and rows[0].balance_available == Decimal("0.00")
    finally:
        if user_id:
            _cleanup(db, user_id)
        db.close()
        _restore_encryption_env(_prev_env)


def test_accounts_without_iban_are_not_collapsed():
    """Guard: a null IBAN must never match other null-IBAN accounts."""
    _prev_env = _set_encryption_env()
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    user_id = None
    try:
        user_id = str(get_or_create_system_user(db).id)
        _cleanup(db, user_id)

        _sync(db, user_id, [_account("no-iban-a", None, name="Card A")])
        _sync(db, user_id, [_account("no-iban-b", None, name="Card B")])

        rows = _rows(db, user_id)
        assert len(rows) == 2, (
            "Accounts with no IBAN must stay distinct — matching on a NULL "
            f"iban_hash would collapse unrelated accounts. Got {len(rows)}."
        )
    finally:
        if user_id:
            _cleanup(db, user_id)
        db.close()
        _restore_encryption_env(_prev_env)


def test_distinct_ibans_remain_distinct_accounts():
    _prev_env = _set_encryption_env()
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    user_id = None
    try:
        user_id = str(get_or_create_system_user(db).id)
        _cleanup(db, user_id)

        suffix = uuid.uuid4().hex[:8].upper()
        _sync(db, user_id, [_account("uid-1", f"NL01ABNA{suffix}1", name="Joint")])
        _sync(db, user_id, [_account("uid-2", f"NL02ABNA{suffix}2", name="Savings")])

        assert len(_rows(db, user_id)) == 2
    finally:
        if user_id:
            _cleanup(db, user_id)
        db.close()
        _restore_encryption_env(_prev_env)


def test_blank_external_id_does_not_merge_unrelated_accounts():
    """A blank external_id is not an identity.

    `Account.external_id == None` renders as `IS NULL`, so an unguarded
    lookup matches the first account that also has none recorded. Providers
    that omit external_id (ibkr_flex, manual) have many such rows, and
    merging them would silently fuse unrelated accounts. A blank value must
    also let an available IBAN reach the fallback.
    """
    _prev_env = _set_encryption_env()
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    user_id = None
    try:
        user_id = str(get_or_create_system_user(db).id)
        _cleanup(db, user_id)

        # Seed two accounts that carry no external_id at all, the way manual
        # and ibkr_flex rows exist in production. Postgres permits several
        # NULLs under the (user_id, provider, external_id) unique constraint.
        suffix = uuid.uuid4().hex[:8].upper()
        for name, iban_value in (("No-ID One", f"NL11ABNA{suffix}1"), ("No-ID Two", None)):
            account = Account(
                user_id=user_id,
                name=name,
                account_type="checking",
                institution="Test Bank",
                currency="EUR",
                provider=PROVIDER,
                external_id=None,
            )
            SyncService._set_account_iban_fields(account, iban_value)
            db.add(account)
        db.commit()

        service = SyncService(db, user_id=user_id)

        # A missing external_id must not resolve to a NULL-external_id row.
        assert service._find_existing_account(PROVIDER, None) is None, (
            "A missing external_id matched a NULL-external_id account: "
            "`external_id == None` renders as `IS NULL` and fuses unrelated rows."
        )

        # ...and it must let an available IBAN reach the fallback.
        matched = service._find_existing_account(PROVIDER, None, f"nl11 abna {suffix.lower()}1")
        assert matched is not None and matched.name == "No-ID One", (
            "A missing external_id must fall through to IBAN matching."
        )
    finally:
        if user_id:
            _cleanup(db, user_id)
        db.close()
        _restore_encryption_env(_prev_env)


def test_iban_matching_ignores_spacing_and_case():
    """Banks format IBANs inconsistently between responses."""
    _prev_env = _set_encryption_env()
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    user_id = None
    try:
        user_id = str(get_or_create_system_user(db).id)
        _cleanup(db, user_id)

        suffix = uuid.uuid4().hex[:8].upper()
        _sync(db, user_id, [_account("fmt-1", f"NL91ABNA{suffix}")])
        _sync(db, user_id, [_account("fmt-2", f"nl91 abna {suffix.lower()}")])

        rows = _rows(db, user_id)
        assert len(rows) == 1, (
            "Same IBAN written with different spacing/case must match; "
            f"got {len(rows)} rows."
        )
    finally:
        if user_id:
            _cleanup(db, user_id)
        db.close()
        _restore_encryption_env(_prev_env)
