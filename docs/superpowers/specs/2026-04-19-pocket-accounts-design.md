# IBAN-Based Pocket Account Tracking

**Date:** 2026-04-19
**Status:** Approved

## Background

Some savings accounts (notably ABN AMRO "pockets") cannot be synced via Open Banking. However, every transfer between the user's main synced account and a pocket shows up in the main account's transaction feed, complete with a counterparty IBAN.

This feature lets users manually register a pocket account by IBAN, and then the system:
1. Auto-detects transfers between the synced parent and the pocket by matching counterparty IBAN
2. Creates a mirror transaction on the pocket account so its balance derives naturally
3. Flags both sides as `include_in_analytics = false` so transfers don't pollute spending/income analytics

---

## Goals

1. Extract counterparty IBAN from Enable Banking transactions during sync
2. Let users register pocket accounts (manual provider) with a canonical IBAN + starting balance
3. Auto-detect and link internal transfers by matching `counterparty_iban_hash`
4. Derive pocket balances from mirror transactions (consistent with the existing `starting_balance + sum(transactions)` model)
5. Exclude detected transfers from analytics on both sides
6. Let users unlink a mistaken match, reverting `include_in_analytics` and deleting the mirror

## Non-Goals

- Pockets that share an IBAN with the synced parent (ABN pockets have distinct IBANs)
- Detecting transfers between two synced user-owned accounts (separate concern — can reuse the same machinery later)
- IBAN validation beyond basic format (country code + length); full mod-97 is YAGNI
- Predictive/fuzzy counterparty matching — the whole point is IBAN is an explicit identifier

---

## Approach

Add IBAN fields to `accounts` and `transactions`. Add a new `internal_transfers` table that links the source transaction (on the synced account) to its mirror transaction (on the pocket account). Detection runs as a new step in the post-import pipeline, and a backfill runs on pocket account creation.

No new service abstraction for counterparty extraction — the Enable Banking adapter gains a few lines to extract IBAN from the nested `creditor`/`debtor` objects it already parses.

---

## Changes

### 1. Add IBAN fields to `accounts`

**Files:** `frontend/lib/db/schema.ts`, `backend/app/models.py`, migration

Two new nullable columns on `accounts`:
- `iban_ciphertext` (text) — AES-encrypted IBAN, using the existing `data_encryption` util
- `iban_hash` (varchar 64) — HMAC-SHA256 blind index for lookup without decrypting

No partial unique constraint — users can legitimately share an IBAN across households (e.g., spouse's pocket), and the lookup is always scoped by `user_id`. A composite index `(user_id, iban_hash)` is added instead.

### 2. Add counterparty IBAN fields to `transactions`

**Files:** `frontend/lib/db/schema.ts`, `backend/app/models.py`, migration

Three new nullable columns on `transactions`:
- `counterparty_iban_ciphertext` (text) — encrypted raw IBAN
- `counterparty_iban_hash` (varchar 64) — blind index for matching
- `internal_transfer_id` (uuid, FK to `internal_transfers.id`, `ON DELETE SET NULL`)

Index: `(user_id, counterparty_iban_hash)` for the detection query.

### 3. Add `internal_transfers` table

**Files:** `frontend/lib/db/schema.ts`, `backend/app/models.py`, migration

```sql
CREATE TABLE internal_transfers (
  id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id          TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  source_txn_id    UUID NOT NULL UNIQUE REFERENCES transactions(id) ON DELETE CASCADE,
  mirror_txn_id    UUID UNIQUE REFERENCES transactions(id) ON DELETE SET NULL,
  source_account_id UUID NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
  pocket_account_id UUID NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
  amount           DECIMAL(15,2) NOT NULL,
  currency         CHAR(3) NOT NULL,
  detected_at      TIMESTAMP DEFAULT NOW(),
  created_at       TIMESTAMP DEFAULT NOW()
);
CREATE INDEX idx_internal_transfers_user ON internal_transfers(user_id);
CREATE INDEX idx_internal_transfers_pocket ON internal_transfers(pocket_account_id);
```

`source_txn_id` is unique — a transaction can only be part of one internal transfer. `mirror_txn_id` is nullable to allow "detected but not yet mirrored" states (and simplifies unlink → we can null it out then delete the mirror).

### 4. Extract counterparty IBAN in the Enable Banking adapter

**File:** `backend/app/integrations/enable_banking_adapter.py` — `normalize_transaction()`

Enable Banking returns counterparty account objects as `creditor_account` / `debtor_account` (or nested under `creditor` / `debtor`), typically shaped like `{"iban": "NL91ABNA0417164300"}` or `{"identification": "...", "scheme_name": "IBAN"}`.

**Logic** (appended to existing creditor/debtor name extraction):

```python
def _extract_iban(account_obj):
    if not isinstance(account_obj, dict):
        return None
    # Most common field
    iban = account_obj.get("iban")
    if iban:
        return iban.replace(" ", "").upper()
    # Fallback: scheme_name + identification
    if account_obj.get("scheme_name", "").upper() == "IBAN":
        ident = account_obj.get("identification")
        if ident:
            return ident.replace(" ", "").upper()
    return None

creditor_iban = _extract_iban(raw.get("creditor_account")) or _extract_iban(raw.get("creditor"))
debtor_iban   = _extract_iban(raw.get("debtor_account"))   or _extract_iban(raw.get("debtor"))

# Counterparty depends on direction: for outflows (DBIT), counterparty is creditor; for inflows, debtor
counterparty_iban = creditor_iban if credit_debit == "DBIT" else debtor_iban
```

Two new fields on `TransactionData` (the adapter DTO): `counterparty_iban: str | None`. Hashing happens at persist time in the sync service (where the encryption keys live), not in the adapter.

### 5. Persist counterparty IBAN during sync

**File:** `backend/app/services/sync_service.py` (or wherever `TransactionData` → `Transaction` mapping lives)

On insert/update of a transaction, if `TransactionData.counterparty_iban` is set:
- `transaction.counterparty_iban_ciphertext = encrypt(iban)`
- `transaction.counterparty_iban_hash = blind_index(iban)`

Uses the existing `encrypt()` / `blind_index()` helpers from `backend/app/security/data_encryption.py`.

### 6. Internal transfer detection service

**File:** `backend/app/services/internal_transfer_service.py` (new)

One class, `InternalTransferService`, with two public methods:

```python
class InternalTransferService:
    def __init__(self, db: Session, user_id: str): ...

    def detect_for_transactions(self, transaction_ids: list[UUID]) -> int:
        """
        For each transaction in the list that has a counterparty_iban_hash,
        check if it matches a manual account's iban_hash. If so, create the
        internal_transfer + mirror transaction and mark both include_in_analytics=False.
        Returns number of transfers detected.
        Idempotent: skips transactions that already have internal_transfer_id set.
        """

    def unlink(self, internal_transfer_id: UUID) -> None:
        """
        Delete the mirror transaction, clear internal_transfer_id on the source,
        set include_in_analytics=True on the source, delete the internal_transfers row.
        """

    def unlink_all_for_pocket(self, pocket_account_id: UUID) -> int:
        """
        Called by the delete-account endpoint before cascading delete.
        Restores include_in_analytics=True on all source transactions linked to
        this pocket; deletes internal_transfers rows. Mirror transactions are
        left to the cascade. Returns count unlinked.
        """
```

**Detection logic:**

1. Load source transactions where `id IN (:ids) AND counterparty_iban_hash IS NOT NULL AND internal_transfer_id IS NULL`
2. Build a dict of the user's manual account IBAN hashes: `{iban_hash: account}` for `user_id == self.user_id AND provider == 'manual' AND iban_hash IS NOT NULL`
3. For each source transaction where `counterparty_iban_hash in manual_accounts`:
   - Skip if source account == matched pocket (shouldn't happen but defensive)
   - Create a mirror `Transaction`:
     - `account_id` = pocket's id
     - `amount` = `-source.amount` (sign flipped)
     - `currency` = `source.currency`
     - `booked_at` = `source.booked_at`
     - `description` = `f"Transfer from/to {source_account.name}"`
     - `merchant` = `source_account.name`
     - `external_id` = `f"mirror-{source.id}"` (avoids dedup collision, scopes to this account)
     - `category_system_id` = the user's "Transfer" category (resolved once per detection batch); `category_id` left NULL so the user can still override
     - `include_in_analytics` = `False`
     - `transaction_type` = `"credit"` if new amount > 0 else `"debit"`
     - Pass the source account's IBAN as the mirror's `counterparty_iban` (if the synced account has one stored, otherwise leave null)
   - Create `InternalTransfer` row linking source + mirror
   - Update source: `include_in_analytics = False`, `internal_transfer_id = <new row id>`
4. Return count

### 7. Wire detection into the post-import pipeline

**File:** `backend/tasks/post_import_pipeline.py`

Add a new step between "functional amounts" and "batch AI categorization":

```python
# Step 2.5: Internal transfer detection
transfer_service = InternalTransferService(db, user_id=user_id)
detected = transfer_service.detect_for_transactions(touched_transaction_ids)
logger.info("[PIPELINE] Internal transfers detected: %s", detected)
```

Must run **after** functional amounts (so mirrors inherit correct FX-converted values) and **before** batch AI categorization. Full order: fx rates → functional amounts → **internal transfer detection** → batch LLM categorization → balance calculation → balance timeseries → subscription detection.

**Mirror functional amount**: computed at insert time by reusing the same `compute_functional_amount()` helper the pipeline step uses for new transactions.

**LLM skip**: the batch categorization step must filter out transactions where `include_in_analytics = False` (which now includes all mirrors and detected source transactions). If that filter is not already present in `CategoryMatcher`, it is added as part of this work.

### 8. Backfill on pocket account creation

**Files:** `backend/app/routes/accounts.py` (or the existing create/update account endpoint)

When a user creates a manual account with an IBAN, or updates an existing manual account to add/change an IBAN:

1. Compute `iban_hash` and persist to the account
2. Fetch all transactions for the user where `counterparty_iban_hash == iban_hash` AND `internal_transfer_id IS NULL`
3. Call `InternalTransferService.detect_for_transactions(those_ids)`
4. Recalculate balance timeseries for the pocket account and the source accounts involved (reuse existing `recalculate_balance_timeseries` task)

This is a synchronous operation wrapped in a single DB transaction. Expected volume is low (≤ a few hundred transactions per pocket).

### 9. Frontend: account form with IBAN input

**File:** `frontend/components/accounts/account-form.tsx`

Add an optional `iban` text input, only shown when the form is creating/editing a manual account. Client-side validation:
- Trimmed, uppercased
- Matches `/^[A-Z]{2}\d{2}[A-Z0-9]{10,30}$/` (2 letter country code + 2 check digits + 10-30 alphanumeric)
- Length 15-34 characters

Server action accepts `iban`, passes through to the backend.

### 10. Frontend: server action + backend update

**File:** `frontend/lib/actions/accounts.ts`

Existing `createAccount` / `updateAccount` actions gain an `iban?: string` field. When present, the action posts it to the backend, which handles encryption + hashing + backfill.

### 11. Frontend: internal transfer chip on transaction detail

**Files:** Transaction detail component (locate during implementation)

When a transaction has `internal_transfer_id`:
- Show a subtle chip: "Internal transfer — {pocket account name}"
- Clicking the chip navigates to the pocket account
- An "Unlink" button (in the chip's context menu) calls a new server action `unlinkInternalTransfer(transferId)` → backend deletes mirror + clears flags

### 12. Frontend: pocket account indicators

**File:** Account list / card component

- Accounts with `provider == "manual"` AND `iban IS NOT NULL` get a "Pocket" badge
- Balance displays normally (derived from `starting_balance + sum(transactions)`, which now includes mirror transactions)

---

## Data Flow

### New transaction arrives via sync

```
EB adapter normalizes txn
  → TransactionData.counterparty_iban = "NL91..."
  → SyncService persists txn with encrypted iban + iban_hash
  → post_import_pipeline runs
      → functional amounts
      → InternalTransferService.detect_for_transactions([new_txn_ids])
          → matches counterparty_iban_hash against user's manual accounts
          → match found → creates mirror txn + internal_transfers row
          → source.include_in_analytics = False
      → batch LLM categorization (skips transactions already in Transfer category)
      → balance timeseries recalc (pocket's balance now reflects mirror)
```

### User creates a pocket account with IBAN

```
POST /accounts {name, type: "savings", provider: "manual", iban, startingBalance}
  → backend validates IBAN format
  → encrypts IBAN, computes blind_index
  → inserts account
  → queries transactions where counterparty_iban_hash matches → N results
  → InternalTransferService.detect_for_transactions([N ids])
  → recalculates balance timeseries
  → returns account with derived balance
```

### User unlinks a mistaken match

```
Click "Unlink" on transaction detail
  → unlinkInternalTransfer(transferId) server action
  → backend InternalTransferService.unlink(transferId)
      → delete mirror transaction
      → source: include_in_analytics=True, internal_transfer_id=NULL
      → delete internal_transfers row
  → balance timeseries recalc for affected accounts
```

---

## What Does Not Change

- Existing balance computation (`starting_balance + sum(transactions)`) — mirrors are just transactions ✅
- Existing FX conversion / functional amount pipeline — mirrors use the same helpers ✅
- Existing dedup via `(account_id, external_id)` unique constraint — mirrors use `mirror-{source_id}` as external_id, scoped to pocket account ✅
- LLM categorization — mirrors arrive pre-categorized as Transfer, skipped ✅
- Analytics queries — they already filter on `include_in_analytics = True` ✅

---

## Error Handling

- **Duplicate detection**: `internal_transfer_id IS NULL` check makes detection idempotent — re-running the pipeline is a no-op for already-linked transactions.
- **Cross-currency transfer**: mirror uses the same raw currency as the source. Balance timeseries + functional_amount handle FX conversion as usual.
- **Pocket account deletion**: the delete-account endpoint must, before performing the delete, call `InternalTransferService.unlink_all_for_pocket(pocket_account_id)` which:
  1. Loads every `internal_transfers` row where `pocket_account_id = target`
  2. For each: sets source `include_in_analytics = True`, clears `internal_transfer_id`
  3. Deletes the `internal_transfers` rows (mirror transactions are deleted by cascade when the pocket account is deleted)
  Only after that does the account delete proceed. This keeps analytics consistent without relying on post-hoc cleanup.
- **IBAN collision** (two pocket accounts with the same IBAN): disallowed at app level — reject on create with 400 "IBAN already registered for another account."

---

## Testing

- Unit: `InternalTransferService.detect_for_transactions` matches, creates mirror, flips analytics flag
- Unit: `InternalTransferService.unlink` reverses the above
- Unit: EB adapter extracts IBAN from both `creditor_account.iban` and nested `creditor.iban` shapes
- Integration: full sync → pipeline → pocket with pre-existing IBAN → mirror created, balance correct
- Integration: create pocket account with existing matching transactions → backfill runs → mirrors created
- Integration: delete pocket account → source transactions restored to `include_in_analytics=True`

---

## Files Affected

| File | Change |
|------|--------|
| `frontend/lib/db/schema.ts` | Add iban fields to accounts; counterparty_iban fields to transactions; new internal_transfers table |
| `backend/app/models.py` | Mirror above |
| `frontend/lib/db/migrations/` | One migration for all three schema changes |
| `backend/app/integrations/enable_banking_adapter.py` | Extract counterparty IBAN |
| `backend/app/services/sync_service.py` | Persist encrypted IBAN + hash when inserting transactions |
| `backend/app/services/internal_transfer_service.py` | NEW — detect + unlink |
| `backend/tasks/post_import_pipeline.py` | Wire detection step |
| `backend/app/routes/accounts.py` | Accept IBAN; trigger backfill on create/update |
| `frontend/components/accounts/account-form.tsx` | IBAN input, validation |
| `frontend/lib/actions/accounts.ts` | Pass IBAN through; new `unlinkInternalTransfer` action |
| Transaction detail component | Internal transfer chip + unlink button |
| Account list / card component | "Pocket" badge |
