# Split Cash and Savings Asset Classes — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Split the single "Cash" asset class into two distinct peer classes — "Cash" (operating: `checking`) and "Savings" (`savings`) — across the assets page, dashboard net-worth chart, and MCP server, without any DB migration.

**Architecture:** The DB already stores `account_type` with distinct `checking`/`savings` values. The split is purely an aggregation-layer change. We extract the `account_type → asset_class` mapping into a single source-of-truth module on each side (frontend TS, backend Python), update the mapping so `savings` resolves to its own class, and add a new entry (`savings`) to the asset-class union, label/color tables, and ordered render list. MCP gains a derived `asset_class` field and an optional filter parameter (additive — backwards compatible).

**Tech Stack:** Next.js (App Router) + Drizzle on the frontend; FastAPI + SQLAlchemy on the backend. Tests: Vitest (frontend, `lib/**/*.test.ts`), pytest (backend, `backend/tests/`).

**Spec:** [docs/superpowers/specs/2026-04-25-split-cash-savings-asset-class-design.md](../specs/2026-04-25-split-cash-savings-asset-class-design.md)

---

## File Structure

**New files (single-source-of-truth modules):**
- `frontend/lib/assets/asset-category.ts` — exports `AssetCategoryKey`, `ASSET_CATEGORY_LABELS`, `ASSET_CATEGORY_COLORS`, `ASSET_CATEGORY_ORDER`, and `getAssetCategory(accountType)`. Replaces duplicated definitions in `dashboard.ts` and `components/assets/types.ts`.
- `frontend/lib/assets/asset-category.test.ts` — Vitest unit tests for `getAssetCategory`.
- `backend/app/mcp/tools/_asset_class.py` — exports `ASSET_CLASS_KEYS` and `account_type_to_asset_class(account_type)`.
- `backend/tests/test_asset_class_mapping.py` — pytest tests for the Python mapping.

**Modified files:**
- `frontend/lib/actions/dashboard.ts` — remove duplicated taxonomy, import from new module. Update `categoryOrder` arrays at ~ln 951 and ~ln 1138.
- `frontend/components/assets/types.ts` — re-export the taxonomy from the new module so existing imports keep working.
- `frontend/components/assets/assets-table.tsx:15` — add `"savings"` to `ACCOUNT_CATEGORY_KEYS`.
- `frontend/app/(dashboard)/assets/asset-management.tsx` — verify `Add Asset` flow handles savings (the `account_type` selector already exposes "Savings Account" — no logic change expected; verify rendering).
- `backend/app/mcp/tools/accounts.py` — add `asset_class` derived field to `list_accounts` and `get_account` responses; add optional `asset_class` filter parameter to `list_accounts`.

**Out of scope:**
- DB migrations (none needed)
- Bank-sync changes (Enable Banking already classifies)
- Net-worth math (mathematically identical — split bucket only)

---

## Task 1: Extract frontend asset-category taxonomy into a single module

**Files:**
- Create: `frontend/lib/assets/asset-category.ts`
- Create: `frontend/lib/assets/asset-category.test.ts`

- [ ] **Step 1: Write failing tests for `getAssetCategory`**

Create `frontend/lib/assets/asset-category.test.ts`:

```ts
import { describe, it, expect } from "vitest";
import {
  getAssetCategory,
  ASSET_CATEGORY_LABELS,
  ASSET_CATEGORY_COLORS,
  ASSET_CATEGORY_ORDER,
} from "./asset-category";

describe("getAssetCategory", () => {
  it("maps checking to cash", () => {
    expect(getAssetCategory("checking")).toBe("cash");
  });

  it("maps savings to savings (its own asset class)", () => {
    expect(getAssetCategory("savings")).toBe("savings");
  });

  it("maps credit to other", () => {
    expect(getAssetCategory("credit")).toBe("other");
  });

  it("maps investment and brokerage to investment", () => {
    expect(getAssetCategory("investment")).toBe("investment");
    expect(getAssetCategory("brokerage")).toBe("investment");
  });

  it("maps crypto / property / vehicle to themselves", () => {
    expect(getAssetCategory("crypto")).toBe("crypto");
    expect(getAssetCategory("property")).toBe("property");
    expect(getAssetCategory("vehicle")).toBe("vehicle");
  });

  it("is case-insensitive", () => {
    expect(getAssetCategory("SAVINGS")).toBe("savings");
    expect(getAssetCategory("Checking")).toBe("cash");
  });

  it("falls back to other for unknown types", () => {
    expect(getAssetCategory("zzz")).toBe("other");
  });
});

describe("ASSET_CATEGORY_ORDER", () => {
  it("places savings immediately after cash", () => {
    const cashIdx = ASSET_CATEGORY_ORDER.indexOf("cash");
    const savingsIdx = ASSET_CATEGORY_ORDER.indexOf("savings");
    expect(savingsIdx).toBe(cashIdx + 1);
  });

  it("includes all 7 asset classes exactly once", () => {
    expect(ASSET_CATEGORY_ORDER).toEqual([
      "cash",
      "savings",
      "investment",
      "crypto",
      "property",
      "vehicle",
      "other",
    ]);
  });
});

describe("display metadata", () => {
  it("provides a label and color for every key in the order", () => {
    for (const key of ASSET_CATEGORY_ORDER) {
      expect(ASSET_CATEGORY_LABELS[key]).toBeTruthy();
      expect(ASSET_CATEGORY_COLORS[key]).toMatch(/^#[0-9A-Fa-f]{6}$/);
    }
  });

  it("uses distinct colors for cash and savings", () => {
    expect(ASSET_CATEGORY_COLORS.cash).not.toBe(ASSET_CATEGORY_COLORS.savings);
  });

  it("labels savings as 'Savings'", () => {
    expect(ASSET_CATEGORY_LABELS.savings).toBe("Savings");
  });
});
```

- [ ] **Step 2: Run tests, confirm they fail**

```bash
cd frontend && pnpm vitest run lib/assets/asset-category.test.ts
```
Expected: FAIL with module not found.

- [ ] **Step 3: Write the module**

Create `frontend/lib/assets/asset-category.ts`:

```ts
export type AssetCategoryKey =
  | "cash"
  | "savings"
  | "investment"
  | "crypto"
  | "property"
  | "vehicle"
  | "other";

export const ASSET_CATEGORY_ORDER: readonly AssetCategoryKey[] = [
  "cash",
  "savings",
  "investment",
  "crypto",
  "property",
  "vehicle",
  "other",
] as const;

export const ASSET_CATEGORY_LABELS: Record<AssetCategoryKey, string> = {
  cash: "Cash",
  savings: "Savings",
  investment: "Investment",
  crypto: "Crypto",
  property: "Property",
  vehicle: "Vehicle",
  other: "Other",
};

export const ASSET_CATEGORY_COLORS: Record<AssetCategoryKey, string> = {
  cash: "#3B82F6",        // blue
  savings: "#06B6D4",     // cyan — sibling of blue, distinct in net-worth stack
  investment: "#10B981",  // green
  crypto: "#F59E0B",      // amber
  property: "#8B5CF6",    // purple
  vehicle: "#EC4899",     // pink
  other: "#6B7280",       // gray
};

const ACCOUNT_TYPE_TO_CATEGORY: Record<string, AssetCategoryKey> = {
  checking: "cash",
  savings: "savings",
  credit: "other",
  investment: "investment",
  brokerage: "investment",
  crypto: "crypto",
  property: "property",
  vehicle: "vehicle",
};

export function getAssetCategory(accountType: string): AssetCategoryKey {
  return ACCOUNT_TYPE_TO_CATEGORY[accountType.toLowerCase()] ?? "other";
}
```

- [ ] **Step 4: Run tests, confirm they pass**

```bash
cd frontend && pnpm vitest run lib/assets/asset-category.test.ts
```
Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add frontend/lib/assets/asset-category.ts frontend/lib/assets/asset-category.test.ts
git commit -m "feat(assets): extract asset-category taxonomy with savings as own class"
```

---

## Task 2: Wire `dashboard.ts` to the new module

**Files:**
- Modify: `frontend/lib/actions/dashboard.ts:749-782`, `:951`, `:1138`

- [ ] **Step 1: Replace the inline taxonomy with imports**

In `frontend/lib/actions/dashboard.ts`, find the block from `// Asset category types and mapping` (around line 748) through the end of `getAssetCategory` (around line 782). Replace the entire block with an import at the top of the file:

Add to the imports near the top of the file (next to existing `@/lib/...` imports):

```ts
import {
  type AssetCategoryKey,
  ASSET_CATEGORY_LABELS,
  ASSET_CATEGORY_COLORS,
  ASSET_CATEGORY_ORDER,
  getAssetCategory,
} from "@/lib/assets/asset-category";
```

Delete lines 748-782 (the inline `type AssetCategoryKey`, `ASSET_CATEGORY_COLORS`, `ASSET_CATEGORY_LABELS`, `getAssetCategory` definitions).

- [ ] **Step 2: Replace both hard-coded `categoryOrder` arrays**

Find at line ~951:

```ts
const categoryOrder: AssetCategoryKey[] = ["cash", "investment", "crypto", "property", "vehicle", "other"];
```

Replace with:

```ts
const categoryOrder = ASSET_CATEGORY_ORDER;
```

Then find the second occurrence inside `getNetWorthTrend()` near line ~1138 (search for `key as AssetCategoryKey` to locate). Replace any equivalent hard-coded order array there with `ASSET_CATEGORY_ORDER`. If the function iterates `Object.keys(ASSET_CATEGORY_LABELS)`, leave that as-is (it's correct — savings is now a key).

- [ ] **Step 3: Type-check**

```bash
cd frontend && pnpm tsc --noEmit
```
Expected: no new errors.

- [ ] **Step 4: Run all frontend tests**

```bash
cd frontend && pnpm vitest run
```
Expected: PASS (no regressions).

- [ ] **Step 5: Commit**

```bash
git add frontend/lib/actions/dashboard.ts
git commit -m "refactor(dashboard): use shared asset-category module; surfaces savings as own class"
```

---

## Task 3: Re-export taxonomy from `components/assets/types.ts`

**Files:**
- Modify: `frontend/components/assets/types.ts:1-65`

- [ ] **Step 1: Replace the duplicated definitions with re-exports**

Replace `frontend/components/assets/types.ts` with:

```ts
export type {
  AssetCategoryKey,
} from "@/lib/assets/asset-category";

export {
  ASSET_CATEGORY_LABELS,
  ASSET_CATEGORY_COLORS,
} from "@/lib/assets/asset-category";

export type AssetType = "account" | "property" | "vehicle";

export interface AssetAccount {
  id: string;
  name: string;
  institution: string | null;
  value: number;
  percentage: number;
  currency: string;
  initial: string;
}

export interface AssetCategory {
  key: import("@/lib/assets/asset-category").AssetCategoryKey;
  label: string;
  color: string;
  value: number;
  percentage: number;
  isActive: boolean;
  accounts: AssetAccount[];
}

export interface AssetsOverviewData {
  total: number;
  currency: string;
  categories: AssetCategory[];
}

export const PROPERTY_TYPES = [
  { value: "residential", label: "Residential" },
  { value: "commercial", label: "Commercial" },
  { value: "land", label: "Land" },
  { value: "other", label: "Other" },
] as const;

export const VEHICLE_TYPES = [
  { value: "car", label: "Car" },
  { value: "motorcycle", label: "Motorcycle" },
  { value: "boat", label: "Boat" },
  { value: "rv", label: "RV" },
  { value: "other", label: "Other" },
] as const;

export type PropertyType = typeof PROPERTY_TYPES[number]["value"];
export type VehicleType = typeof VEHICLE_TYPES[number]["value"];
```

- [ ] **Step 2: Type-check**

```bash
cd frontend && pnpm tsc --noEmit
```
Expected: no errors.

- [ ] **Step 3: Commit**

```bash
git add frontend/components/assets/types.ts
git commit -m "refactor(assets): re-export taxonomy from shared module"
```

---

## Task 4: Make Savings rows click-through in the assets table

**Files:**
- Modify: `frontend/components/assets/assets-table.tsx:15`

- [ ] **Step 1: Add `"savings"` to `ACCOUNT_CATEGORY_KEYS`**

Change line 15 from:

```ts
const ACCOUNT_CATEGORY_KEYS: AssetCategoryKey[] = ["cash", "investment", "crypto"];
```

to:

```ts
const ACCOUNT_CATEGORY_KEYS: AssetCategoryKey[] = ["cash", "savings", "investment", "crypto"];
```

- [ ] **Step 2: Type-check**

```bash
cd frontend && pnpm tsc --noEmit
```
Expected: no errors.

- [ ] **Step 3: Commit**

```bash
git add frontend/components/assets/assets-table.tsx
git commit -m "feat(assets-table): make savings account rows click-through"
```

---

## Task 5: Smoke-test the assets page in the browser

**Files:** none

- [ ] **Step 1: Start dev server**

```bash
cd frontend && pnpm dev
```

- [ ] **Step 2: Navigate to `/assets` and verify**

Open `http://localhost:3000/assets`. Verify:
1. Cash and Savings appear as **two separate rows** in the Assets Overview table.
2. The horizontal weight bar at the top of the page shows two segments (blue = Cash, cyan = Savings) plus any other active classes.
3. Cash row contains only `account_type=checking` accounts (e.g. ABN AMRO Giannis, Revo Pro, Revo Joint, Revo Pocket — based on the user's data).
4. Savings row contains only `account_type=savings` accounts (e.g. ABN Long Term Savings, ABN Partner if it's savings).
5. Cash + Savings totals = the previous combined Cash total (€17,419 in the screenshot).
6. Clicking a Savings account row navigates to `/accounts/<id>`.

- [ ] **Step 3: Navigate to `/` (dashboard) and verify the net-worth trend**

The stacked area chart should now render Savings as a distinct stripe in cyan, sitting next to the Cash blue stripe. Total net worth at any date is unchanged.

- [ ] **Step 4: If anything is wrong, fix and re-test before proceeding**

If a checking account is appearing under Savings or vice versa, the user has likely manually labeled it incorrectly. Document this in the PR body as "user-facing migration: re-label any mis-classified manual accounts via Settings → Accounts."

- [ ] **Step 5: Commit (if any tweaks were needed)**

If no tweaks: skip this step.

---

## Task 6: Backend — extract Python asset-class mapping

**Files:**
- Create: `backend/app/mcp/tools/_asset_class.py`
- Create: `backend/tests/test_asset_class_mapping.py`

- [ ] **Step 1: Write failing pytest**

Create `backend/tests/test_asset_class_mapping.py`:

```python
"""Tests for the MCP asset-class mapping helper."""
import pytest

from app.mcp.tools._asset_class import (
    ASSET_CLASS_KEYS,
    account_type_to_asset_class,
)


class TestAccountTypeToAssetClass:
    def test_checking_maps_to_cash(self):
        assert account_type_to_asset_class("checking") == "cash"

    def test_savings_maps_to_savings(self):
        assert account_type_to_asset_class("savings") == "savings"

    def test_credit_maps_to_other(self):
        assert account_type_to_asset_class("credit") == "other"

    def test_investment_and_brokerage_map_to_investment(self):
        assert account_type_to_asset_class("investment") == "investment"
        assert account_type_to_asset_class("brokerage") == "investment"

    def test_crypto_property_vehicle_self(self):
        assert account_type_to_asset_class("crypto") == "crypto"
        assert account_type_to_asset_class("property") == "property"
        assert account_type_to_asset_class("vehicle") == "vehicle"

    def test_case_insensitive(self):
        assert account_type_to_asset_class("SAVINGS") == "savings"
        assert account_type_to_asset_class("Checking") == "cash"

    def test_unknown_returns_other(self):
        assert account_type_to_asset_class("zzz") == "other"

    def test_none_returns_other(self):
        assert account_type_to_asset_class(None) == "other"


class TestAssetClassKeys:
    def test_includes_savings(self):
        assert "savings" in ASSET_CLASS_KEYS

    def test_includes_all_seven(self):
        assert ASSET_CLASS_KEYS == (
            "cash",
            "savings",
            "investment",
            "crypto",
            "property",
            "vehicle",
            "other",
        )
```

- [ ] **Step 2: Run pytest, confirm fail**

```bash
cd backend && pytest tests/test_asset_class_mapping.py -v
```
Expected: FAIL — module not found.

- [ ] **Step 3: Write the helper module**

Create `backend/app/mcp/tools/_asset_class.py`:

```python
"""Mapping between Account.account_type values and MCP asset-class keys.

Mirrors the frontend taxonomy in `frontend/lib/assets/asset-category.ts`.
Keep these two in sync — both sides are intentionally explicit so neither
side has to ship the other's enum.
"""
from __future__ import annotations

from typing import Optional

ASSET_CLASS_KEYS: tuple[str, ...] = (
    "cash",
    "savings",
    "investment",
    "crypto",
    "property",
    "vehicle",
    "other",
)

_ACCOUNT_TYPE_TO_ASSET_CLASS: dict[str, str] = {
    "checking": "cash",
    "savings": "savings",
    "credit": "other",
    "investment": "investment",
    "brokerage": "investment",
    "crypto": "crypto",
    "property": "property",
    "vehicle": "vehicle",
}


def account_type_to_asset_class(account_type: Optional[str]) -> str:
    """Return the asset-class key for a given account_type. Falls back to 'other'."""
    if not account_type:
        return "other"
    return _ACCOUNT_TYPE_TO_ASSET_CLASS.get(account_type.lower(), "other")
```

- [ ] **Step 4: Run pytest, confirm pass**

```bash
cd backend && pytest tests/test_asset_class_mapping.py -v
```
Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add backend/app/mcp/tools/_asset_class.py backend/tests/test_asset_class_mapping.py
git commit -m "feat(mcp): add asset-class mapping helper with savings as own class"
```

---

## Task 7: Expose `asset_class` field and filter on MCP `list_accounts` / `get_account`

**Files:**
- Modify: `backend/app/mcp/tools/accounts.py:11-90`
- Add tests: `backend/tests/test_mcp_accounts_asset_class.py`

- [ ] **Step 1: Write failing pytest for the MCP shape**

Create `backend/tests/test_mcp_accounts_asset_class.py`:

```python
"""Tests for asset_class on MCP list_accounts / get_account responses."""
from __future__ import annotations

import uuid
from decimal import Decimal

import pytest

from app.models import Account
from app.mcp.tools.accounts import list_accounts, get_account


@pytest.fixture
def seeded_user(db_session):
    user_id = str(uuid.uuid4())
    rows = [
        Account(
            user_id=user_id,
            name="Op Checking",
            account_type="checking",
            institution="ING",
            currency="EUR",
            provider="manual",
            is_active=True,
            starting_balance=Decimal("0"),
        ),
        Account(
            user_id=user_id,
            name="Long Term Savings",
            account_type="savings",
            institution="ABN",
            currency="EUR",
            provider="manual",
            is_active=True,
            starting_balance=Decimal("0"),
        ),
        Account(
            user_id=user_id,
            name="Brokerage",
            account_type="brokerage",
            institution="IBKR",
            currency="EUR",
            provider="ibkr",
            is_active=True,
            starting_balance=Decimal("0"),
        ),
    ]
    for r in rows:
        db_session.add(r)
    db_session.commit()
    yield user_id
    for r in rows:
        db_session.delete(r)
    db_session.commit()


def test_list_accounts_includes_asset_class(seeded_user):
    accounts = list_accounts(user_id=seeded_user)
    by_name = {a["name"]: a for a in accounts}
    assert by_name["Op Checking"]["asset_class"] == "cash"
    assert by_name["Long Term Savings"]["asset_class"] == "savings"
    assert by_name["Brokerage"]["asset_class"] == "investment"


def test_list_accounts_filters_by_asset_class(seeded_user):
    only_savings = list_accounts(user_id=seeded_user, asset_class="savings")
    assert [a["name"] for a in only_savings] == ["Long Term Savings"]
    assert all(a["asset_class"] == "savings" for a in only_savings)


def test_list_accounts_filter_unknown_asset_class_returns_empty(seeded_user):
    assert list_accounts(user_id=seeded_user, asset_class="zzz") == []


def test_get_account_includes_asset_class(seeded_user):
    accounts = list_accounts(user_id=seeded_user)
    savings_id = next(a["id"] for a in accounts if a["name"] == "Long Term Savings")
    detail = get_account(user_id=seeded_user, account_id=savings_id)
    assert detail is not None
    assert detail["asset_class"] == "savings"
```

- [ ] **Step 2: Run pytest, confirm fail**

```bash
cd backend && pytest tests/test_mcp_accounts_asset_class.py -v
```
Expected: FAIL — `asset_class` key missing / `asset_class` parameter not accepted.

- [ ] **Step 3: Modify `accounts.py` — add field and filter**

Replace `backend/app/mcp/tools/accounts.py` content for the two affected functions:

At the top of the file, add:

```python
from app.mcp.tools._asset_class import account_type_to_asset_class
```

Update `list_accounts` signature and body:

```python
def list_accounts(
    user_id: str,
    include_inactive: bool = False,
    asset_class: Optional[str] = None,
) -> list[dict]:
    """
    List all accounts for a user.

    Args:
        user_id: The user's ID
        include_inactive: Whether to include inactive accounts (default: False)
        asset_class: Optional asset-class filter, e.g. "cash", "savings",
            "investment", "crypto", "property", "vehicle", "other".

    Returns:
        List of account dictionaries with id, name, type, institution, currency,
        balance, asset_class, etc.
    """
    with get_db() as db:
        query = db.query(Account).filter(Account.user_id == user_id)

        if not include_inactive:
            query = query.filter(Account.is_active == True)

        accounts = query.order_by(Account.name).all()

        results = [
            {
                "id": str(account.id),
                "name": account.name,
                "account_type": account.account_type,
                "asset_class": account_type_to_asset_class(account.account_type),
                "institution": account.institution,
                "currency": account.currency,
                "provider": account.provider,
                "balance_available": float(account.balance_available) if account.balance_available else None,
                "starting_balance": float(account.starting_balance) if account.starting_balance else 0,
                "functional_balance": float(account.functional_balance) if account.functional_balance else None,
                "is_active": account.is_active,
                "alias_patterns": account.alias_patterns or [],
                "last_synced_at": account.last_synced_at.isoformat() if account.last_synced_at else None,
                "created_at": account.created_at.isoformat() if account.created_at else None,
            }
            for account in accounts
        ]

        if asset_class is not None:
            normalized = asset_class.lower()
            results = [r for r in results if r["asset_class"] == normalized]

        return results
```

Update `get_account` to add the field. Inside the returned dict, add this line right after `"account_type": account.account_type,`:

```python
"asset_class": account_type_to_asset_class(account.account_type),
```

- [ ] **Step 4: Run pytest, confirm pass**

```bash
cd backend && pytest tests/test_mcp_accounts_asset_class.py -v
```
Expected: all tests pass.

- [ ] **Step 5: Run full backend test suite**

```bash
cd backend && pytest tests/test_asset_class_mapping.py tests/test_mcp_accounts_asset_class.py tests/test_mcp_server_health.py tests/test_mcp_pagination.py -v
```
Expected: PASS (no regressions on adjacent MCP tests).

- [ ] **Step 6: Commit**

```bash
git add backend/app/mcp/tools/accounts.py backend/tests/test_mcp_accounts_asset_class.py
git commit -m "feat(mcp): expose asset_class on accounts and add asset_class filter"
```

---

## Task 8: Update MCP server description / docstring exposed to clients

**Files:**
- Modify: wherever `list_accounts` is registered as an MCP tool (search for the registration site).

- [ ] **Step 1: Find the registration site**

```bash
cd backend && grep -RIn "list_accounts" app/mcp --include="*.py" | grep -v "tools/accounts.py"
```

- [ ] **Step 2: Update the tool description**

In the file(s) returned, locate the docstring or description string passed to the MCP framework's tool decorator/registry for `list_accounts`. Append a sentence describing the new `asset_class` parameter:

> "Optionally filter by `asset_class` ('cash', 'savings', 'investment', 'crypto', 'property', 'vehicle', 'other')."

The new field `asset_class` on each returned record is self-documenting via the docstring already updated in Task 7 — no further change needed unless the registration explicitly enumerates returned fields.

- [ ] **Step 3: Run MCP discovery test**

```bash
cd backend && pytest tests/test_mcp_discovery.py -v
```
Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add -u backend/app/mcp
git commit -m "docs(mcp): document asset_class filter on list_accounts"
```

If no registration-site changes were needed (description already pulls from the function docstring), skip the commit.

---

## Task 9: Final verification

**Files:** none

- [ ] **Step 1: Run all tests both sides**

```bash
cd frontend && pnpm vitest run
cd ../backend && pytest tests/test_asset_class_mapping.py tests/test_mcp_accounts_asset_class.py tests/test_mcp_server_health.py tests/test_mcp_discovery.py tests/test_mcp_pagination.py -v
```
Expected: all green.

- [ ] **Step 2: Type-check**

```bash
cd frontend && pnpm tsc --noEmit
```
Expected: no errors.

- [ ] **Step 3: Manual UI smoke test (re-run Task 5 checklist)**

Confirm Cash + Savings render correctly with real data on both `/assets` and `/`.

- [ ] **Step 4: Open PR**

```bash
gh pr create --title "Split Cash and Savings into distinct asset classes" --body "$(cat <<'EOF'
## Summary
- Surface "Savings" as its own asset class on the Assets page and dashboard, distinct from operating "Cash"
- Add a derived `asset_class` field and optional `asset_class` filter to MCP `list_accounts` / `get_account`
- No DB migration: existing `account_type` column already distinguishes `checking` vs `savings`

## User-facing migration
If any manually-created account is mislabeled (e.g. created as `checking` but actually used for savings), edit it via Settings → Accounts. Bank-synced accounts (Enable Banking) are already classified correctly.

## Test plan
- [ ] Vitest: `pnpm vitest run`
- [ ] pytest: `pytest tests/test_asset_class_mapping.py tests/test_mcp_accounts_asset_class.py`
- [ ] Manual: `/assets` shows Cash and Savings as separate rows; total liquidity unchanged
- [ ] Manual: dashboard net-worth chart renders Savings as a distinct stripe
- [ ] Manual: MCP `list_accounts` returns `asset_class` and `list_accounts(asset_class="savings")` filters correctly
EOF
)"
```

---

## Self-Review Notes

- ✅ Spec coverage: every section of the spec maps to a task — taxonomy split (Tasks 1-3), UI click-through (Task 4), UI smoke test (Task 5), MCP backend (Tasks 6-8).
- ✅ No placeholders: every code-changing step shows the exact code.
- ✅ Type consistency: `AssetCategoryKey` defined once in Task 1; `ASSET_CATEGORY_ORDER` referenced consistently in Task 2; `account_type_to_asset_class` defined in Task 6 and used in Task 7.
- ✅ TDD: every code module gets a failing test first, then implementation, then green.
- ✅ Frequent commits: each task ends with a commit.
