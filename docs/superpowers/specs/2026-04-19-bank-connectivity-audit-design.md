# Bank Connectivity Audit & Fixes

**Date:** 2026-04-19
**Status:** Approved

## Background

A full audit of the Enable Banking integration identified five gaps. This spec covers the fixes. The categorization pipeline was audited and confirmed correct — no changes required there.

### Audit Findings Summary

| Area | Finding |
|------|---------|
| Disconnect | ✅ Correct — accounts and transactions are preserved, only unlinked |
| Fix Categories | ✅ Correct — respects user overrides, rewrites system categories |
| Categorization pipeline | ✅ Correct — LLM intentionally batched post-sync, no double-spending |
| Sync idempotency | ❌ No guard — rapid re-triggers spawn concurrent syncs |
| Account addition | ❌ No flow — user must fully disconnect + re-auth to add a new account |
| Re-auth wizard | ❌ No pre-matching — previously-linked accounts are not auto-detected |
| Per-account sync range | ❌ All accounts use the same window — re-linked accounts re-fetch full history |

---

## Approach: Enhanced Re-Auth (Approach A)

Re-auth continues to create a new `BankConnection` row. The existing flow is enhanced in three ways:
1. `external_id` is preserved on disconnect so re-auth can auto-match accounts
2. The map-accounts wizard is pre-populated with suggested mappings
3. Sync start date is computed per-account, not per-connection

No new tables. One new nullable column. One new GET endpoint. One frontend wizard change.

---

## Changes

### 1. Preserve `external_id` on Disconnect

**File:** `backend/app/routes/enable_banking.py` — DELETE `/{connection_id}`

**Current behaviour:** disconnect clears `external_id`, `external_id_ciphertext`, `external_id_hash`, `provider`, and `bank_connection_id` from all linked accounts.

**New behaviour:** only clear `bank_connection_id` and `provider`. Preserve `external_id`, `external_id_ciphertext`, and `external_id_hash`.

**Rationale:** `external_id` is the bank's stable UID for an account — identifying information, not session-sensitive. Keeping it enables auto-matching during re-auth. The unique constraint on `(userId, provider, externalIdHash)` remains safe because `provider` is cleared to `NULL`, so the constraint cannot conflict.

---

### 2. Sync Idempotency Guard

**File:** `backend/tasks/enable_banking_tasks.py` — `sync_bank_connection` task

**New column:** `sync_started_at` (nullable timestamp) on `bank_connections`. Set at the start of every sync attempt; cleared on completion or failure.

**Schema change:** one column added to `bank_connections` in both Drizzle schema (`frontend/lib/db/schema.ts`) and SQLAlchemy model (`backend/app/models.py`). One migration generated.

**Guard logic** (checked at the top of the task, before any API calls):

```python
SYNC_COOLDOWN_SECONDS = 300       # 5 min since last completed sync
SYNC_IN_PROGRESS_TIMEOUT = 600    # 10 min since sync started (covers largest 730-day load)

now = datetime.now(timezone.utc)

if connection.last_synced_at and (now - connection.last_synced_at).total_seconds() < SYNC_COOLDOWN_SECONDS:
    logger.info("[SYNC] Skipped: completed sync too recent (%s)", connection.last_synced_at)
    return

if connection.sync_started_at and (now - connection.sync_started_at).total_seconds() < SYNC_IN_PROGRESS_TIMEOUT:
    logger.info("[SYNC] Skipped: sync already in progress since %s", connection.sync_started_at)
    return

# Set sync_started_at before first API call
connection.sync_started_at = now
db.commit()
```

`sync_started_at` is cleared (set to `NULL`) in the task's `finally` block.

**Initial sync edge case:** `last_synced_at` is `NULL` on first sync — guard never fires. ✅

---

### 3. Per-Account Sync Start Date

**File:** `backend/tasks/enable_banking_tasks.py` — `sync_bank_connection` task

**Current behaviour:** a single `start_date` is computed for the whole connection before the account loop.

**New behaviour:** `start_date` is computed inside the account loop, per-account:

```python
for account in accounts:
    if account.last_synced_at is not None:
        start_date = (account.last_synced_at - timedelta(days=1)).date()
    else:
        start_date = (now - timedelta(days=connection.initial_sync_days)).date()
```

**Effect:**
- Previously-synced re-linked accounts → incremental sync from `last_synced_at - 1 day` ✅
- New accounts (never synced) → full lookback using `initial_sync_days` ✅
- `external_id` dedup constraint remains a safety net regardless ✅

`account.last_synced_at` is already set per-account at the end of each sync and is preserved through disconnect — no schema change needed.

---

### 4. Suggested Mappings Endpoint

**File:** `backend/app/routes/enable_banking.py`

**New endpoint:** `GET /connections/{connection_id}/suggested-mappings`

Requires `connection.status == "pending_setup"` (raw session data must still be present).

**Logic:**
1. For each bank account UID in `connection.raw_session_data["accounts"]`, compute its blind index (`blind_index(uid)`)
2. Look up whether the user has an existing account with that `external_id_hash`
3. If found → suggest `action: "link"` with `suggested_account_id` and `suggested_account_name`
4. If not found → suggest `action: "create"`

**Response schema:**
```json
[
  {
    "bank_uid": "abc123",
    "bank_name": "ABN AMRO Savings",
    "suggested_action": "link",
    "suggested_account_id": "uuid",
    "suggested_account_name": "My ABN Savings"
  },
  {
    "bank_uid": "def456",
    "bank_name": "New Current Account",
    "suggested_action": "create",
    "suggested_account_id": null,
    "suggested_account_name": null
  }
]
```

**Auth:** same internal auth signature as all other EB endpoints (`get_user_id` dependency).

---

### 5. Map-Accounts Wizard Pre-Population

**File:** `frontend/app/(dashboard)/settings/connect-bank/map-accounts/page.tsx` and related components

**Current behaviour:** wizard treats every bank account as unmapped; user manually selects action and target for each.

**New behaviour:**
1. On mount, call `GET /connections/{connection_id}/suggested-mappings` via a new server action `getSuggestedMappings(connectionId)`
2. Pre-populate each bank account row with the suggested action and account
3. Rows with `suggested_action: "link"` are pre-filled and visually indicated as "previously linked" — still fully editable (user can override to "create new" if desired)
4. Rows with `suggested_action: "create"` behave exactly as today

**Validation relaxation (backend):** the existing check `if existing.bank_connection_id is not None → reject` already passes for previously-disconnected accounts (their `bank_connection_id` is `NULL`). No change needed. ✅

**Error prevention:** if a user somehow tries to create a new account with a bank UID that already matches an existing account's `external_id_hash`, the backend returns a 400 with a clear message: "An account with this bank UID already exists — use 'link to existing' instead."

---

### 6. Categorization Pipeline Documentation

**File:** `backend/tasks/enable_banking_tasks.py`

Add an inline comment explaining why `use_llm_categorization=False` is set on `SyncService`:

```python
# LLM categorization is intentionally disabled here.
# Inline per-transaction LLM calls during sync waste tokens and slow the import.
# The post_import_pipeline (step 3) runs a single batch LLM pass over all
# touched transactions after sync completes — more efficient and equally accurate.
sync_service = SyncService(db, user_id=connection.user_id, use_llm_categorization=False)
```

---

## Data Flow: Re-Auth with Existing Accounts

```
User clicks "Connect Bank" (same bank as before)
  → POST /auth → OAuth redirect
  → POST /session → new BankConnection (pending_setup)
  → GET /suggested-mappings
      → for each bank UID, blind_index lookup against user's accounts
      → returns pre-suggested link/create per account
  → Wizard renders pre-populated mappings
      → previously-linked accounts: pre-filled as "link to existing"
      → new accounts: "create new"
  → User confirms → POST /map-accounts
      → re-links accounts (bank_connection_id is NULL so validation passes)
      → new accounts created normally
      → connection status → active
  → sync_bank_connection triggered
      → is_initial_sync = True (new connection row, last_synced_at is NULL)
          → only affects subscription detection scope (scans all user transactions)
          → does NOT affect sync date range — that is handled per-account (see below)
      → idempotency guard checked
      → per-account start_date computed
          → re-linked: last_synced_at - 1 day
          → new: now - initial_sync_days
      → sync proceeds, no duplicates (external_id dedup)
  → post_import_pipeline runs
```

---

## What Does Not Change

- Disconnect preserving accounts and transactions — already correct ✅
- "Fix Categories" endpoint — already correct ✅
- Categorization precedence: `category_id` (user) → `category_system_id` (LLM) ✅
- Post-import pipeline steps and ordering ✅
- Frontend bank connections manager UI (other than wizard pre-population) ✅

---

## Files Affected

| File | Change |
|------|--------|
| `backend/app/routes/enable_banking.py` | Disconnect: stop clearing external_id fields; new suggested-mappings endpoint |
| `backend/tasks/enable_banking_tasks.py` | Idempotency guard; per-account sync start date; comment on LLM flag |
| `backend/app/models.py` | Add `sync_started_at` column |
| `frontend/lib/db/schema.ts` | Add `syncStartedAt` column to bankConnections |
| `frontend/lib/db/migrations/` | Migration for new column |
| `frontend/lib/actions/bank-connections.ts` | New `getSuggestedMappings` server action |
| `frontend/app/(dashboard)/settings/connect-bank/map-accounts/` | Pre-populate wizard from suggestions |
