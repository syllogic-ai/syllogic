# Recognize-Own-IBANs Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Persist `iban_hash` on synced (EB-connected) accounts during sync, then generalize internal-transfer detection to match counterparty IBAN against any user account — so transfers between two synced accounts and transfers from synced to manual savings are both correctly recognized as internal.

**Architecture:** Three small backend changes — the `AccountData` adapter DTO learns an `iban` field, `SyncService` persists `iban_hash` + `iban_ciphertext` on synced accounts, and `InternalTransferService` drops its manual-only filter and branches on the destination account's provider (mirror for manual, link-only for synced). No schema migration. No frontend changes — manual reconciliation already works via the existing `UpdateBalanceDialog`.

**Tech Stack:** Python 3.11 + FastAPI + SQLAlchemy 2.0 + Celery, AES-GCM + HMAC-SHA256 blind index via existing `data_encryption` module, pytest.

**Spec:** `docs/superpowers/specs/2026-04-25-recognize-own-ibans-design.md`

---

## File Structure

| File | Responsibility |
|------|----------------|
| `backend/app/integrations/base.py` | DTO — add `iban` to `AccountData` |
| `backend/app/integrations/enable_banking_adapter.py` | Source — populate `AccountData.iban` from raw EB account |
| `backend/app/services/sync_service.py` | Persist — write `iban_ciphertext` + `iban_hash` on synced accounts |
| `backend/app/services/internal_transfer_service.py` | Detect — generalize mapping, branch by provider |
| `backend/tests/test_enable_banking_adapter.py` | Adapter test |
| `backend/tests/test_account_sync_encryption.py` | Sync persistence tests |
| `backend/tests/test_internal_transfer_service.py` | Synced↔synced detection + unlink tests |
| `backend/tests/test_post_import_pipeline.py` | End-to-end integration test |

---

## Task 1: Add `iban` field to `AccountData`

**Files:**
- Modify: `backend/app/integrations/base.py`

- [ ] **Step 1: Add the field**

In `backend/app/integrations/base.py`, inside `class AccountData`, after `currency`:

```python
class AccountData(BaseModel):
    """Canonical account data model."""
    external_id: str
    name: str
    account_type: str  # checking, savings, credit
    institution: str
    currency: str
    iban: Optional[str] = None  # IBAN of this account (stripped, upper-cased; None if not IBAN-based)
    balance_available: Optional[Decimal] = None
    metadata: dict = {}
```

(`Optional` is already imported at the top of the file.)

- [ ] **Step 2: Sanity check — module still imports**

Run:

```bash
cd backend && .venv/bin/python -c "from app.integrations.base import AccountData; print(AccountData(external_id='x', name='x', account_type='checking', institution='x', currency='EUR', iban='NL12').iban)"
```

Expected: `NL12`

- [ ] **Step 3: Commit**

```bash
git add backend/app/integrations/base.py
git commit -m "feat(adapter): add iban field to AccountData DTO"
```

---

## Task 2: EB adapter populates `AccountData.iban`

**Files:**
- Modify: `backend/app/integrations/enable_banking_adapter.py:69-85`
- Test: `backend/tests/test_enable_banking_adapter.py`

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/test_enable_banking_adapter.py`:

```python
class TestFetchAccountsIban(unittest.TestCase):
    """fetch_accounts must populate AccountData.iban from the raw EB session response."""

    def setUp(self):
        # Bypass __init__ — we don't need the real HTTP client to test transformation
        self.adapter = EnableBankingAdapter.__new__(EnableBankingAdapter)
        self.adapter.session_id = "session-123"

    def test_fetch_accounts_extracts_iban_from_raw(self):
        """A session-data response with iban populated must surface it on AccountData."""
        from unittest.mock import MagicMock
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "aspsp": {"name": "ABN AMRO"},
            "accounts": [
                {
                    "uid": "acc-1",
                    "iban": "NL91 ABNA 0417 1643 00",
                    "account_name": "Main Checking",
                    "cash_account_type": "CACC",
                    "currency": "EUR",
                },
            ],
        }
        self.adapter.client = MagicMock()
        self.adapter.client.get.return_value = mock_response

        accounts = self.adapter.fetch_accounts()

        self.assertEqual(len(accounts), 1)
        # IBAN must be passed through to AccountData. Whitespace is left as-is here
        # — normalization happens at persist time alongside the existing helper.
        self.assertEqual(accounts[0].iban, "NL91 ABNA 0417 1643 00")

    def test_fetch_accounts_iban_is_none_when_missing(self):
        """Accounts without an IBAN (e.g. some credit cards) must yield iban=None."""
        from unittest.mock import MagicMock
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "aspsp": {"name": "ABN AMRO"},
            "accounts": [
                {
                    "uid": "acc-2",
                    "account_name": "Credit Card",
                    "cash_account_type": "CARD",
                    "currency": "EUR",
                },
            ],
        }
        self.adapter.client = MagicMock()
        self.adapter.client.get.return_value = mock_response

        accounts = self.adapter.fetch_accounts()

        self.assertEqual(len(accounts), 1)
        self.assertIsNone(accounts[0].iban)
```

- [ ] **Step 2: Run test to verify failure**

```bash
cd backend && .venv/bin/pytest tests/test_enable_banking_adapter.py::TestFetchAccountsIban -v
```

Expected: FAIL — `AccountData(...)` does not currently include `iban`, the assertion compares `None` to the IBAN string.

- [ ] **Step 3: Wire IBAN through the adapter**

In `backend/app/integrations/enable_banking_adapter.py`, modify the `accounts.append(AccountData(...))` block in `fetch_accounts`:

```python
        for acc in session_data.get("accounts", []):
            accounts.append(AccountData(
                external_id=acc["uid"],
                name=acc.get("account_name") or acc.get("iban") or "Unknown Account",
                account_type=self._map_account_type(acc.get("cash_account_type")),
                institution=aspsp_name,
                currency=acc.get("currency", "EUR"),
                iban=acc.get("iban"),
                balance_available=None,  # Fetched separately via fetch_balances
            ))
```

Single-line change — added `iban=acc.get("iban")`.

- [ ] **Step 4: Run tests to verify pass**

```bash
cd backend && .venv/bin/pytest tests/test_enable_banking_adapter.py -v
```

Expected: all tests in the file pass (existing + 2 new).

- [ ] **Step 5: Commit**

```bash
git add backend/app/integrations/base.py backend/app/integrations/enable_banking_adapter.py backend/tests/test_enable_banking_adapter.py
git commit -m "feat(eb): expose account-level IBAN on AccountData"
```

---

## Task 3: SyncService persists IBAN on synced accounts

**Files:**
- Modify: `backend/app/services/sync_service.py:40-54, 132-165`
- Test: `backend/tests/test_account_sync_encryption.py`

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/test_account_sync_encryption.py`:

```python
def test_sync_service_persists_iban_on_synced_account_first_sync(db_session) -> None:
    """When AccountData.iban is set on a fresh sync, the synced account row is
    persisted with iban_ciphertext (enc:v1: envelope) + iban_hash (blind index)."""
    _set_encryption_env()
    try:
        from app.services.sync_service import SyncService
        from app.integrations.base import AccountData
        from app.security.data_encryption import blind_index

        user = _make_user(db_session)
        service = SyncService(db_session, user_id=user.id, use_llm_categorization=False)

        # Mock the adapter — only fetch_accounts is needed for this test path.
        from unittest.mock import MagicMock
        adapter = MagicMock()
        adapter.fetch_accounts.return_value = [
            AccountData(
                external_id="ext-iban-1",
                name="ABN Checking",
                account_type="checking",
                institution="ABN AMRO",
                currency="EUR",
                iban="NL91ABNA0417164300",
            ),
        ]

        service.sync_accounts(adapter, provider="enable_banking")
        db_session.commit()

        from app.models import Account
        from app.security.data_encryption import decrypt_value
        row = db_session.query(Account).filter_by(external_id="ext-iban-1").one()
        assert row.iban_ciphertext is not None
        assert row.iban_ciphertext.startswith("enc:v1:")
        assert decrypt_value(row.iban_ciphertext) == "NL91ABNA0417164300"
        assert row.iban_hash == blind_index("NL91ABNA0417164300")
    finally:
        reset_encryption_config_cache()


def test_sync_service_does_not_overwrite_existing_iban(db_session) -> None:
    """If iban_hash is already set on the account, sync must NOT overwrite it."""
    _set_encryption_env()
    try:
        from app.services.sync_service import SyncService
        from app.integrations.base import AccountData
        from app.security.data_encryption import encrypt_value, blind_index

        user = _make_user(db_session)

        # Pre-create an account with a different IBAN already set.
        from app.models import Account
        from decimal import Decimal
        original_iban = "NL01PRESET0000000000"
        existing = Account(
            user_id=user.id,
            name="ABN Checking",
            account_type="checking",
            institution="ABN AMRO",
            currency="EUR",
            provider="enable_banking",
            external_id="ext-iban-2",
            iban_ciphertext=encrypt_value(original_iban),
            iban_hash=blind_index(original_iban),
            starting_balance=Decimal("0"),
            is_active=True,
        )
        db_session.add(existing)
        db_session.commit()

        service = SyncService(db_session, user_id=user.id, use_llm_categorization=False)
        from unittest.mock import MagicMock
        adapter = MagicMock()
        adapter.fetch_accounts.return_value = [
            AccountData(
                external_id="ext-iban-2",
                name="ABN Checking",
                account_type="checking",
                institution="ABN AMRO",
                currency="EUR",
                iban="NL99DIFFERENT0000000",  # different IBAN — must be ignored
            ),
        ]

        service.sync_accounts(adapter, provider="enable_banking")
        db_session.commit()

        db_session.refresh(existing)
        assert existing.iban_hash == blind_index(original_iban), (
            "iban_hash must NOT be overwritten when already set"
        )


def test_sync_service_skips_iban_when_account_data_iban_is_none(db_session) -> None:
    """Accounts without an IBAN (some credit cards) must not trigger encryption."""
    _set_encryption_env()
    try:
        from app.services.sync_service import SyncService
        from app.integrations.base import AccountData

        user = _make_user(db_session)
        service = SyncService(db_session, user_id=user.id, use_llm_categorization=False)
        from unittest.mock import MagicMock
        adapter = MagicMock()
        adapter.fetch_accounts.return_value = [
            AccountData(
                external_id="ext-noiban",
                name="Credit Card",
                account_type="credit",
                institution="ABN AMRO",
                currency="EUR",
                iban=None,
            ),
        ]
        service.sync_accounts(adapter, provider="enable_banking")
        db_session.commit()

        from app.models import Account
        row = db_session.query(Account).filter_by(external_id="ext-noiban").one()
        assert row.iban_ciphertext is None
        assert row.iban_hash is None
    finally:
        reset_encryption_config_cache()
```

If a `_make_user` helper isn't already in this file, copy the one from `tests/test_internal_transfer_service.py`. The `_set_encryption_env` helper exists in this file (look near the top).

- [ ] **Step 2: Run tests to verify failure**

```bash
cd backend && .venv/bin/pytest tests/test_account_sync_encryption.py -v -k "iban"
```

Expected: FAIL — sync_service does not persist `iban_ciphertext`/`iban_hash` yet.

- [ ] **Step 3: Add the persistence helper**

In `backend/app/services/sync_service.py`, immediately after the existing `_set_account_external_id_fields` helper (around line 54), add:

```python
    @staticmethod
    def _set_account_iban_fields(account: Account, iban: Optional[str]) -> None:
        """Persist iban_ciphertext + iban_hash on a synced account.

        IBAN is treated as immutable. If the account already has iban_hash set,
        we do NOT overwrite — bank IBANs don't change in practice, and avoiding
        overwrites prevents a transient EB-response anomaly from corrupting
        the registered IBAN. Whitespace is stripped and the value is upper-cased
        before encryption to match the format used everywhere else in the codebase.
        """
        if not iban:
            return
        if account.iban_hash is not None:
            return
        normalized = iban.replace(" ", "").upper()
        encrypted = encrypt_value(normalized)
        hashed = blind_index(normalized)
        if encrypted is None or hashed is None:
            # Encryption not configured — sync_service already logs/handles this for
            # external_id; mirror that behavior (silent skip).
            return
        account.iban_ciphertext = encrypted
        account.iban_hash = hashed
```

- [ ] **Step 4: Wire into both insert and update branches**

In `backend/app/services/sync_service.py`, find the account upsert loop (around line 135-165). Update both branches to call the new helper.

Replace:

```python
            if existing_account:
                existing_account.name = account_data.name
                existing_account.account_type = account_data.account_type
                existing_account.institution = account_data.institution
                existing_account.currency = account_data.currency
                ...
                existing_account.balance_available = account_data.balance_available
                self._set_account_external_id_fields(existing_account, account_data.external_id)
                ...
                synced_accounts.append(existing_account)
            else:
                ...
                    name=account_data.name,
                    account_type=account_data.account_type,
                    institution=account_data.institution,
                    currency=account_data.currency,
                    ...
                    balance_available=account_data.balance_available,
                ...
                self._set_account_external_id_fields(new_account, account_data.external_id)
                ...
                synced_accounts.append(new_account)
```

with the same code, but adding `self._set_account_iban_fields(<account>, account_data.iban)` immediately after each `_set_account_external_id_fields` call. Two call sites — one in the update branch, one in the insert branch.

Read the actual surrounding code first (`grep -n "_set_account_external_id_fields" backend/app/services/sync_service.py`) and place the new call adjacent on each call site. Do not refactor unrelated lines.

- [ ] **Step 5: Run tests to verify pass**

```bash
cd backend && .venv/bin/pytest tests/test_account_sync_encryption.py -v
```

Expected: all 3 new tests + existing tests pass.

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/sync_service.py backend/tests/test_account_sync_encryption.py
git commit -m "feat(sync): persist iban_ciphertext + iban_hash on synced accounts"
```

---

## Task 4: Generalize InternalTransferService detection

**Files:**
- Modify: `backend/app/services/internal_transfer_service.py:36-50, 68-180`
- Test: `backend/tests/test_internal_transfer_service.py`

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_internal_transfer_service.py`:

```python
def test_detect_synced_to_synced_no_mirror_link_only() -> None:
    """When the destination is a synced account, detection MUST NOT create a
    mirror — EB delivers the destination side independently. We still create
    an internal_transfers row with mirror_txn_id=NULL so the unlink endpoint
    works, and we mark the source as Transfer + include_in_analytics=False."""
    _ensure_schema()
    db = SessionLocal()
    user_id: Optional[str] = None
    try:
        from app.services.internal_transfer_service import InternalTransferService

        user = _make_user(db)
        user_id = user.id
        _make_transfer_category(db, user_id)
        synced_source = _make_synced_account(db, user_id, name="Main Checking")

        # Build a SYNCED destination account (provider='enable_banking') with iban_hash.
        synced_dest_iban = "NL55SYNCED0000000000"
        synced_dest = Account(
            user_id=user_id,
            name="Synced Savings",
            account_type="savings",
            institution="ABN AMRO",
            currency="EUR",
            provider="enable_banking",
            external_id=f"ext-{uuid.uuid4().hex[:12]}",
            iban_hash=blind_index(synced_dest_iban),
            is_active=True,
            starting_balance=Decimal("0"),
        )
        db.add(synced_dest)
        db.commit()

        src = _make_source_transaction(
            db, user_id, synced_source.id,
            counterparty_iban=synced_dest_iban,
            amount=Decimal("-200.00"),
        )

        service = InternalTransferService(db, user_id=user_id)
        result = service.detect_for_transactions([src.id])

        assert result["detected"] == 1, f"Expected 1 detection, got {result}"
        # Synced destinations don't need balance recalc (no mirror added) so
        # the touched-pockets list does NOT include the synced destination.
        assert synced_dest.id not in result["pocket_account_ids"]

        # Source flipped
        db.refresh(src)
        assert src.include_in_analytics is False
        assert src.internal_transfer_id is not None

        # Link row exists with mirror_txn_id=NULL
        link = (
            db.query(InternalTransfer)
            .filter(InternalTransfer.id == src.internal_transfer_id)
            .one()
        )
        assert link.mirror_txn_id is None, (
            "Synced destinations must NOT have a mirror — EB delivers that side independently"
        )
        assert link.source_account_id == synced_source.id
        assert link.pocket_account_id == synced_dest.id

        # CRUCIALLY: no mirror transaction was created on the synced destination
        mirror_count = (
            db.query(Transaction)
            .filter(Transaction.account_id == synced_dest.id)
            .count()
        )
        assert mirror_count == 0, (
            "Synced destination must not receive a mirror transaction"
        )
    finally:
        if user_id:
            _cleanup_user(db, user_id)
        db.close()


def test_detect_synced_to_manual_still_creates_mirror() -> None:
    """Existing PR #72 behavior must be preserved: synced→manual still creates a mirror."""
    _ensure_schema()
    db = SessionLocal()
    user_id: Optional[str] = None
    try:
        from app.services.internal_transfer_service import InternalTransferService

        user = _make_user(db)
        user_id = user.id
        _make_transfer_category(db, user_id)
        synced = _make_synced_account(db, user_id, name="Main Checking")
        pocket = _make_pocket_account(db, user_id, iban=POCKET_IBAN)
        src = _make_source_transaction(
            db, user_id, synced.id,
            counterparty_iban=POCKET_IBAN,
            amount=Decimal("-50.00"),
        )

        service = InternalTransferService(db, user_id=user_id)
        result = service.detect_for_transactions([src.id])

        assert result["detected"] == 1
        # Manual destination IS in the touched list (mirror created → balance recalc needed)
        assert pocket.id in result["pocket_account_ids"]

        # Mirror exists on pocket with sign-flipped amount
        mirror = (
            db.query(Transaction)
            .filter(Transaction.account_id == pocket.id)
            .one()
        )
        assert mirror.amount == Decimal("50.00")
    finally:
        if user_id:
            _cleanup_user(db, user_id)
        db.close()


def test_unlink_synced_to_synced_link_no_mirror_to_delete() -> None:
    """Unlinking a synced→synced link (mirror_txn_id=NULL) must restore the source
    and delete the link without erroring on the missing mirror."""
    _ensure_schema()
    db = SessionLocal()
    user_id: Optional[str] = None
    try:
        from app.services.internal_transfer_service import InternalTransferService

        user = _make_user(db)
        user_id = user.id
        _make_transfer_category(db, user_id)
        synced_source = _make_synced_account(db, user_id, name="Main")

        synced_dest_iban = "NL55SYNCED0000000000"
        synced_dest = Account(
            user_id=user_id, name="Synced Savings", account_type="savings",
            institution="ABN AMRO", currency="EUR", provider="enable_banking",
            external_id=f"ext-{uuid.uuid4().hex[:12]}",
            iban_hash=blind_index(synced_dest_iban),
            is_active=True, starting_balance=Decimal("0"),
        )
        db.add(synced_dest); db.commit()

        src = _make_source_transaction(
            db, user_id, synced_source.id,
            counterparty_iban=synced_dest_iban,
            amount=Decimal("-200.00"),
        )

        service = InternalTransferService(db, user_id=user_id)
        service.detect_for_transactions([src.id])
        link = db.query(InternalTransfer).filter_by(user_id=user_id).one()
        assert link.mirror_txn_id is None

        service.unlink(link.id)
        db.commit()

        # Source restored
        db.refresh(src)
        assert src.include_in_analytics is True
        assert src.internal_transfer_id is None
        # Link gone
        assert db.query(InternalTransfer).filter_by(user_id=user_id).count() == 0
    finally:
        if user_id:
            _cleanup_user(db, user_id)
        db.close()
```

Add the new tests to the `__main__` runner at the bottom of the file:

```python
        test_detect_synced_to_synced_no_mirror_link_only,
        test_detect_synced_to_manual_still_creates_mirror,
        test_unlink_synced_to_synced_link_no_mirror_to_delete,
```

- [ ] **Step 2: Run tests to verify failure**

```bash
cd backend && .venv/bin/pytest tests/test_internal_transfer_service.py::test_detect_synced_to_synced_no_mirror_link_only tests/test_internal_transfer_service.py::test_detect_synced_to_manual_still_creates_mirror tests/test_internal_transfer_service.py::test_unlink_synced_to_synced_link_no_mirror_to_delete -v
```

Expected: 3 FAILS — current detection filters on `provider='manual'` so synced destinations are skipped, and the new touched-pocket-id semantics aren't enforced.

- [ ] **Step 3: Generalize the account-IBAN map**

In `backend/app/services/internal_transfer_service.py`, replace `_load_pocket_map` with a generalized version. Find the existing method (around line 36):

```python
    def _load_pocket_map(self) -> Dict[str, Account]:
        """Return ``{iban_hash: pocket_account}`` for this user's active manual
        accounts that have an IBAN hash recorded.
        """
        pockets = (
            self.db.query(Account)
            .filter(
                Account.user_id == self.user_id,
                Account.provider == "manual",
                Account.iban_hash.isnot(None),
                Account.is_active.is_(True),
            )
            .all()
        )
        return {p.iban_hash: p for p in pockets}
```

Replace with:

```python
    def _load_user_account_iban_map(self) -> Dict[str, Account]:
        """Return ``{iban_hash: account}`` for ALL of this user's active accounts
        that have an IBAN hash recorded (synced and manual alike).

        The caller branches on ``account.provider`` to decide whether to mirror
        the transfer (manual destinations, where no other transaction source
        exists) or just tag and link it (synced destinations, where EB delivers
        the destination side's transaction independently).
        """
        accounts = (
            self.db.query(Account)
            .filter(
                Account.user_id == self.user_id,
                Account.iban_hash.isnot(None),
                Account.is_active.is_(True),
            )
            .all()
        )
        return {a.iban_hash: a for a in accounts}
```

- [ ] **Step 4: Update the call site + branch on provider**

Find `detect_for_transactions` in the same file. Replace the call to `_load_pocket_map()` with `_load_user_account_iban_map()`. Then, inside the per-transaction loop, branch on the matched account's provider when creating mirror + link.

Locate the existing block (around line 105-155) where the mirror is created:

```python
            mirror_amount = -src.amount
            mirror_functional = (
                -src.functional_amount if src.functional_amount is not None else None
            )

            src_account_name = getattr(src.account, "name", None) or "account"
            description = (
                f"Transfer from {src_account_name}"
                if mirror_amount > 0
                else f"Transfer to {src_account_name}"
            )

            mirror = Transaction(
                user_id=self.user_id,
                account_id=pocket.id,
                external_id=f"mirror-{src.id}",
                amount=mirror_amount,
                currency=src.currency,
                functional_amount=mirror_functional,
                description=description,
                merchant=src_account_name,
                booked_at=src.booked_at,
                transaction_type="credit" if mirror_amount > 0 else "debit",
                category_system_id=transfer_category_id,
                include_in_analytics=False,
            )
            self.db.add(mirror)
            self.db.flush()  # assigns mirror.id

            link = InternalTransfer(
                user_id=self.user_id,
                source_txn_id=src.id,
                mirror_txn_id=mirror.id,
                source_account_id=src.account_id,
                pocket_account_id=pocket.id,
                amount=abs(src.amount),
                currency=src.currency,
            )
```

Replace with:

```python
            # Branch on destination provider:
            #  - manual → create mirror so the manual side's balance reflects the transfer
            #  - synced → no mirror (EB delivers that side's transaction independently);
            #    still record an internal_transfers link with mirror_txn_id=NULL so the
            #    unlink endpoint and analytics flag work the same way for both shapes.
            mirror_id: Optional[UUID] = None
            if pocket.provider == "manual":
                mirror_amount = -src.amount
                mirror_functional = (
                    -src.functional_amount if src.functional_amount is not None else None
                )

                src_account_name = getattr(src.account, "name", None) or "account"
                description = (
                    f"Transfer from {src_account_name}"
                    if mirror_amount > 0
                    else f"Transfer to {src_account_name}"
                )

                mirror = Transaction(
                    user_id=self.user_id,
                    account_id=pocket.id,
                    external_id=f"mirror-{src.id}",
                    amount=mirror_amount,
                    currency=src.currency,
                    functional_amount=mirror_functional,
                    description=description,
                    merchant=src_account_name,
                    booked_at=src.booked_at,
                    transaction_type="credit" if mirror_amount > 0 else "debit",
                    category_system_id=transfer_category_id,
                    include_in_analytics=False,
                )
                self.db.add(mirror)
                self.db.flush()  # assigns mirror.id
                mirror_id = mirror.id

            link = InternalTransfer(
                user_id=self.user_id,
                source_txn_id=src.id,
                mirror_txn_id=mirror_id,  # None for synced destinations
                source_account_id=src.account_id,
                pocket_account_id=pocket.id,
                amount=abs(src.amount),
                currency=src.currency,
            )
```

Right below this block, find where `touched_pockets.add(...)` is called. Update it so synced destinations are NOT added (no balance recalc needed since no mirror was created):

Find:

```python
            touched_pockets.add(pocket.id)
            detected += 1
```

Replace with:

```python
            # Only manual destinations get added to the recalc set — they're the
            # only ones where a mirror transaction was created and the balance
            # needs to be recomputed. Synced destinations get their transactions
            # (and therefore their balance) directly from EB.
            if pocket.provider == "manual":
                touched_pockets.add(pocket.id)
            detected += 1
```

Also add the missing import at the top of the file if not already present:

```python
from typing import Dict, List, Optional
from uuid import UUID
```

Check both — they're likely already imported (used elsewhere). Don't duplicate.

- [ ] **Step 5: Run tests to verify pass**

```bash
cd backend && .venv/bin/pytest tests/test_internal_transfer_service.py -v
```

Expected: all tests pass — the 3 new ones plus all 8 existing ones from PR #72.

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/internal_transfer_service.py backend/tests/test_internal_transfer_service.py
git commit -m "feat(transfers): generalize detection to recognize all user IBANs"
```

---

## Task 5: Pipeline integration test (synced↔synced end-to-end)

**Files:**
- Test: `backend/tests/test_post_import_pipeline.py`

This is a new integration test verifying the full pipeline behavior end-to-end with two synced accounts. No production code change.

- [ ] **Step 1: Write the test**

Append to `backend/tests/test_post_import_pipeline.py`:

```python
def test_pipeline_synced_to_synced_tags_transfer_no_mirror() -> None:
    """End-to-end: a sync delivers a checking transaction whose counterparty IBAN
    matches another synced account. Pipeline detection must:
      - tag source transaction as Transfer + include_in_analytics=False
      - create internal_transfers link with mirror_txn_id=NULL
      - NOT add any transaction to the destination account
      - NOT extend balance recalc to the destination account
    """
    _ensure_schema()
    db = SessionLocal()
    user_id: Optional[str] = None
    try:
        from tasks.post_import_pipeline import _run_post_import_pipeline
        from app.security.data_encryption import (
            blind_index,
            encrypt_value,
            reset_encryption_config_cache,
        )

        user = _make_user(db)
        user_id = user.id

        # Two synced accounts: ABN checking (source), Revo Pocket (synced savings dest).
        # Both have iban_hash populated as if the upstream sync wrote them.
        checking_iban = "NL11ABNA0000000001"
        pocket_iban = "NL22REVO0000000002"

        checking = Account(
            user_id=user_id, name="ABN Checking", account_type="checking",
            institution="ABN AMRO", currency="EUR",
            provider="enable_banking", external_id="ext-checking",
            iban_ciphertext=encrypt_value(checking_iban),
            iban_hash=blind_index(checking_iban),
            is_active=True, starting_balance=Decimal("0"),
        )
        pocket = Account(
            user_id=user_id, name="Revo Pocket", account_type="savings",
            institution="Revolut", currency="EUR",
            provider="enable_banking", external_id="ext-pocket",
            iban_ciphertext=encrypt_value(pocket_iban),
            iban_hash=blind_index(pocket_iban),
            is_active=True, starting_balance=Decimal("0"),
        )
        cat = Category(
            user_id=user_id, name="Transfer", category_type="transfer", is_system=True,
        )
        db.add_all([checking, pocket, cat])
        db.commit()

        src = Transaction(
            user_id=user_id, account_id=checking.id, external_id="src-1",
            amount=Decimal("-200.00"), currency="EUR",
            functional_amount=Decimal("-200.00"),
            description="Transfer to savings", merchant=None,
            booked_at=datetime(2026, 4, 25, tzinfo=timezone.utc),
            transaction_type="debit",
            counterparty_iban_ciphertext=encrypt_value(pocket_iban),
            counterparty_iban_hash=blind_index(pocket_iban),
            include_in_analytics=True,
        )
        db.add(src)
        db.commit()

        # Patch the LLM step so the test stays hermetic
        from app.services.category_matcher import CategoryMatcher
        with patch.object(CategoryMatcher, "match_categories_batch_llm",
                          return_value=({}, 0, 0.0)):
            _run_post_import_pipeline(
                user_id=user_id,
                account_ids=[str(checking.id)],  # only source in scope (typical sync)
                transaction_ids=[str(src.id)],
                is_initial_sync=False,
            )

        # Source flipped
        db.refresh(src)
        assert src.include_in_analytics is False
        assert src.internal_transfer_id is not None

        # Link with mirror_txn_id=NULL (no mirror)
        link = (
            db.query(InternalTransfer)
            .filter(InternalTransfer.id == src.internal_transfer_id)
            .one()
        )
        assert link.mirror_txn_id is None
        assert link.pocket_account_id == pocket.id

        # No transaction added to the synced destination
        assert (
            db.query(Transaction)
            .filter(Transaction.account_id == pocket.id)
            .count()
            == 0
        )
    finally:
        if user_id:
            _cleanup_user(db, user_id)
        db.close()
```

Add to the `__main__` test runner at the bottom of the file:

```python
        test_pipeline_synced_to_synced_tags_transfer_no_mirror,
```

- [ ] **Step 2: Run the test**

```bash
cd backend && .venv/bin/pytest tests/test_post_import_pipeline.py::test_pipeline_synced_to_synced_tags_transfer_no_mirror -v
```

Expected: PASS — the implementation from Task 4 already handles this end-to-end.

- [ ] **Step 3: Run the full pipeline test file**

```bash
cd backend && .venv/bin/pytest tests/test_post_import_pipeline.py -v
```

Expected: all tests pass.

- [ ] **Step 4: Commit**

```bash
git add backend/tests/test_post_import_pipeline.py
git commit -m "test(pipeline): synced-to-synced transfer detection e2e"
```

---

## Task 6: Full regression run + open PR

**Files:** none (verification + git only)

- [ ] **Step 1: Run the full pocket-accounts test suite**

```bash
cd backend && .venv/bin/pytest tests/test_enable_banking_adapter.py tests/test_account_sync_encryption.py tests/test_internal_transfer_service.py tests/test_post_import_pipeline.py tests/test_pocket_account_routes.py -v
```

Expected: every test passes — 13 (adapter) + previous sync tests + 3 (sync IBAN) + 11 (transfer service: 8 existing + 3 new) + 4 (pipeline: 3 existing + 1 new) + 7 (pocket routes).

- [ ] **Step 2: Push branch and open PR**

```bash
git push -u origin explore/savings-balance-detection
gh pr create --title "feat: recognize own IBANs across all accounts (synced + manual)" --body "$(cat <<'EOF'
## Summary

Generalizes PR #72's pocket-account detection to recognize ALL of the user's
own IBANs:

- Sync now persists \`iban_ciphertext\` + \`iban_hash\` on synced (EB-connected)
  accounts. PR #72 only set these on manual pockets.
- Internal-transfer detection drops its \`provider='manual'\` filter and
  matches counterparty IBAN against any user account.
- For manual destinations: existing PR #72 mirror behavior preserved (balance
  reflects detected transfers).
- For synced destinations: no mirror is created (EB delivers the destination
  side independently). We still write an \`internal_transfers\` row with
  \`mirror_txn_id=NULL\` so the unlink endpoint works the same way and the
  source's \`include_in_analytics\` is correctly flipped.

Manual reconciliation (the \`Adjust\` button on the Edit Account dialog → drift
correction via \`Balancing Transfer\` category) already works for any account —
no UI change.

**Spec:** \`docs/superpowers/specs/2026-04-25-recognize-own-ibans-design.md\`

## Test plan

- [x] Unit tests for adapter \`AccountData.iban\` extraction (2)
- [x] Sync persists IBAN on first sync, doesn't overwrite, skips when None (3)
- [x] Detection: synced→synced creates link with \`mirror_txn_id=NULL\`, no mirror; synced→manual still creates mirror (3)
- [x] Unlink works on a synced↔synced link (mirror=NULL) (1)
- [x] Pipeline e2e: synced→synced tags transfer, no destination mutation (1)
- [ ] Manual: deploy backend + worker, trigger ABN sync, verify \`accounts.iban_hash\` populated for all synced accounts via Drizzle Studio
- [ ] Manual: trigger another sync after IBANs are populated, verify any \`counterparty_iban\` ABN→Revo or ABN→ABN-pocket transfer is auto-tagged as Transfer

## Risk

Low. The detection branch on provider only takes a different code path; the existing manual-pocket flow is unchanged. No schema changes (columns + index from PR #72 are reused). Rollback = redeploy prior backend image.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

- [ ] **Step 3: Wait for CI**

Monitor with:

```bash
gh pr checks <PR_NUMBER>
```

Expected: all 8 checks pass (build backend, build frontend, build-and-test, Compose Smoke Test, Vercel, Vercel Preview Comments, cubic).

- [ ] **Step 4: Address any cubic findings**

If cubic flags issues, fix inline, push, and re-check CI.

- [ ] **Step 5: Squash-merge**

```bash
gh pr merge <PR_NUMBER> --squash
git push origin --delete explore/savings-balance-detection
```

---

## Task 7: Deploy and verify in production

**Files:** none (deploy + smoke test)

- [ ] **Step 1: Wait for the docker build on main**

Monitor with:

```bash
gh run list --limit 1 --workflow docker-build.yml --branch main
```

Wait for `completed success`.

- [ ] **Step 2: Redeploy backend services**

```bash
RAILWAY_ENVIRONMENT=production railway redeploy --service backend --yes
RAILWAY_ENVIRONMENT=production railway redeploy --service worker --yes
RAILWAY_ENVIRONMENT=production railway redeploy --service beat --yes
RAILWAY_ENVIRONMENT=production railway redeploy --service mcp --yes
```

Wait for each to reach SUCCESS:

```bash
for svc in backend worker beat mcp; do
  echo "--- $svc ---"
  railway service status --service $svc
done
```

- [ ] **Step 3: Verify the new code is live**

Run a synced-account-IBAN backfill check via railway ssh to the app service:

```bash
CMD='node -e "
const postgres = require(\"postgres\");
const sql = postgres(process.env.DATABASE_URL);
(async () => {
  const before = await sql\`SELECT provider, COUNT(*)::int AS total, COUNT(iban_hash)::int AS with_iban_hash FROM accounts GROUP BY provider ORDER BY total DESC\`;
  console.log(JSON.stringify(before, null, 2));
  await sql.end();
})().catch(e => { console.error(e); process.exit(1); });
"'
railway ssh --service app "$CMD"
```

Note the current state — synced accounts will still have `with_iban_hash=0` until a sync runs.

- [ ] **Step 4: Trigger a sync on the ABN connection**

User-driven: open https://app.syllogic.ai/settings → Bank Connections → "Sync Now" on ABN AMRO.

Monitor worker logs:

```bash
railway logs --service worker | grep -E "EB_DEBUG|extracted_creditor_iban|extracted_debtor_iban|INTERNAL_TRANSFER" | tail -40
```

Expected:
- New `[EB_DEBUG]` lines now print `creditor_account=...` and `debtor_account=...` directly (already deployed via PR #83)
- `extracted_creditor_iban='NL...'` should be non-null on SEPA transfers
- `[INTERNAL_TRANSFER] Detected N transfer(s) for user ...` line appears with N > 0

- [ ] **Step 5: Re-check the database**

Run the same query from Step 3. Expected:
- `enable_banking` row's `with_iban_hash` jumps from 0 to a non-zero count (one per synced account that has an IBAN)
- Count of `internal_transfers` rows > 0 if any of the just-synced transactions matched another user account's IBAN

```bash
CMD='node -e "
const postgres = require(\"postgres\");
const sql = postgres(process.env.DATABASE_URL);
(async () => {
  const a = await sql\`SELECT provider, COUNT(*)::int AS total, COUNT(iban_hash)::int AS with_iban_hash FROM accounts GROUP BY provider\`;
  console.log(\"ACCOUNTS:\", JSON.stringify(a));
  const t = await sql\`SELECT COUNT(*)::int AS total, COUNT(counterparty_iban_hash)::int AS with_cp, COUNT(internal_transfer_id)::int AS linked FROM transactions\`;
  console.log(\"TXNS:\", JSON.stringify(t[0]));
  const it = await sql\`SELECT COUNT(*)::int AS total, COUNT(mirror_txn_id)::int AS with_mirror FROM internal_transfers\`;
  console.log(\"LINKS:\", JSON.stringify(it[0]));
  await sql.end();
})().catch(e => { console.error(e); process.exit(1); });
"'
railway ssh --service app "$CMD"
```

- [ ] **Step 6: Manual UI verification**

In the production app:
1. Open `/transactions`, find an ABN→ABN-pocket transfer
2. Click into the transaction detail sheet
3. Confirm the **"Internal transfer — ABN Long Term Savings"** chip appears at the top
4. Confirm `include_in_analytics` is reflected in dashboard charts (transfer should not appear in "spending" charts)
5. Confirm the ABN Long Term Savings pocket balance has updated to reflect the detected transfer

If any step is unexpected, capture logs and inspect the link rows in the DB.

---

## Completion criteria

- All 7 tasks checked off
- All tests pass: `cd backend && .venv/bin/pytest tests/test_enable_banking_adapter.py tests/test_account_sync_encryption.py tests/test_internal_transfer_service.py tests/test_post_import_pipeline.py tests/test_pocket_account_routes.py -v`
- PR merged, all 4 backend services redeployed
- Smoke test passes: synced accounts have `iban_hash` populated; internal transfers detected with appropriate mirror/no-mirror behavior; UI chips appear correctly
