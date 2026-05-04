# Recognize-Own-IBANs Internal Transfer Detection

**Date:** 2026-04-25
**Status:** Approved

## Background

PR #72 added pocket-account internal-transfer detection: a manual account registered with an IBAN gets mirror transactions auto-created whenever a synced account's transaction has a `counterparty_iban_hash` matching that pocket. This works for the user's manual `ABN Long Term Savings` pocket — once a sync runs and the EB adapter actually populates `creditor_account.iban`.

But the system has no general notion of "this IBAN belongs to me." Synced (`provider='enable_banking'`) accounts never have their own `iban_hash` populated, even though the EB session response always includes each account's IBAN. As a result:

1. A transfer between two of the user's synced accounts (e.g. `ABN AMRO Giannis` checking → `Revo Pocket` synced savings) is **not** recognized as internal — both sides get LLM-categorized as if external.
2. Detection logic is one-sided. It only fires when the destination is a manual pocket. The system can never answer the basic question: "is this counterparty one of my own accounts?"

## Goals

1. **Recognize own IBANs.** Persist `iban_hash` and `iban_ciphertext` on every account that has an IBAN — synced or manual. Achieved by writing IBAN during EB sync, in addition to the existing manual-account registration flow from PR #72.
2. **Generalize internal-transfer detection.** Match a transaction's `counterparty_iban_hash` against *any* user account's `iban_hash`, not just manual ones. Both sides of an own-IBAN transfer are tagged as `Transfer` and excluded from analytics.
3. **Preserve PR #72's manual-pocket balance update.** When the destination is a manual account (no EB sync), still create a mirror transaction so its balance reflects the detected transfer.
4. **Avoid double-counting on synced destinations.** When the destination is a synced account, do NOT create a mirror — EB delivers the destination side's transaction independently, and our detection will correctly tag that side too.
5. **Manual reconciliation already works.** The existing `UpdateBalanceDialog` + `createOrUpdateBalancingTransaction` flow is generic across providers — no UI change needed.

## Non-Goals

- Heuristic transfer detection (matching opposite-sign amounts on the same date across accounts). YAGNI — we have IBANs.
- Automatic balance-from-transfers-only override that ignores other transactions on a savings account. The user explicitly scoped this to manual savings, where the only transactions ARE the mirrors anyway.
- Periodic reminder/notification jobs. Manual reconciliation is on-demand via the existing UI.
- Updating manual-account IBAN after creation (out of scope per PR #72's spec — delete + recreate).

---

## Architecture

Three small changes:

### 1. Sync persists synced-account IBAN

`backend/app/integrations/base.py`: add `iban: Optional[str] = None` to `AccountData`.

`backend/app/integrations/enable_banking_adapter.py` (`fetch_accounts`): populate `iban` from `acc.get("iban")`. The session-data response from EB already includes this field per account (it's used today only as a fallback for the display name on line 79).

`backend/app/services/sync_service.py` (account upsert path): when an `AccountData` has `iban` populated and the corresponding `Account` row's `iban_hash` is currently `NULL`, write:
- `account.iban_ciphertext = encrypt_value(iban)`
- `account.iban_hash = blind_index(iban)`

The IBAN is treated as immutable per account — once set, never overwritten. (The user's bank does not change account IBANs; we don't try to handle that.)

Apply this in both the new-account-insert and existing-account-update paths so any backfill catches accounts the system already knows about.

### 2. Detection generalizes to any user IBAN

`backend/app/services/internal_transfer_service.py`:

Rename `_load_pocket_map` → `_load_user_account_iban_map`. Drop the `Account.provider == "manual"` filter. The new map contains every active user account that has `iban_hash` set, regardless of provider.

In `detect_for_transactions`, branch on the matched destination account's provider:

| Destination | Behavior |
|-------------|----------|
| `provider='manual'` | Create mirror transaction on the destination, link via `internal_transfers` row, flip `include_in_analytics=False` on both sides. (Existing PR #72 behavior — preserved.) |
| Synced (`provider='enable_banking'`, etc.) | NO mirror. Create `internal_transfers` row with `mirror_txn_id = NULL`. Mark source's `category_system_id = Transfer`, `include_in_analytics = False`. The destination side's own EB-delivered transaction will independently get the same treatment when its `counterparty_iban_hash` matches the source account's IBAN. |

Why no mirror for synced destinations: the destination side's transaction comes from EB on its own. Creating a mirror would double-count the transfer in the destination's balance.

Why still create an `internal_transfers` row even with no mirror: it preserves the unlink contract — the user can click "Unlink" on a wrongly-detected transfer, and the existing `unlink()` method already handles `mirror_txn_id = NULL` gracefully (it checks `if link.mirror_txn_id is not None` before attempting to delete).

### 3. Manual reconciliation reuses existing UI

`UpdateBalanceDialog` already supports any account via `createOrUpdateBalancingTransaction`. The "Adjust" button is wired in `asset-management.tsx:714-727` inside the Edit Account flow with no provider gating. **Zero frontend code changes.**

---

## Data Flow

### Synced → manual savings (existing PR #72 flow, unchanged)

```
EB delivers checking txn: amount=-500, counterparty_iban_hash=H(savings_iban)
  ↓
sync_service writes counterparty_iban_hash on the transaction row
  ↓
post_import_pipeline step 3 → InternalTransferService.detect_for_transactions
  ↓
_load_user_account_iban_map → finds savings account (provider='manual') matching H(savings_iban)
  ↓
matched.provider == 'manual' → CREATE mirror (+500 on savings)
                             → CREATE internal_transfers row {source_txn_id, mirror_txn_id}
                             → flip include_in_analytics=False on both
  ↓
post_import_pipeline → balance/timeseries recalc on both checking AND savings
```

### Synced → synced savings (new)

```
EB delivers checking txn: amount=-500, counterparty_iban_hash=H(other_iban)
  ↓
sync_service writes counterparty_iban_hash on the transaction row
  ↓
detect_for_transactions → _load_user_account_iban_map → finds Revo Pocket (provider='enable_banking')
  ↓
matched.provider != 'manual' → NO mirror
                             → CREATE internal_transfers row {source_txn_id, mirror_txn_id=NULL}
                             → flip source.include_in_analytics=False, set category_system_id=Transfer
  ↓
[Later, in the same or next sync]
EB delivers Revo Pocket txn: amount=+500, counterparty_iban_hash=H(checking_iban)
  ↓
detect_for_transactions runs on this transaction too
  ↓
matched is checking account → NO mirror, separate internal_transfers row, flip its own analytics flag
```

Both sides are independently identified as transfers. The `internal_transfers` table grows by 2 rows for one logical transfer between synced accounts — that's intentional. Each row links one transaction to "the account on the other side of the IBAN." The unlink UI works the same for either side.

### Manual reconciliation (existing flow)

```
User opens Edit Account → "Adjust" button → UpdateBalanceDialog
  ↓
Enter target balance for date X
  ↓
createOrUpdateBalancingTransaction → creates "Balancing Transfer" txn for the diff
  ↓
post_import_pipeline → balance/timeseries recalc
```

Unchanged. Works for both manual savings (the primary use case here — drift from interest, missed transfers) and any other account.

---

## Components Affected

| File | Change |
|------|--------|
| `backend/app/integrations/base.py` | Add `iban: Optional[str] = None` to `AccountData` |
| `backend/app/integrations/enable_banking_adapter.py` | `fetch_accounts` populates `iban` from raw EB response |
| `backend/app/services/sync_service.py` | Persist `iban_ciphertext` + `iban_hash` on synced accounts during upsert |
| `backend/app/services/internal_transfer_service.py` | Rename + generalize `_load_pocket_map` → `_load_user_account_iban_map`; branch on destination provider; no mirror for synced destinations; still create `internal_transfers` row with `mirror_txn_id=NULL` |
| `backend/tests/test_enable_banking_adapter.py` | Test `AccountData.iban` populated from raw |
| `backend/tests/test_account_sync_encryption.py` | Test synced account gets iban_hash on first sync (insert path) and on subsequent sync (update path, NULL → set) |
| `backend/tests/test_internal_transfer_service.py` | Add: synced↔synced detection creates link with `mirror_txn_id=NULL`, no mirror; manual destination still creates mirror |

No schema migration. No frontend changes. No new endpoints.

---

## Error Handling

- **Synced account has no IBAN.** EB returns IBAN for IBAN-using accounts. For non-IBAN accounts (e.g. some credit cards), `acc.get("iban")` is `None`. Skip silently — no `iban_hash` set, account participates only in normal categorization.
- **Encryption not configured.** `encrypt_value` and `blind_index` return `None` when `DATA_ENCRYPTION_KEY_CURRENT` is unset. Skip persistence — log a warning. Manual-pocket flow already handles this.
- **IBAN already set on account, sync sees a different IBAN.** Should not happen in practice (IBANs don't change). Defensive policy: do NOT overwrite. Log a warning. The detection logic uses whichever IBAN is currently stored.
- **Same IBAN on two of the user's accounts.** Should not happen for distinct bank accounts. The partial unique index `accounts_user_iban_hash_manual_uq` only enforces uniqueness for `provider='manual'`. For synced accounts we don't add a unique index — trust the bank. If it ever happens, detection picks the first match and logs a warning.

---

## Testing

### EB adapter
- `AccountData.iban` populated from `acc["iban"]`
- `AccountData.iban` is `None` when raw account has no IBAN

### Sync service
- New synced account: first sync writes `iban_ciphertext` + `iban_hash`
- Existing synced account with `iban_hash=NULL`: subsequent sync backfills hash + ciphertext
- Existing synced account with `iban_hash` already set: sync does NOT overwrite
- Account-data with `iban=None`: no encryption attempted, no warning either

### Internal transfer service
- Synced→synced: link created with `mirror_txn_id=NULL`, source flipped to `include_in_analytics=False`, category set to Transfer, NO mirror transaction on destination
- Synced→manual: existing PR #72 behavior preserved (mirror created, link with both txn IDs)
- Both sides detected independently when both have counterparty_iban_hash (verifying we don't double-detect a single source-side transaction)
- Unlink on a synced↔synced link (no mirror): source restored, link row deleted, no error

### Pipeline integration
- Full e2e: sync delivers checking txn + savings txn (synced↔synced), pipeline runs, both transactions tagged Transfer, both excluded from analytics, two `internal_transfers` rows exist, no mirrors

---

## What Does Not Change

- ✅ PR #72's manual-pocket flow (creation, backfill, mirror, balance update via mirror summing)
- ✅ Pipeline ordering: detection (step 3) before LLM (step 4)
- ✅ LLM filter on `include_in_analytics=True` (skips both detected sources and mirrors)
- ✅ `UpdateBalanceDialog` and "Balancing Transfer" category logic
- ✅ Unique-IBAN-per-manual-pocket constraint (still enforced for `provider='manual'` rows only)
- ✅ Sync idempotency, post-import pipeline structure
