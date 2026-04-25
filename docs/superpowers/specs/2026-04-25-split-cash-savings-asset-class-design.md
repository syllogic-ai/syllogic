# Split Cash and Savings Asset Classes — Design

**Date:** 2026-04-25
**Status:** Draft

## Problem

The Assets Overview groups all liquid bank balances under a single "Cash" asset class. This hides the split between operating cash (checking accounts used for day-to-day spending) and savings (long-term reserves). The user wants both to remain in the "liquid" half of the portfolio but be reported as distinct asset classes so they can see at a glance: how much is operating cash vs how much is parked in savings.

## Goal

Surface "Cash" (operating) and "Savings" as two separate asset classes across:

- Assets page (overview table, weight bar, expandable account list)
- Dashboard (net-worth trend stack)
- MCP server (account listings exposed to the AI agent)

Total liquidity, net worth, and existing percentages of the *combined* liquid pool remain mathematically unchanged — we are only splitting one bucket into two.

## Non-Goals

- No new database migration. The `accounts.account_type` column already stores `checking` and `savings` as distinct values.
- No changes to bank-sync logic. Enable Banking already maps `SVGS`/`MGLD`/`MOMA` → `savings` and `CACC`/`TRAN`/`CASH` → `checking` (`backend/app/integrations/enable_banking_adapter.py:39`).
- No changes to Sankey, recurring detection, categorizer, or transaction categorization.
- No changes to net-worth math or any monetary aggregate. Totals stay identical.
- No new "Savings" tab in account-creation wizards beyond the existing `account_type` selector — users can already pick "Savings Account".

## Key Architectural Insight

The split is purely an **aggregation-layer** concern. The data is already there:

- DB schema (`backend/app/models.py:28`, `frontend/lib/db/schema.ts:203`): `account_type` is a free-form string with `checking`, `savings`, `credit`, `investment`, `brokerage`, `crypto`, `property`, `vehicle`.
- Bank sync: assigns `savings` correctly today.
- The collapse to a single "Cash" asset class happens in exactly one function: `getAssetCategory()` at `frontend/lib/actions/dashboard.ts:770`, which maps both `checking` and `savings` to the asset key `"cash"`.

So the change is: introduce a new asset class key `"savings"` and re-route `account_type = savings` to it, parallel to (not nested under) `"cash"`.

## Design

### 1. Asset class taxonomy

Add `"savings"` to the `AssetCategoryKey` union as a peer of `cash` / `investment` / `crypto` / `property` / `vehicle` / `other`.

```ts
type AssetCategoryKey =
  | "cash"
  | "savings"   // new
  | "investment"
  | "crypto"
  | "property"
  | "vehicle"
  | "other";
```

This union is duplicated in two files (`frontend/lib/actions/dashboard.ts:749` and `frontend/components/assets/types.ts:1`) — both must be updated. (Out of scope to dedupe; following existing pattern.)

### 2. Mapping

Update `getAssetCategory()` (`frontend/lib/actions/dashboard.ts:770`):

```ts
const typeMap: Record<string, AssetCategoryKey> = {
  checking: "cash",
  savings: "savings",   // was "cash"
  credit: "other",
  investment: "investment",
  brokerage: "investment",
  crypto: "crypto",
  property: "property",
  vehicle: "vehicle",
};
```

### 3. Display metadata

Add label and color entries (in both `dashboard.ts` and `components/assets/types.ts`):

- Label: `"Savings"`
- Color: a sibling-of-blue (e.g. `#60A5FA` light blue, or `#06B6D4` cyan) — close enough to cash visually that the eye groups them as "liquid", but distinct.

Update the `categoryOrder` array at `frontend/lib/actions/dashboard.ts:951` and the equivalent at `:1138` so `savings` appears immediately after `cash`:

```ts
["cash", "savings", "investment", "crypto", "property", "vehicle", "other"]
```

### 4. Click-through navigation

Add `"savings"` to `ACCOUNT_CATEGORY_KEYS` at `frontend/components/assets/assets-table.tsx:15` so savings account rows link to the account detail page (same behavior as cash).

```ts
const ACCOUNT_CATEGORY_KEYS: AssetCategoryKey[] = ["cash", "savings", "investment", "crypto"];
```

### 5. MCP server

The MCP layer (`backend/app/mcp/tools/accounts.py`) already returns `account_type` on `list_accounts` and `get_account`, so a sufficiently smart agent can already distinguish. To make the asset-class concept first-class for the agent (mirroring UI semantics):

- Add a derived `asset_class` field to the account response. Computed server-side via the same mapping as the frontend (`checking → cash`, `savings → savings`, etc.). This avoids duplicating the mapping in the agent's prompt.
- Add an optional `asset_class` filter parameter to `list_accounts` (string, one of the asset-class keys). Filters accounts whose derived class matches.

Place the mapping helper in `backend/app/mcp/tools/_asset_class.py` (new file) so it can be imported wherever else needed.

### 6. Backfill

Enable Banking already classifies correctly, and the manual account-creation form (`frontend/components/accounts/account-form.tsx`, `frontend/components/settings/account-list.tsx:61`) already exposes `checking` vs `savings` as separate options. So no automated backfill is required.

If users have manually-created accounts mislabeled (e.g. an account they treat as savings but created as `checking`), the existing Settings → Accounts edit flow lets them flip the type. We will note this in the PR description as user-facing migration guidance — no code change needed.

### 7. Onboarding / mock data

- `frontend/lib/mock-data/transactions.ts:10` already supports `"savings"` — no change.
- `frontend/lib/actions/csv-import.ts:1649` defaults to `"checking"` for imported accounts — leave as-is. Users can re-classify post-import.

## Data Flow

```
Bank sync (Enable Banking)
   └── account_type = "savings" / "checking"  ── (no change)
         │
         ▼
DB: accounts.account_type
         │
         ├── Frontend
         │     ├── getAssetsOverview()  → getAssetCategory(t)  → asset key
         │     ├── getNetWorthTrend()   → same mapping         → stack series
         │     └── AssetsTable          → renders by category key
         │
         └── MCP server
               ├── list_accounts() returns account_type + new derived asset_class
               └── list_accounts(asset_class=...) filters server-side
```

## Risks & Edge Cases

- **Color collision in net-worth chart:** the dashboard's stacked area chart at `getNetWorthTrend()` already renders one stripe per asset class. Adding a new stripe is automatic from the mapping change, but the new color must remain distinguishable from `cash`'s blue. Pick a clearly different hue; verify visually.
- **User-mislabeled accounts:** any manual account a user created as `checking` that they actually treat as savings will continue to roll up under "Cash" until they edit it. Acceptable — covered by the existing edit UI.
- **MCP backwards compatibility:** adding a new field to `list_accounts` response is additive — existing MCP clients are unaffected. Adding a new optional filter parameter is also additive.

## Testing

- Unit-test `getAssetCategory()` for the savings → savings mapping.
- Verify Assets Overview UI renders Cash and Savings as separate rows and the weight bar splits them.
- Verify net-worth trend on the dashboard renders savings as a separate stack.
- MCP: invoke `list_accounts` and confirm `asset_class` is present and correct; invoke `list_accounts(asset_class="savings")` and confirm only savings accounts return.
- Smoke-test with the user's actual data: ABN Long Term Savings should appear under Savings; ABN AMRO Giannis (checking) should remain under Cash.

## Open Questions

None — design is mechanical and the data layer already supports it.
