# Pocket Account Tracking Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let users register unsyncable savings accounts ("pockets") by IBAN, then auto-detect internal transfers from the synced parent, create mirror transactions so balances derive naturally, and exclude transfers from analytics.

**Architecture:** Three schema additions (IBAN fields on `accounts`, counterparty IBAN on `transactions`, a new `internal_transfers` table). The Enable Banking adapter extracts counterparty IBAN, the sync service encrypts and hashes it on persist, and a new `InternalTransferService` runs detection as a step in the post-import pipeline. A new backend endpoint creates pocket accounts with IBAN, backfilling matches. Frontend gets an IBAN input, a "pocket" badge, an internal-transfer chip on transactions, and an unlink action.

**Tech Stack:** Drizzle (schema source of truth) + SQLAlchemy (backend mirror), Next.js server actions, FastAPI + Celery, AES-GCM + HMAC-SHA256 blind index via existing `data_encryption` module, pytest + vitest.

**Spec:** `docs/superpowers/specs/2026-04-19-pocket-accounts-design.md`

**Scope note — IBAN editing:** this plan implements IBAN assignment at pocket creation only. Editing an existing pocket account's IBAN is out of scope; users can delete and recreate. This keeps the surface area small for v1 and avoids the edge case of "partially migrated" internal transfer links.

---

## File Structure

| File | Responsibility |
|------|----------------|
| `frontend/lib/db/schema.ts` | Drizzle schema — source of truth |
| `backend/app/models.py` | SQLAlchemy mirror |
| `frontend/lib/db/migrations/NNNN_*.sql` | Generated migration |
| `backend/app/integrations/base.py` | Add `counterparty_iban` to `TransactionData` |
| `backend/app/integrations/enable_banking_adapter.py` | Extract IBAN from EB raw payload |
| `backend/app/services/sync_service.py` | Encrypt + hash IBAN on persist |
| `backend/app/services/internal_transfer_service.py` | NEW — detect/unlink internal transfers |
| `backend/tasks/post_import_pipeline.py` | Add detection step; filter LLM by `include_in_analytics` |
| `backend/app/routes/accounts.py` | NEW endpoints — create pocket, unlink internal transfer, delete cleanup |
| `frontend/lib/actions/accounts.ts` | Route IBAN ops through backend; new `unlinkInternalTransfer` |
| `frontend/components/accounts/account-form.tsx` | IBAN input + validation |
| `frontend/components/transactions/transaction-row-details.tsx` | Internal-transfer chip |
| `frontend/components/accounts/account-header.tsx` | "Pocket" badge |

---

## Task 1: Add IBAN fields to `accounts` schema

**Files:**
- Modify: `frontend/lib/db/schema.ts`
- Modify: `backend/app/models.py`
- Create: `frontend/lib/db/migrations/<next>_add_pocket_account_fields.sql` (auto-generated)

- [ ] **Step 1: Add Drizzle columns**

In `frontend/lib/db/schema.ts`, inside the `accounts` pgTable block, add after `externalIdHash`:

```typescript
    ibanCiphertext: text("iban_ciphertext"),
    ibanHash: varchar("iban_hash", { length: 64 }),
```

And in the table options block, add an index:

```typescript
    index("idx_accounts_user_iban_hash").on(table.userId, table.ibanHash),
```

- [ ] **Step 2: Add SQLAlchemy columns**

In `backend/app/models.py`, locate the `Account` model and add inside the columns (after `external_id_hash`):

```python
    iban_ciphertext = Column(Text, nullable=True)
    iban_hash = Column(String(64), nullable=True, index=False)  # composite index defined in __table_args__
```

Then update `__table_args__` to include:

```python
    Index("idx_accounts_user_iban_hash", "user_id", "iban_hash"),
```

- [ ] **Step 3: Generate migration**

```bash
cd frontend && pnpm db:generate
```

Expected: new `NNNN_*.sql` file created adding the two columns and index. Inspect the generated SQL to confirm.

- [ ] **Step 4: Apply migration locally**

```bash
cd frontend && pnpm db:push
```

Expected: migration applies cleanly, no errors.

- [ ] **Step 5: Commit**

```bash
git add frontend/lib/db/schema.ts backend/app/models.py frontend/lib/db/migrations/
git commit -m "feat(db): add iban_ciphertext and iban_hash to accounts"
```

---

## Task 2: Add counterparty IBAN fields to `transactions` schema

**Files:**
- Modify: `frontend/lib/db/schema.ts`
- Modify: `backend/app/models.py`

- [ ] **Step 1: Add Drizzle columns**

In `frontend/lib/db/schema.ts`, inside the `transactions` pgTable block, add after `debtor`:

```typescript
    counterpartyIbanCiphertext: text("counterparty_iban_ciphertext"),
    counterpartyIbanHash: varchar("counterparty_iban_hash", { length: 64 }),
    internalTransferId: uuid("internal_transfer_id"),  // FK added in Task 3
```

Add an index in the options block:

```typescript
    index("idx_transactions_user_counterparty_iban").on(table.userId, table.counterpartyIbanHash),
```

- [ ] **Step 2: Add SQLAlchemy columns**

In `backend/app/models.py`, inside `Transaction`:

```python
    counterparty_iban_ciphertext = Column(Text, nullable=True)
    counterparty_iban_hash = Column(String(64), nullable=True)
    internal_transfer_id = Column(UUID(as_uuid=True), nullable=True)  # FK constraint added via __table_args__ after Task 3
```

Add to `__table_args__`:

```python
    Index("idx_transactions_user_counterparty_iban", "user_id", "counterparty_iban_hash"),
```

- [ ] **Step 3: Generate and apply migration**

```bash
cd frontend && pnpm db:generate && pnpm db:push
```

Expected: new columns + index present.

- [ ] **Step 4: Commit**

```bash
git add frontend/lib/db/schema.ts backend/app/models.py frontend/lib/db/migrations/
git commit -m "feat(db): add counterparty IBAN fields to transactions"
```

---

## Task 3: Add `internal_transfers` table

**Files:**
- Modify: `frontend/lib/db/schema.ts`
- Modify: `backend/app/models.py`

- [ ] **Step 1: Add Drizzle table**

In `frontend/lib/db/schema.ts`, after `transactions` block and before `accountBalances`, add:

```typescript
export const internalTransfers = pgTable(
  "internal_transfers",
  {
    id: uuid("id").defaultRandom().primaryKey(),
    userId: text("user_id")
      .references(() => users.id, { onDelete: "cascade" })
      .notNull(),
    sourceTxnId: uuid("source_txn_id")
      .references(() => transactions.id, { onDelete: "cascade" })
      .notNull()
      .unique(),
    mirrorTxnId: uuid("mirror_txn_id")
      .references(() => transactions.id, { onDelete: "set null" })
      .unique(),
    sourceAccountId: uuid("source_account_id")
      .references(() => accounts.id, { onDelete: "cascade" })
      .notNull(),
    pocketAccountId: uuid("pocket_account_id")
      .references(() => accounts.id, { onDelete: "cascade" })
      .notNull(),
    amount: decimal("amount", { precision: 15, scale: 2 }).notNull(),
    currency: char("currency", { length: 3 }).notNull(),
    detectedAt: timestamp("detected_at").defaultNow(),
    createdAt: timestamp("created_at").defaultNow(),
  },
  (table) => [
    index("idx_internal_transfers_user").on(table.userId),
    index("idx_internal_transfers_pocket").on(table.pocketAccountId),
  ]
);
```

Then wire the FK on `transactions.internalTransferId` — change the column added in Task 2 to:

```typescript
    internalTransferId: uuid("internal_transfer_id").references(() => internalTransfers.id, { onDelete: "set null" }),
```

- [ ] **Step 2: Add SQLAlchemy model**

In `backend/app/models.py`, add a new class `InternalTransfer`:

```python
class InternalTransfer(Base):
    __tablename__ = "internal_transfers"

    id = Column(UUID(as_uuid=True), primary_key=True, server_default=sa_text("gen_random_uuid()"))
    user_id = Column(Text, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    source_txn_id = Column(UUID(as_uuid=True), ForeignKey("transactions.id", ondelete="CASCADE"), nullable=False, unique=True)
    mirror_txn_id = Column(UUID(as_uuid=True), ForeignKey("transactions.id", ondelete="SET NULL"), unique=True, nullable=True)
    source_account_id = Column(UUID(as_uuid=True), ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False)
    pocket_account_id = Column(UUID(as_uuid=True), ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False)
    amount = Column(Numeric(15, 2), nullable=False)
    currency = Column(String(3), nullable=False)
    detected_at = Column(DateTime, server_default=sa_func.now())
    created_at = Column(DateTime, server_default=sa_func.now())

    __table_args__ = (
        Index("idx_internal_transfers_user", "user_id"),
        Index("idx_internal_transfers_pocket", "pocket_account_id"),
    )
```

Update `Transaction.__table_args__` / column FK: the `internal_transfer_id` column now has a real FK to `internal_transfers.id`:

```python
    internal_transfer_id = Column(
        UUID(as_uuid=True),
        ForeignKey("internal_transfers.id", ondelete="SET NULL"),
        nullable=True,
    )
```

- [ ] **Step 3: Generate and apply migration**

```bash
cd frontend && pnpm db:generate && pnpm db:push
```

Expected: `internal_transfers` table created with FKs and indexes; `transactions.internal_transfer_id` FK added.

- [ ] **Step 4: Verify schema**

```bash
cd frontend && pnpm db:studio
```

Open studio, confirm the new table exists with correct columns and FKs. (Manual visual check — no automated test yet; service tests come in Task 6.)

- [ ] **Step 5: Commit**

```bash
git add frontend/lib/db/schema.ts backend/app/models.py frontend/lib/db/migrations/
git commit -m "feat(db): add internal_transfers table"
```

---

## Task 4: Extract counterparty IBAN in Enable Banking adapter

**Files:**
- Modify: `backend/app/integrations/base.py` (add field to `TransactionData`)
- Modify: `backend/app/integrations/enable_banking_adapter.py`
- Test: `backend/tests/test_enable_banking_adapter.py`

- [ ] **Step 1: Write failing test**

Append to `backend/tests/test_enable_banking_adapter.py`:

```python
def test_normalize_extracts_counterparty_iban_from_creditor_account_iban():
    adapter = EnableBankingAdapter(token="tok", base_url="https://example.com")
    raw = {
        "transaction_id": "tx-1",
        "account_id": "acc-1",
        "transaction_amount": {"amount": "12.50", "currency": "EUR"},
        "credit_debit_indicator": "DBIT",
        "booking_date": "2026-04-01",
        "creditor_account": {"iban": "NL91 ABNA 0417 1643 00"},
        "debtor_account": {"iban": "NL02 RABO 0123 4567 89"},
        "creditor": {"name": "Some Merchant"},
    }
    txn = adapter.normalize_transaction(raw)
    # Outflow (DBIT) → counterparty is the creditor IBAN, stripped of spaces and upper-cased
    assert txn.counterparty_iban == "NL91ABNA0417164300"


def test_normalize_extracts_counterparty_iban_from_nested_creditor():
    adapter = EnableBankingAdapter(token="tok", base_url="https://example.com")
    raw = {
        "transaction_id": "tx-2",
        "account_id": "acc-1",
        "transaction_amount": {"amount": "5.00", "currency": "EUR"},
        "credit_debit_indicator": "CRDT",
        "booking_date": "2026-04-01",
        "creditor_account": None,
        "debtor_account": None,
        "debtor": {"name": "Friend", "iban": "BE68539007547034"},
    }
    txn = adapter.normalize_transaction(raw)
    # Inflow (CRDT) → counterparty is the debtor IBAN
    assert txn.counterparty_iban == "BE68539007547034"


def test_normalize_handles_missing_iban_gracefully():
    adapter = EnableBankingAdapter(token="tok", base_url="https://example.com")
    raw = {
        "transaction_id": "tx-3",
        "account_id": "acc-1",
        "transaction_amount": {"amount": "5.00", "currency": "EUR"},
        "credit_debit_indicator": "DBIT",
        "booking_date": "2026-04-01",
    }
    txn = adapter.normalize_transaction(raw)
    assert txn.counterparty_iban is None
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd backend && pytest tests/test_enable_banking_adapter.py -v -k counterparty_iban
```

Expected: FAIL with `AttributeError: 'TransactionData' object has no attribute 'counterparty_iban'`.

- [ ] **Step 3: Add field to `TransactionData`**

In `backend/app/integrations/base.py`, inside `class TransactionData`, add after `debtor`:

```python
    counterparty_iban: Optional[str] = None  # IBAN of the other party (stripped, upper-cased)
```

- [ ] **Step 4: Extract IBAN in the adapter**

In `backend/app/integrations/enable_banking_adapter.py`, add a module-level helper above the class:

```python
def _extract_iban(account_obj) -> Optional[str]:
    if not isinstance(account_obj, dict):
        return None
    iban = account_obj.get("iban")
    if iban:
        return iban.replace(" ", "").upper()
    if (account_obj.get("scheme_name") or "").upper() == "IBAN":
        ident = account_obj.get("identification")
        if ident:
            return ident.replace(" ", "").upper()
    return None
```

Then inside `normalize_transaction`, after the existing `credit_debit = ...` line and before the sign-flip logic, compute the counterparty IBAN:

```python
        creditor_iban = (
            _extract_iban(raw.get("creditor_account"))
            or _extract_iban(raw.get("creditor"))
        )
        debtor_iban = (
            _extract_iban(raw.get("debtor_account"))
            or _extract_iban(raw.get("debtor"))
        )
        counterparty_iban = creditor_iban if credit_debit == "DBIT" else debtor_iban
```

And pass it through in the `TransactionData(...)` return:

```python
        return TransactionData(
            # ... existing fields ...
            counterparty_iban=counterparty_iban,
            metadata={"raw": raw},
        )
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
cd backend && pytest tests/test_enable_banking_adapter.py -v
```

Expected: all counterparty_iban tests PASS; all previously-passing tests still PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/integrations/base.py backend/app/integrations/enable_banking_adapter.py backend/tests/test_enable_banking_adapter.py
git commit -m "feat(eb): extract counterparty IBAN from Enable Banking payload"
```

---

## Task 5: Persist encrypted counterparty IBAN during sync

**Files:**
- Modify: `backend/app/services/sync_service.py`
- Test: `backend/tests/test_account_sync_encryption.py`

- [ ] **Step 1: Write failing test**

Append to `backend/tests/test_account_sync_encryption.py`:

```python
def test_sync_service_persists_encrypted_counterparty_iban(db_session, user_with_manual_account, monkeypatch):
    # Force encryption on for this test
    monkeypatch.setenv("DATA_ENCRYPTION_KEY_CURRENT", "0" * 64)  # 32-byte hex zero key for deterministic test
    from backend.app.security.data_encryption import reset_encryption_config_cache
    reset_encryption_config_cache()

    from backend.app.services.sync_service import SyncService
    from backend.app.integrations.base import TransactionData
    from decimal import Decimal
    from datetime import datetime, timezone

    user = user_with_manual_account["user"]
    account = user_with_manual_account["account"]
    service = SyncService(db_session, user_id=user.id, use_llm_categorization=False)

    td = TransactionData(
        external_id="ext-1",
        account_external_id=account.external_id,
        amount=Decimal("-10.00"),
        currency="EUR",
        description="Test",
        counterparty_iban="NL91ABNA0417164300",
        booked_at=datetime(2026, 4, 1, tzinfo=timezone.utc),
        transaction_type="debit",
    )

    service.upsert_transactions(account, [td])
    db_session.commit()

    from backend.app.models import Transaction
    from backend.app.security.data_encryption import decrypt_value, blind_index

    row = db_session.query(Transaction).filter_by(external_id="ext-1").one()
    assert row.counterparty_iban_ciphertext is not None
    assert row.counterparty_iban_ciphertext.startswith("enc:v1:")
    assert decrypt_value(row.counterparty_iban_ciphertext) == "NL91ABNA0417164300"
    assert row.counterparty_iban_hash == blind_index("NL91ABNA0417164300")
```

(If `user_with_manual_account` fixture does not yet exist, add it to `conftest.py` creating a user plus one account with `provider="manual"`, `external_id="acc-ext"`.)

- [ ] **Step 2: Run test to verify it fails**

```bash
cd backend && pytest tests/test_account_sync_encryption.py::test_sync_service_persists_encrypted_counterparty_iban -v
```

Expected: FAIL — the sync service currently ignores `counterparty_iban`.

- [ ] **Step 3: Implement**

In `backend/app/services/sync_service.py`, locate the section where a `Transaction` is built from `TransactionData` (search for `Transaction(` within `upsert_transactions` or equivalent). Add:

```python
from app.security.data_encryption import encrypt_value, blind_index

# ... inside the mapping where fields are set on a new/updated Transaction row ...
if td.counterparty_iban:
    txn.counterparty_iban_ciphertext = encrypt_value(td.counterparty_iban)
    txn.counterparty_iban_hash = blind_index(td.counterparty_iban)
else:
    txn.counterparty_iban_ciphertext = None
    txn.counterparty_iban_hash = None
```

Apply this for both the insert branch and the update branch so re-synced transactions pick up IBAN on subsequent runs.

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd backend && pytest tests/test_account_sync_encryption.py -v
```

Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/sync_service.py backend/tests/test_account_sync_encryption.py
git commit -m "feat(sync): persist encrypted counterparty IBAN + blind index"
```

---

## Task 6: `InternalTransferService` — detect, unlink, unlink_all_for_pocket

**Files:**
- Create: `backend/app/services/internal_transfer_service.py`
- Create: `backend/tests/test_internal_transfer_service.py`

- [ ] **Step 1: Write failing test**

Create `backend/tests/test_internal_transfer_service.py`:

```python
import pytest
from decimal import Decimal
from datetime import datetime, timezone
from uuid import UUID

from app.models import Account, Transaction, InternalTransfer, Category
from app.services.internal_transfer_service import InternalTransferService
from app.security.data_encryption import encrypt_value, blind_index, reset_encryption_config_cache


@pytest.fixture(autouse=True)
def _enable_encryption(monkeypatch):
    monkeypatch.setenv("DATA_ENCRYPTION_KEY_CURRENT", "0" * 64)
    reset_encryption_config_cache()
    yield
    reset_encryption_config_cache()


@pytest.fixture
def user_with_synced_and_pocket(db_session):
    """User with one synced main account and one manual pocket account with IBAN."""
    from tests.helpers import create_user  # expected existing test helper
    user = create_user(db_session)

    pocket_iban = "NL91ABNA0417164300"
    synced = Account(
        user_id=user.id, name="Main", account_type="checking",
        provider="gocardless", external_id="acc-synced", currency="EUR",
        starting_balance=Decimal("0"),
    )
    pocket = Account(
        user_id=user.id, name="Savings Pocket", account_type="savings",
        provider="manual", currency="EUR", starting_balance=Decimal("0"),
        iban_ciphertext=encrypt_value(pocket_iban),
        iban_hash=blind_index(pocket_iban),
    )
    # Transfer category
    transfer_cat = Category(
        user_id=user.id, name="Transfer", category_type="transfer", is_system=True,
    )
    db_session.add_all([synced, pocket, transfer_cat])
    db_session.commit()
    return {"user": user, "synced": synced, "pocket": pocket, "transfer_cat": transfer_cat, "pocket_iban": pocket_iban}


def test_detect_creates_mirror_and_marks_source_not_in_analytics(db_session, user_with_synced_and_pocket):
    ctx = user_with_synced_and_pocket
    src = Transaction(
        user_id=ctx["user"].id,
        account_id=ctx["synced"].id,
        external_id="ext-1",
        amount=Decimal("-50.00"),
        currency="EUR",
        description="To savings",
        booked_at=datetime(2026, 4, 1, tzinfo=timezone.utc),
        transaction_type="debit",
        counterparty_iban_ciphertext=encrypt_value(ctx["pocket_iban"]),
        counterparty_iban_hash=blind_index(ctx["pocket_iban"]),
        include_in_analytics=True,
    )
    db_session.add(src)
    db_session.commit()

    service = InternalTransferService(db_session, user_id=ctx["user"].id)
    count = service.detect_for_transactions([src.id])

    assert count == 1

    # Source flipped
    db_session.refresh(src)
    assert src.include_in_analytics is False
    assert src.internal_transfer_id is not None

    # Mirror exists on pocket
    mirror = db_session.query(Transaction).filter_by(account_id=ctx["pocket"].id).one()
    assert mirror.amount == Decimal("50.00")  # sign flipped
    assert mirror.currency == "EUR"
    assert mirror.include_in_analytics is False
    assert mirror.category_system_id == ctx["transfer_cat"].id
    assert mirror.external_id == f"mirror-{src.id}"
    assert mirror.transaction_type == "credit"

    # InternalTransfer row
    it = db_session.query(InternalTransfer).filter_by(source_txn_id=src.id).one()
    assert it.mirror_txn_id == mirror.id
    assert it.amount == Decimal("50.00")
    assert it.currency == "EUR"
    assert it.source_account_id == ctx["synced"].id
    assert it.pocket_account_id == ctx["pocket"].id


def test_detect_is_idempotent(db_session, user_with_synced_and_pocket):
    ctx = user_with_synced_and_pocket
    src = Transaction(
        user_id=ctx["user"].id, account_id=ctx["synced"].id, external_id="ext-2",
        amount=Decimal("-5.00"), currency="EUR", description="x",
        booked_at=datetime(2026, 4, 1, tzinfo=timezone.utc), transaction_type="debit",
        counterparty_iban_ciphertext=encrypt_value(ctx["pocket_iban"]),
        counterparty_iban_hash=blind_index(ctx["pocket_iban"]),
        include_in_analytics=True,
    )
    db_session.add(src); db_session.commit()

    service = InternalTransferService(db_session, user_id=ctx["user"].id)
    assert service.detect_for_transactions([src.id]) == 1
    # Second call: no new mirrors
    assert service.detect_for_transactions([src.id]) == 0
    assert db_session.query(Transaction).filter_by(account_id=ctx["pocket"].id).count() == 1


def test_detect_skips_when_no_matching_pocket(db_session, user_with_synced_and_pocket):
    ctx = user_with_synced_and_pocket
    src = Transaction(
        user_id=ctx["user"].id, account_id=ctx["synced"].id, external_id="ext-3",
        amount=Decimal("-5.00"), currency="EUR", description="x",
        booked_at=datetime(2026, 4, 1, tzinfo=timezone.utc), transaction_type="debit",
        counterparty_iban_ciphertext=encrypt_value("NL99OTHER0000000000"),
        counterparty_iban_hash=blind_index("NL99OTHER0000000000"),
        include_in_analytics=True,
    )
    db_session.add(src); db_session.commit()

    service = InternalTransferService(db_session, user_id=ctx["user"].id)
    assert service.detect_for_transactions([src.id]) == 0
    db_session.refresh(src)
    assert src.include_in_analytics is True
    assert src.internal_transfer_id is None


def test_unlink_reverses_detection(db_session, user_with_synced_and_pocket):
    ctx = user_with_synced_and_pocket
    src = Transaction(
        user_id=ctx["user"].id, account_id=ctx["synced"].id, external_id="ext-4",
        amount=Decimal("-7.00"), currency="EUR", description="x",
        booked_at=datetime(2026, 4, 1, tzinfo=timezone.utc), transaction_type="debit",
        counterparty_iban_ciphertext=encrypt_value(ctx["pocket_iban"]),
        counterparty_iban_hash=blind_index(ctx["pocket_iban"]),
        include_in_analytics=True,
    )
    db_session.add(src); db_session.commit()

    service = InternalTransferService(db_session, user_id=ctx["user"].id)
    service.detect_for_transactions([src.id])
    it = db_session.query(InternalTransfer).one()

    service.unlink(it.id)
    db_session.commit()

    db_session.refresh(src)
    assert src.include_in_analytics is True
    assert src.internal_transfer_id is None
    assert db_session.query(InternalTransfer).count() == 0
    assert db_session.query(Transaction).filter_by(account_id=ctx["pocket"].id).count() == 0


def test_unlink_all_for_pocket_restores_sources(db_session, user_with_synced_and_pocket):
    ctx = user_with_synced_and_pocket
    src1 = Transaction(
        user_id=ctx["user"].id, account_id=ctx["synced"].id, external_id="ext-5",
        amount=Decimal("-1.00"), currency="EUR", description="a",
        booked_at=datetime(2026, 4, 1, tzinfo=timezone.utc), transaction_type="debit",
        counterparty_iban_ciphertext=encrypt_value(ctx["pocket_iban"]),
        counterparty_iban_hash=blind_index(ctx["pocket_iban"]),
        include_in_analytics=True,
    )
    src2 = Transaction(
        user_id=ctx["user"].id, account_id=ctx["synced"].id, external_id="ext-6",
        amount=Decimal("-2.00"), currency="EUR", description="b",
        booked_at=datetime(2026, 4, 2, tzinfo=timezone.utc), transaction_type="debit",
        counterparty_iban_ciphertext=encrypt_value(ctx["pocket_iban"]),
        counterparty_iban_hash=blind_index(ctx["pocket_iban"]),
        include_in_analytics=True,
    )
    db_session.add_all([src1, src2]); db_session.commit()

    service = InternalTransferService(db_session, user_id=ctx["user"].id)
    service.detect_for_transactions([src1.id, src2.id])
    assert service.unlink_all_for_pocket(ctx["pocket"].id) == 2

    db_session.refresh(src1); db_session.refresh(src2)
    assert src1.include_in_analytics is True and src1.internal_transfer_id is None
    assert src2.include_in_analytics is True and src2.internal_transfer_id is None
    assert db_session.query(InternalTransfer).count() == 0
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd backend && pytest tests/test_internal_transfer_service.py -v
```

Expected: FAIL with `ImportError` (service module doesn't exist).

- [ ] **Step 3: Implement the service**

Create `backend/app/services/internal_transfer_service.py`:

```python
"""Detect and manage internal transfers between the user's synced accounts
and their manually-registered pocket accounts.

Matching is done by counterparty IBAN blind index: transactions whose
counterparty_iban_hash matches a manual account's iban_hash are linked to
that pocket, and a mirror transaction is created on the pocket side.
"""
from __future__ import annotations

import logging
from decimal import Decimal
from typing import List
from uuid import UUID

from sqlalchemy.orm import Session

from app.models import Account, Category, InternalTransfer, Transaction

logger = logging.getLogger(__name__)


class InternalTransferService:
    def __init__(self, db: Session, user_id: str):
        self.db = db
        self.user_id = user_id

    def _load_pocket_map(self) -> dict[str, Account]:
        """Return {iban_hash: pocket_account} for this user's manual accounts with an IBAN."""
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

    def _resolve_transfer_category_id(self):
        cat = (
            self.db.query(Category)
            .filter(
                Category.user_id == self.user_id,
                Category.category_type == "transfer",
            )
            .order_by(Category.is_system.desc(), Category.created_at.asc())
            .first()
        )
        return cat.id if cat else None

    def detect_for_transactions(self, transaction_ids: List[UUID]) -> int:
        if not transaction_ids:
            return 0

        pocket_map = self._load_pocket_map()
        if not pocket_map:
            return 0

        sources = (
            self.db.query(Transaction)
            .filter(
                Transaction.id.in_(transaction_ids),
                Transaction.user_id == self.user_id,
                Transaction.counterparty_iban_hash.isnot(None),
                Transaction.internal_transfer_id.is_(None),
            )
            .all()
        )

        transfer_category_id = self._resolve_transfer_category_id()
        detected = 0

        for src in sources:
            pocket = pocket_map.get(src.counterparty_iban_hash)
            if pocket is None or pocket.id == src.account_id:
                continue

            mirror_amount = -src.amount
            mirror = Transaction(
                user_id=self.user_id,
                account_id=pocket.id,
                external_id=f"mirror-{src.id}",
                amount=mirror_amount,
                currency=src.currency,
                functional_amount=(-src.functional_amount) if src.functional_amount is not None else None,
                description=f"Transfer from {src.account.name}" if mirror_amount > 0 else f"Transfer to {src.account.name}",
                merchant=src.account.name,
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
            self.db.add(link)
            self.db.flush()

            src.include_in_analytics = False
            src.internal_transfer_id = link.id
            # Also label source with Transfer system category for consistency
            if transfer_category_id and src.category_id is None:
                src.category_system_id = transfer_category_id

            detected += 1

        if detected:
            self.db.commit()
        logger.info("[INTERNAL_TRANSFER] Detected %d transfer(s) for user %s", detected, self.user_id)
        return detected

    def unlink(self, internal_transfer_id: UUID) -> None:
        link = (
            self.db.query(InternalTransfer)
            .filter(
                InternalTransfer.id == internal_transfer_id,
                InternalTransfer.user_id == self.user_id,
            )
            .one_or_none()
        )
        if link is None:
            return

        src = self.db.query(Transaction).filter(Transaction.id == link.source_txn_id).one_or_none()
        if src is not None:
            src.include_in_analytics = True
            src.internal_transfer_id = None

        if link.mirror_txn_id is not None:
            mirror = self.db.query(Transaction).filter(Transaction.id == link.mirror_txn_id).one_or_none()
            if mirror is not None:
                self.db.delete(mirror)

        self.db.delete(link)
        self.db.commit()

    def unlink_all_for_pocket(self, pocket_account_id: UUID) -> int:
        links = (
            self.db.query(InternalTransfer)
            .filter(
                InternalTransfer.pocket_account_id == pocket_account_id,
                InternalTransfer.user_id == self.user_id,
            )
            .all()
        )
        count = 0
        for link in links:
            src = self.db.query(Transaction).filter(Transaction.id == link.source_txn_id).one_or_none()
            if src is not None:
                src.include_in_analytics = True
                src.internal_transfer_id = None
            # Mirror transactions will be removed by cascade when the pocket account is deleted
            self.db.delete(link)
            count += 1
        if count:
            self.db.commit()
        return count
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd backend && pytest tests/test_internal_transfer_service.py -v
```

Expected: all five tests PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/internal_transfer_service.py backend/tests/test_internal_transfer_service.py
git commit -m "feat(service): InternalTransferService — detect, unlink, unlink_all_for_pocket"
```

---

## Task 7: Wire detection into the post-import pipeline

**Files:**
- Modify: `backend/tasks/post_import_pipeline.py`
- Test: `backend/tests/test_post_import_pipeline.py`

- [ ] **Step 1: Write failing test**

Append to `backend/tests/test_post_import_pipeline.py`:

```python
def test_pipeline_runs_internal_transfer_detection_before_llm(db_session, monkeypatch):
    """Detection step must run between functional_amounts and batch LLM categorization."""
    from backend.tasks.post_import_pipeline import _run_pipeline
    from backend.app.models import Transaction, Account, InternalTransfer, Category
    from backend.app.security.data_encryption import encrypt_value, blind_index, reset_encryption_config_cache
    from tests.helpers import create_user
    from decimal import Decimal
    from datetime import datetime, timezone

    monkeypatch.setenv("DATA_ENCRYPTION_KEY_CURRENT", "0" * 64)
    reset_encryption_config_cache()

    user = create_user(db_session)
    pocket_iban = "NL91ABNA0417164300"
    synced = Account(
        user_id=user.id, name="Main", account_type="checking",
        provider="gocardless", currency="EUR", starting_balance=Decimal("0"),
    )
    pocket = Account(
        user_id=user.id, name="Pocket", account_type="savings",
        provider="manual", currency="EUR", starting_balance=Decimal("0"),
        iban_ciphertext=encrypt_value(pocket_iban),
        iban_hash=blind_index(pocket_iban),
    )
    cat = Category(user_id=user.id, name="Transfer", category_type="transfer", is_system=True)
    db_session.add_all([synced, pocket, cat]); db_session.commit()

    src = Transaction(
        user_id=user.id, account_id=synced.id, external_id="ext-pipe",
        amount=Decimal("-20.00"), currency="EUR", description="to pocket",
        booked_at=datetime(2026, 4, 1, tzinfo=timezone.utc), transaction_type="debit",
        counterparty_iban_ciphertext=encrypt_value(pocket_iban),
        counterparty_iban_hash=blind_index(pocket_iban),
    )
    db_session.add(src); db_session.commit()

    # Patch the LLM call to capture what it was given
    calls = {"llm_txn_ids": []}
    from backend.app.services.category_matcher import CategoryMatcher
    def fake_batch(self, inp):
        calls["llm_txn_ids"] = [d["index"] for d in inp]
        return {}, 0, 0.0
    monkeypatch.setattr(CategoryMatcher, "match_categories_batch_llm", fake_batch)

    _run_pipeline(db_session, user_id=user.id, transaction_ids=[src.id], account_ids=[synced.id, pocket.id])

    # Mirror was created
    mirror_count = db_session.query(Transaction).filter_by(account_id=pocket.id).count()
    assert mirror_count == 1
    # Link exists
    assert db_session.query(InternalTransfer).count() == 1
    # LLM did NOT see internal transfers (filtered out by include_in_analytics=False)
    assert len(calls["llm_txn_ids"]) == 0
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd backend && pytest tests/test_post_import_pipeline.py::test_pipeline_runs_internal_transfer_detection_before_llm -v
```

Expected: FAIL — pipeline currently doesn't invoke the service, and LLM sees all transactions.

- [ ] **Step 3: Add detection step + LLM filter**

In `backend/tasks/post_import_pipeline.py`:

First, update the module docstring to list 7 steps (was 6):

```python
"""
Shared post-import pipeline Celery task.

Runs 7 post-processing steps in order after any transaction import (CSV or Enable Banking):
  1. FX rate sync
  2. Functional amount calculation
  3. Internal transfer detection (create mirrors, flag both sides as non-analytics)
  4. Batch AI categorization (for transactions without a user-assigned category)
  5. Balance calculation
  6. Balance timeseries
  7. Subscription detection
"""
```

Add the import:

```python
from app.services.internal_transfer_service import InternalTransferService
```

Add the helper before `_batch_categorize_transactions`:

```python
def _detect_internal_transfers(db, user_id: str, transaction_ids: List[str]) -> int:
    service = InternalTransferService(db, user_id=user_id)
    return service.detect_for_transactions(transaction_ids)
```

Update `_batch_categorize_transactions`'s query to also filter out non-analytics transactions (mirrors and detected sources):

```python
    transactions = (
        db.query(Transaction)
        .filter(
            Transaction.id.in_(transaction_ids),
            Transaction.user_id == user_id,
            Transaction.category_id.is_(None),   # Preserve user-assigned categories
            Transaction.include_in_analytics.is_(True),  # Skip internal transfers
        )
        .all()
    )
```

Then inside the main pipeline function (search for where `_update_functional_amounts(...)` is called — that's step 2), insert the new step 3 call immediately after:

```python
    _update_functional_amounts(db, user_id, transaction_ids)

    # Step 3: Internal transfer detection (must run before LLM categorization)
    detected = _detect_internal_transfers(db, user_id, transaction_ids)
    logger.info("[POST_IMPORT_PIPELINE] Internal transfers detected: %d", detected)

    # Step 4: Batch AI categorization
    _batch_categorize_transactions(db, user_id, transaction_ids)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd backend && pytest tests/test_post_import_pipeline.py -v
```

Expected: new test PASSes; previously-passing tests still PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/tasks/post_import_pipeline.py backend/tests/test_post_import_pipeline.py
git commit -m "feat(pipeline): detect internal transfers before LLM categorization"
```

---

## Task 8: Backend endpoint — create pocket account with IBAN

**Files:**
- Modify: `backend/app/routes/accounts.py` (create the file if it does not yet exist; otherwise add a new router entry)
- Test: `backend/tests/test_pocket_account_routes.py` (new)

- [ ] **Step 1: Check whether `accounts.py` routes file exists**

```bash
ls backend/app/routes/ | grep -i account
```

If it exists, add the new endpoint to it. If not, create `backend/app/routes/accounts.py` and register the router in `backend/app/main.py` with `app.include_router(accounts_router, prefix="/api/accounts", tags=["accounts"])`.

- [ ] **Step 2: Write failing test**

Create `backend/tests/test_pocket_account_routes.py`:

```python
import pytest
from decimal import Decimal
from fastapi.testclient import TestClient
from datetime import datetime, timezone

from backend.app.main import app
from backend.app.models import Account, Transaction, InternalTransfer, Category
from backend.app.security.data_encryption import encrypt_value, blind_index, reset_encryption_config_cache
from tests.helpers import create_user, make_internal_auth_headers  # existing helper used in other EB tests


@pytest.fixture(autouse=True)
def _keys(monkeypatch):
    monkeypatch.setenv("DATA_ENCRYPTION_KEY_CURRENT", "0" * 64)
    reset_encryption_config_cache()
    yield
    reset_encryption_config_cache()


def test_create_pocket_account_encrypts_iban_and_backfills(db_session):
    user = create_user(db_session)
    # Pre-seed a synced account + one transaction with counterparty IBAN matching the to-be-registered pocket
    synced = Account(
        user_id=user.id, name="Main", account_type="checking",
        provider="gocardless", currency="EUR", starting_balance=Decimal("0"),
    )
    cat = Category(user_id=user.id, name="Transfer", category_type="transfer", is_system=True)
    db_session.add_all([synced, cat]); db_session.commit()

    iban = "NL91ABNA0417164300"
    src = Transaction(
        user_id=user.id, account_id=synced.id, external_id="ext-pre",
        amount=Decimal("-30.00"), currency="EUR", description="pre-existing",
        booked_at=datetime(2026, 4, 1, tzinfo=timezone.utc), transaction_type="debit",
        counterparty_iban_ciphertext=encrypt_value(iban),
        counterparty_iban_hash=blind_index(iban),
    )
    db_session.add(src); db_session.commit()

    client = TestClient(app)
    path = "/api/accounts/pocket"
    resp = client.post(
        path,
        json={
            "name": "My Pocket",
            "account_type": "savings",
            "currency": "EUR",
            "starting_balance": "0",
            "iban": iban,
        },
        headers=make_internal_auth_headers("POST", path, user.id),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["account_id"]
    assert body["backfilled_count"] == 1

    pocket = db_session.query(Account).filter_by(id=body["account_id"]).one()
    assert pocket.provider == "manual"
    assert pocket.iban_ciphertext.startswith("enc:v1:")
    assert pocket.iban_hash == blind_index(iban)

    # Backfill linked the pre-existing transaction
    db_session.refresh(src)
    assert src.include_in_analytics is False
    assert src.internal_transfer_id is not None
    assert db_session.query(InternalTransfer).count() == 1


def test_create_pocket_account_rejects_duplicate_iban(db_session):
    user = create_user(db_session)
    iban = "NL91ABNA0417164300"
    existing = Account(
        user_id=user.id, name="Existing", account_type="savings",
        provider="manual", currency="EUR", starting_balance=Decimal("0"),
        iban_ciphertext=encrypt_value(iban), iban_hash=blind_index(iban),
    )
    db_session.add(existing); db_session.commit()

    client = TestClient(app)
    path = "/api/accounts/pocket"
    resp = client.post(
        path,
        json={"name": "Dup", "account_type": "savings", "currency": "EUR", "starting_balance": "0", "iban": iban},
        headers=make_internal_auth_headers("POST", path, user.id),
    )
    assert resp.status_code == 400
    assert "already" in resp.json()["detail"].lower()


def test_create_pocket_account_rejects_invalid_iban(db_session):
    user = create_user(db_session)
    client = TestClient(app)
    path = "/api/accounts/pocket"
    resp = client.post(
        path,
        json={"name": "Bad", "account_type": "savings", "currency": "EUR", "starting_balance": "0", "iban": "not-an-iban"},
        headers=make_internal_auth_headers("POST", path, user.id),
    )
    assert resp.status_code == 400
```

- [ ] **Step 3: Run test to verify it fails**

```bash
cd backend && pytest tests/test_pocket_account_routes.py -v
```

Expected: FAIL — endpoint doesn't exist.

- [ ] **Step 4: Implement the endpoint**

Add to `backend/app/routes/accounts.py`:

```python
import re
from decimal import Decimal
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, field_validator
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_user_id   # existing internal-auth dependency
from app.models import Account, Transaction
from app.security.data_encryption import encrypt_value, blind_index
from app.services.internal_transfer_service import InternalTransferService

router = APIRouter()

_IBAN_RE = re.compile(r"^[A-Z]{2}\d{2}[A-Z0-9]{10,30}$")


class CreatePocketRequest(BaseModel):
    name: str
    account_type: str = "savings"
    currency: str = "EUR"
    starting_balance: Decimal = Decimal("0")
    iban: str

    @field_validator("iban")
    @classmethod
    def _normalize_iban(cls, v: str) -> str:
        norm = v.replace(" ", "").upper()
        if not (15 <= len(norm) <= 34) or not _IBAN_RE.match(norm):
            raise ValueError("Invalid IBAN format")
        return norm


class CreatePocketResponse(BaseModel):
    account_id: UUID
    backfilled_count: int


@router.post("/pocket", response_model=CreatePocketResponse)
def create_pocket_account(
    payload: CreatePocketRequest,
    user_id: str = Depends(get_user_id),
    db: Session = Depends(get_db),
):
    iban_hash = blind_index(payload.iban)
    if iban_hash is None:
        raise HTTPException(status_code=500, detail="Encryption not configured")

    existing = (
        db.query(Account)
        .filter(Account.user_id == user_id, Account.iban_hash == iban_hash)
        .first()
    )
    if existing is not None:
        raise HTTPException(status_code=400, detail="An account with this IBAN is already registered")

    account = Account(
        user_id=user_id,
        name=payload.name,
        account_type=payload.account_type,
        currency=payload.currency,
        provider="manual",
        starting_balance=payload.starting_balance,
        functional_balance=payload.starting_balance,
        iban_ciphertext=encrypt_value(payload.iban),
        iban_hash=iban_hash,
        is_active=True,
    )
    db.add(account)
    db.flush()

    # Backfill: find existing transactions whose counterparty matches this IBAN
    candidate_ids = [
        row[0]
        for row in db.query(Transaction.id)
        .filter(
            Transaction.user_id == user_id,
            Transaction.counterparty_iban_hash == iban_hash,
            Transaction.internal_transfer_id.is_(None),
        )
        .all()
    ]
    service = InternalTransferService(db, user_id=user_id)
    backfilled = service.detect_for_transactions(candidate_ids)
    db.commit()

    return CreatePocketResponse(account_id=account.id, backfilled_count=backfilled)
```

Also register the router — in `backend/app/main.py`, add:

```python
from app.routes import accounts as accounts_router
app.include_router(accounts_router.router, prefix="/api/accounts", tags=["accounts"])
```

(If a router is already defined, add the new endpoint to the existing one instead.)

- [ ] **Step 5: Run tests to verify they pass**

```bash
cd backend && pytest tests/test_pocket_account_routes.py -v
```

Expected: all three tests PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/routes/accounts.py backend/app/main.py backend/tests/test_pocket_account_routes.py
git commit -m "feat(api): POST /api/accounts/pocket — create pocket with IBAN + backfill"
```

---

## Task 9: Backend endpoint — unlink internal transfer

**Files:**
- Modify: `backend/app/routes/accounts.py`
- Test: `backend/tests/test_pocket_account_routes.py`

- [ ] **Step 1: Write failing test**

Append to `backend/tests/test_pocket_account_routes.py`:

```python
def test_unlink_internal_transfer_restores_source(db_session):
    user = create_user(db_session)
    iban = "NL91ABNA0417164300"
    synced = Account(user_id=user.id, name="Main", account_type="checking", provider="gocardless", currency="EUR", starting_balance=Decimal("0"))
    pocket = Account(
        user_id=user.id, name="Pocket", account_type="savings",
        provider="manual", currency="EUR", starting_balance=Decimal("0"),
        iban_ciphertext=encrypt_value(iban), iban_hash=blind_index(iban),
    )
    cat = Category(user_id=user.id, name="Transfer", category_type="transfer", is_system=True)
    db_session.add_all([synced, pocket, cat]); db_session.commit()

    src = Transaction(
        user_id=user.id, account_id=synced.id, external_id="ext-u",
        amount=Decimal("-9.00"), currency="EUR", description="x",
        booked_at=datetime(2026, 4, 1, tzinfo=timezone.utc), transaction_type="debit",
        counterparty_iban_ciphertext=encrypt_value(iban),
        counterparty_iban_hash=blind_index(iban),
    )
    db_session.add(src); db_session.commit()

    from backend.app.services.internal_transfer_service import InternalTransferService
    InternalTransferService(db_session, user_id=user.id).detect_for_transactions([src.id])
    link = db_session.query(InternalTransfer).one()

    client = TestClient(app)
    path = f"/api/accounts/internal-transfers/{link.id}"
    resp = client.delete(path, headers=make_internal_auth_headers("DELETE", path, user.id))
    assert resp.status_code == 204

    db_session.refresh(src)
    assert src.include_in_analytics is True
    assert db_session.query(InternalTransfer).count() == 0
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd backend && pytest tests/test_pocket_account_routes.py::test_unlink_internal_transfer_restores_source -v
```

Expected: FAIL (404 — endpoint missing).

- [ ] **Step 3: Implement the endpoint**

Add to `backend/app/routes/accounts.py`:

```python
from fastapi import status

@router.delete("/internal-transfers/{transfer_id}", status_code=status.HTTP_204_NO_CONTENT)
def unlink_internal_transfer(
    transfer_id: UUID,
    user_id: str = Depends(get_user_id),
    db: Session = Depends(get_db),
):
    service = InternalTransferService(db, user_id=user_id)
    service.unlink(transfer_id)
    return None
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd backend && pytest tests/test_pocket_account_routes.py -v
```

Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/routes/accounts.py backend/tests/test_pocket_account_routes.py
git commit -m "feat(api): DELETE /api/accounts/internal-transfers/:id — unlink detected transfer"
```

---

## Task 10: Backend endpoint — account delete cleans up internal transfers

**Files:**
- Modify: `backend/app/routes/accounts.py` (or wherever DELETE /api/accounts/:id lives today)
- Test: `backend/tests/test_pocket_account_routes.py`

- [ ] **Step 1: Locate the existing delete endpoint**

```bash
grep -rn "accounts/\{account_id\}" backend/app/routes/ || grep -rn "DELETE.*account" backend/app/routes/
```

If a DELETE endpoint already exists, modify it. If not, add one in `backend/app/routes/accounts.py`.

- [ ] **Step 2: Write failing test**

Append to `backend/tests/test_pocket_account_routes.py`:

```python
def test_delete_pocket_account_restores_linked_sources(db_session):
    user = create_user(db_session)
    iban = "NL91ABNA0417164300"
    synced = Account(user_id=user.id, name="Main", account_type="checking", provider="gocardless", currency="EUR", starting_balance=Decimal("0"))
    pocket = Account(
        user_id=user.id, name="Pocket", account_type="savings",
        provider="manual", currency="EUR", starting_balance=Decimal("0"),
        iban_ciphertext=encrypt_value(iban), iban_hash=blind_index(iban),
    )
    cat = Category(user_id=user.id, name="Transfer", category_type="transfer", is_system=True)
    db_session.add_all([synced, pocket, cat]); db_session.commit()

    src = Transaction(
        user_id=user.id, account_id=synced.id, external_id="ext-d",
        amount=Decimal("-4.00"), currency="EUR", description="x",
        booked_at=datetime(2026, 4, 1, tzinfo=timezone.utc), transaction_type="debit",
        counterparty_iban_ciphertext=encrypt_value(iban),
        counterparty_iban_hash=blind_index(iban),
    )
    db_session.add(src); db_session.commit()

    from backend.app.services.internal_transfer_service import InternalTransferService
    InternalTransferService(db_session, user_id=user.id).detect_for_transactions([src.id])
    pocket_id = pocket.id

    client = TestClient(app)
    path = f"/api/accounts/{pocket_id}"
    resp = client.delete(path, headers=make_internal_auth_headers("DELETE", path, user.id))
    assert resp.status_code == 204

    # Pocket gone
    assert db_session.query(Account).filter_by(id=pocket_id).count() == 0
    # Source restored
    db_session.refresh(src)
    assert src.include_in_analytics is True
    assert src.internal_transfer_id is None
    # Links gone
    assert db_session.query(InternalTransfer).count() == 0
```

- [ ] **Step 3: Run test to verify it fails**

```bash
cd backend && pytest tests/test_pocket_account_routes.py::test_delete_pocket_account_restores_linked_sources -v
```

Expected: depending on whether a delete endpoint exists, either FAIL (404) or PASS-but-not-restored.

- [ ] **Step 4: Implement / update the delete endpoint**

In `backend/app/routes/accounts.py`:

```python
@router.delete("/{account_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_account(
    account_id: UUID,
    user_id: str = Depends(get_user_id),
    db: Session = Depends(get_db),
):
    account = (
        db.query(Account)
        .filter(Account.id == account_id, Account.user_id == user_id)
        .one_or_none()
    )
    if account is None:
        raise HTTPException(status_code=404, detail="Account not found")

    # Pocket accounts may have linked internal transfers — restore the sources before cascade
    InternalTransferService(db, user_id=user_id).unlink_all_for_pocket(account_id)

    db.delete(account)
    db.commit()
    return None
```

If there is already a delete endpoint elsewhere (e.g. in the frontend server action using Drizzle), add the `unlink_all_for_pocket` call in that code path instead, before the delete runs.

- [ ] **Step 5: Run tests to verify they pass**

```bash
cd backend && pytest tests/test_pocket_account_routes.py -v
```

Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/routes/accounts.py backend/tests/test_pocket_account_routes.py
git commit -m "feat(api): DELETE /api/accounts/:id unlinks internal transfers before cascade"
```

---

## Task 11: Frontend server actions — pocket account + unlink

**Files:**
- Modify: `frontend/lib/actions/accounts.ts`

- [ ] **Step 1: Add the `createPocketAccount` action**

In `frontend/lib/actions/accounts.ts`, add at the bottom of the file:

```typescript
import { getBackendBaseUrl } from "@/lib/backend-url";
import { createInternalAuthHeaders } from "@/lib/internal-auth";
import { getAuthenticatedSession } from "@/lib/auth-helpers";
import { isDemoRestrictedUserEmail, DEMO_RESTRICTED_ACTION_ERROR } from "@/lib/demo-access";

export type CreatePocketAccountInput = {
  name: string;
  accountType?: string;           // defaults to "savings"
  currency?: string;              // defaults to "EUR"
  startingBalance?: number;
  iban: string;
};

export async function createPocketAccount(
  input: CreatePocketAccountInput,
): Promise<{ success: boolean; error?: string; accountId?: string; backfilledCount?: number }> {
  const session = await getAuthenticatedSession();
  const userId = session?.user?.id;
  if (!userId) return { success: false, error: "Not authenticated" };
  if (isDemoRestrictedUserEmail(session.user.email)) {
    return { success: false, error: DEMO_RESTRICTED_ACTION_ERROR };
  }

  try {
    const path = "/api/accounts/pocket";
    const url = `${getBackendBaseUrl().replace(/\/+$/, "")}${path}`;
    const headers = createInternalAuthHeaders({ method: "POST", pathWithQuery: path, userId });
    const resp = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json", ...headers },
      body: JSON.stringify({
        name: input.name,
        account_type: input.accountType ?? "savings",
        currency: input.currency ?? "EUR",
        starting_balance: String(input.startingBalance ?? 0),
        iban: input.iban,
      }),
    });
    if (!resp.ok) {
      const data = await resp.json().catch(() => ({ detail: "Failed to create pocket account" }));
      return { success: false, error: data.detail ?? "Failed to create pocket account" };
    }
    const data = await resp.json();
    revalidatePath("/settings");
    revalidatePath("/transactions/import");
    return { success: true, accountId: data.account_id, backfilledCount: data.backfilled_count };
  } catch {
    return { success: false, error: "Failed to create pocket account" };
  }
}

export async function unlinkInternalTransfer(
  transferId: string,
): Promise<{ success: boolean; error?: string }> {
  const session = await getAuthenticatedSession();
  const userId = session?.user?.id;
  if (!userId) return { success: false, error: "Not authenticated" };

  try {
    const path = `/api/accounts/internal-transfers/${transferId}`;
    const url = `${getBackendBaseUrl().replace(/\/+$/, "")}${path}`;
    const headers = createInternalAuthHeaders({ method: "DELETE", pathWithQuery: path, userId });
    const resp = await fetch(url, { method: "DELETE", headers });
    if (!resp.ok && resp.status !== 204) {
      return { success: false, error: "Failed to unlink" };
    }
    revalidatePath("/transactions");
    return { success: true };
  } catch {
    return { success: false, error: "Failed to unlink" };
  }
}
```

- [ ] **Step 2: Typecheck**

```bash
cd frontend && pnpm tsc --noEmit
```

Expected: no errors.

- [ ] **Step 3: Commit**

```bash
git add frontend/lib/actions/accounts.ts
git commit -m "feat(actions): createPocketAccount + unlinkInternalTransfer"
```

---

## Task 12: Frontend — IBAN input in AccountForm

**Files:**
- Modify: `frontend/components/accounts/account-form.tsx`

- [ ] **Step 1: Add IBAN state and validation regex**

Replace the body of `frontend/components/accounts/account-form.tsx` with this version (keeps existing behavior for regular accounts and adds an optional "Register as Pocket" toggle that reveals the IBAN field):

```typescript
"use client";

import { useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { CURRENCIES, ACCOUNT_TYPES } from "@/lib/constants";
import { createAccount, createPocketAccount } from "@/lib/actions/accounts";

const IBAN_RE = /^[A-Z]{2}\d{2}[A-Z0-9]{10,30}$/;

interface AccountFormProps {
  onSuccess?: () => void;
  onCancel?: () => void;
  submitLabel?: string;
  cancelLabel?: string;
  showCancel?: boolean;
  successMessage?: string;
}

export function AccountForm({
  onSuccess,
  onCancel,
  submitLabel = "Create Account",
  cancelLabel = "Cancel",
  showCancel = true,
  successMessage = "Account created successfully",
}: AccountFormProps) {
  const [isLoading, setIsLoading] = useState(false);

  const [name, setName] = useState("");
  const [accountType, setAccountType] = useState("");
  const [institution, setInstitution] = useState("");
  const [currency, setCurrency] = useState("EUR");
  const [initialBalance, setInitialBalance] = useState("");
  const [isPocket, setIsPocket] = useState(false);
  const [iban, setIban] = useState("");

  const resetForm = () => {
    setName("");
    setAccountType("");
    setInstitution("");
    setCurrency("EUR");
    setInitialBalance("");
    setIsPocket(false);
    setIban("");
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    if (!name.trim()) {
      toast.error("Please enter an account name");
      return;
    }
    if (!accountType) {
      toast.error("Please select an account type");
      return;
    }
    if (!currency) {
      toast.error("Please select a currency");
      return;
    }

    const normalizedIban = iban.replace(/\s+/g, "").toUpperCase();
    if (isPocket) {
      if (!normalizedIban) {
        toast.error("Please enter an IBAN for the pocket account");
        return;
      }
      if (!IBAN_RE.test(normalizedIban) || normalizedIban.length < 15 || normalizedIban.length > 34) {
        toast.error("Please enter a valid IBAN");
        return;
      }
    }

    setIsLoading(true);

    try {
      const balance = initialBalance ? parseFloat(initialBalance) : 0;
      if (initialBalance && isNaN(balance)) {
        toast.error("Please enter a valid initial balance");
        setIsLoading(false);
        return;
      }

      const result = isPocket
        ? await createPocketAccount({
            name: name.trim(),
            accountType,
            currency,
            startingBalance: balance,
            iban: normalizedIban,
          })
        : await createAccount({
            name: name.trim(),
            accountType,
            institution: institution.trim() || undefined,
            currency,
            startingBalance: balance,
          });

      if (result.success) {
        const message = isPocket && result.backfilledCount
          ? `${successMessage} — ${result.backfilledCount} existing transfer(s) linked`
          : successMessage;
        toast.success(message);
        resetForm();
        onSuccess?.();
      } else {
        toast.error(result.error || "Failed to create account");
      }
    } catch {
      toast.error("An error occurred. Please try again.");
    } finally {
      setIsLoading(false);
    }
  };

  const handleCancel = () => {
    resetForm();
    onCancel?.();
  };

  return (
    <form onSubmit={handleSubmit}>
      <div className="grid gap-4 py-4">
        <div className="space-y-2">
          <Label htmlFor="account-name">Account Name</Label>
          <Input
            id="account-name"
            placeholder="e.g., Main Checking"
            value={name}
            onChange={(e) => setName(e.target.value)}
          />
        </div>

        <div className="space-y-2">
          <Label htmlFor="account-type">Account Type</Label>
          <Select value={accountType} onValueChange={(v) => v && setAccountType(v)}>
            <SelectTrigger>
              <SelectValue placeholder="Select account type" />
            </SelectTrigger>
            <SelectContent>
              {ACCOUNT_TYPES.map((type) => (
                <SelectItem key={type.value} value={type.value}>
                  {type.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        {!isPocket && (
          <div className="space-y-2">
            <Label htmlFor="account-institution">Institution (optional)</Label>
            <Input
              id="account-institution"
              placeholder="e.g., Bank of America"
              value={institution}
              onChange={(e) => setInstitution(e.target.value)}
            />
          </div>
        )}

        <div className="space-y-2">
          <Label htmlFor="account-currency">Currency</Label>
          <Select value={currency} onValueChange={(v) => v && setCurrency(v)}>
            <SelectTrigger>
              <SelectValue placeholder="Select currency" />
            </SelectTrigger>
            <SelectContent>
              {CURRENCIES.map((curr) => (
                <SelectItem key={curr.code} value={curr.code}>
                  {curr.code} - {curr.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        <div className="space-y-2">
          <Label htmlFor="account-balance">Initial Balance (optional)</Label>
          <Input
            id="account-balance"
            type="number"
            step="0.01"
            placeholder="0.00"
            value={initialBalance}
            onChange={(e) => setInitialBalance(e.target.value)}
          />
        </div>

        <div className="flex items-center justify-between rounded border p-3">
          <div>
            <Label htmlFor="is-pocket" className="cursor-pointer">Register as pocket account</Label>
            <p className="text-xs text-muted-foreground">
              Tracks a savings pocket by IBAN. Transfers from your main account will be auto-detected.
            </p>
          </div>
          <Switch id="is-pocket" checked={isPocket} onCheckedChange={setIsPocket} />
        </div>

        {isPocket && (
          <div className="space-y-2">
            <Label htmlFor="account-iban">IBAN</Label>
            <Input
              id="account-iban"
              placeholder="NL91 ABNA 0417 1643 00"
              value={iban}
              onChange={(e) => setIban(e.target.value)}
              autoComplete="off"
              autoCapitalize="characters"
            />
          </div>
        )}
      </div>
      <div className="flex justify-end gap-2">
        {showCancel && (
          <Button type="button" variant="outline" onClick={handleCancel} disabled={isLoading}>
            {cancelLabel}
          </Button>
        )}
        <Button type="submit" disabled={isLoading}>
          {isLoading ? "Creating..." : submitLabel}
        </Button>
      </div>
    </form>
  );
}
```

- [ ] **Step 2: Verify the `Switch` component is available**

```bash
ls frontend/components/ui/switch.tsx
```

If missing, add it via shadcn MCP. Command:

```bash
cd frontend && pnpm dlx shadcn@latest add switch
```

- [ ] **Step 3: Typecheck and build**

```bash
cd frontend && pnpm tsc --noEmit
```

Expected: no errors.

- [ ] **Step 4: Commit**

```bash
git add frontend/components/accounts/account-form.tsx frontend/components/ui/switch.tsx
git commit -m "feat(ui): AccountForm — register-as-pocket toggle + IBAN input"
```

---

## Task 13: Frontend — internal transfer chip on transaction detail

**Files:**
- Find: the transaction detail component (likely `frontend/components/transactions/transaction-row-details.tsx` or similar)
- Modify: that component

- [ ] **Step 1: Locate the component**

```bash
grep -rln "transaction" frontend/components/transactions/ | head
```

Find the component that renders transaction detail (expanded row, side panel, or dialog). Note its path.

- [ ] **Step 2: Surface `internalTransferId` + pocket info in the query**

In the Drizzle query that fetches a single transaction (search in `frontend/lib/actions/transactions.ts` or equivalent), add a left join to `internal_transfers` and `accounts` so the result includes `internalTransferId`, `pocketAccountId`, `pocketAccountName`. Example snippet (adapt to existing query shape):

```typescript
import { internalTransfers, accounts as accountsTable } from "@/lib/db/schema";

// In the select:
const rows = await db
  .select({
    // ... existing fields ...
    internalTransferId: transactions.internalTransferId,
    pocketAccountName: accountsTable.name,
    pocketAccountId: accountsTable.id,
  })
  .from(transactions)
  .leftJoin(internalTransfers, eq(internalTransfers.id, transactions.internalTransferId))
  .leftJoin(accountsTable, eq(accountsTable.id, internalTransfers.pocketAccountId))
  .where(/* existing */);
```

- [ ] **Step 3: Render the chip**

In the transaction detail component, add near the top of the detail block:

```tsx
{transaction.internalTransferId && transaction.pocketAccountName && (
  <div className="flex items-center gap-2 rounded border bg-muted/40 p-2 text-xs">
    <RiExchangeLine className="h-4 w-4" />
    <span className="flex-1">
      Internal transfer — {transaction.pocketAccountName}
    </span>
    <button
      type="button"
      className="text-muted-foreground underline hover:text-foreground"
      onClick={async () => {
        const res = await unlinkInternalTransfer(transaction.internalTransferId!);
        if (res.success) {
          toast.success("Transfer unlinked");
        } else {
          toast.error(res.error ?? "Failed to unlink");
        }
      }}
    >
      Unlink
    </button>
  </div>
)}
```

Add imports at the top of the file:

```tsx
import { RiExchangeLine } from "@remixicon/react";
import { unlinkInternalTransfer } from "@/lib/actions/accounts";
import { toast } from "sonner";
```

- [ ] **Step 4: Typecheck**

```bash
cd frontend && pnpm tsc --noEmit
```

Expected: no errors.

- [ ] **Step 5: Commit**

```bash
git add frontend/components/transactions/ frontend/lib/actions/transactions.ts
git commit -m "feat(ui): internal-transfer chip + unlink button on transaction detail"
```

---

## Task 14: Frontend — "Pocket" badge on account card

**Files:**
- Find: the account list or account card component (likely `frontend/components/accounts/account-header.tsx` or a list page)
- Modify: that component

- [ ] **Step 1: Locate the component**

```bash
grep -rln "provider.*manual\|Manual\b" frontend/components/accounts/ | head
```

If there is already logic branching on `provider`, extend it. Otherwise, open `frontend/components/accounts/account-header.tsx` and the account list at `frontend/app/(dashboard)/settings/accounts/page.tsx` (or similar) and add the badge where account metadata is rendered.

- [ ] **Step 2: Add the badge**

Where the account's name/type is rendered, add:

```tsx
{account.provider === "manual" && account.ibanHash ? (
  <Badge variant="secondary">Pocket</Badge>
) : null}
```

The Drizzle query that loads the account must include `ibanHash` — check `frontend/lib/actions/accounts.ts` and add `ibanHash: accounts.ibanHash` to the select if missing.

- [ ] **Step 3: Typecheck**

```bash
cd frontend && pnpm tsc --noEmit
```

Expected: no errors.

- [ ] **Step 4: Visual check**

Run `cd frontend && pnpm dev`, create a pocket account via the form, and confirm:
- The "Pocket" badge appears on the account card
- Internal transfer chip appears on a transaction whose counterparty IBAN matches the pocket

- [ ] **Step 5: Commit**

```bash
git add frontend/components/accounts/ frontend/lib/actions/accounts.ts
git commit -m "feat(ui): Pocket badge on account header + include ibanHash in query"
```

---

## Task 15: Deploy

- [ ] **Step 1: Open PR**

```bash
gh pr create --title "feat: pocket account tracking (IBAN-based internal transfer detection)" --body "$(cat <<'EOF'
## Summary
- Adds manual "pocket" accounts registered by IBAN
- Enable Banking adapter extracts counterparty IBAN
- Post-import pipeline detects internal transfers, creates mirror transactions on pocket accounts, flags both sides as `include_in_analytics=false`
- Frontend: IBAN input, "Pocket" badge, internal-transfer chip with unlink action
- Spec: `docs/superpowers/specs/2026-04-19-pocket-accounts-design.md`

## Test plan
- [ ] Run `pytest backend/tests/ -v` — all green
- [ ] Create a pocket account with an IBAN that matches existing transactions → backfill creates mirrors
- [ ] Trigger a bank sync → new transfers auto-linked
- [ ] Unlink a mistaken match via the chip → source restored to analytics
- [ ] Delete the pocket account → all sources restored

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

- [ ] **Step 2: Merge the PR and redeploy Railway services**

After merge:

```bash
RAILWAY_ENVIRONMENT=production railway redeploy --service backend --yes
RAILWAY_ENVIRONMENT=production railway redeploy --service worker --yes
```

(Frontend redeploy is automatic via Railway's GitHub integration.)

- [ ] **Step 3: Post-deploy smoke check**

On the deployed app:
1. Go to Settings → Accounts → Add Account
2. Toggle "Register as pocket account"
3. Enter an IBAN matching one of your existing counterparties
4. Submit → verify backfill count in the success toast
5. Open a linked transaction → confirm chip appears

---

## Completion criteria

- All 15 tasks checked off
- All tests passing: `cd backend && pytest tests/ -v` and `cd frontend && pnpm tsc --noEmit`
- PR merged and deployed
- Manual smoke check passed
