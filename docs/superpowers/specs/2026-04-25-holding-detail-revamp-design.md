# Holding Detail Page Revamp — Design Spec

_Date: 2026-04-25_

## 1. Goals

Replace the bare-bones `/investments/[holdingId]` page (currently a raw history table) with a full Syllogic-style single-column detail view. Add row-click navigation from the holdings table. No new backend endpoints required.

Out of scope:
- Editing IBKR-synced holdings (backend enforces manual-only)
- Deleting a holding from the detail page (already available in the table)
- Price alerts or watchlist

## 2. Entry point

`HoldingsTableHF` rows become clickable: `cursor: pointer` + `onClick={() => router.push('/investments/' + h.id)}`. The existing kebab/delete button must stop propagation so it doesn't trigger navigation.

## 3. Data fetching

Server component (`app/(dashboard)/investments/[holdingId]/page.tsx`) fetches in parallel:

```ts
const [holdings, history, portfolio] = await Promise.all([
  listHoldings(),
  getHoldingHistory(holdingId, from, to),   // initial 1M window
  getPortfolio(),
]);
const holding = holdings.find(h => h.id === holdingId);
if (!holding) notFound();
```

No backend change. `listHoldings()` is lightweight (single user, small dataset).

Passes `holding`, `initialHistory`, `portfolio` to `<HoldingDetailView>` as props.

## 4. Layout (single column, `.syllogic-surface`)

### 4.1 Back breadcrumb
`← All holdings` → `router.push("/investments")`. Small, muted, top-left.

### 4.2 Header row
Left-aligned, flex row:
- Symbol in large bold (e.g. `VUAA`)
- Type badge (`TypeBadge` from `HoldingsTableHF`)
- Full name in muted text
- Account badge (bordered, muted) pulled right
- Stale amber dot if `holding.is_stale`

### 4.3 Stats strip
Five cells (same border/padding style as `PortfolioStatsStrip`):

| Cell | Value | Notes |
|---|---|---|
| Current price | `current_price` | currency from `holding.currency` |
| Market value | `current_value_user_currency` | portfolio currency symbol |
| Total return | `(marketValue − costBasis) / costBasis × 100` | `—` if `avg_cost` is null |
| Avg cost / share | `avg_cost` | `—` if null |
| Portfolio weight | `current_value_user_currency / portfolio.total_value × 100` | `%` |

`costBasis = Number(avg_cost) × Number(quantity)`.

### 4.4 Chart card
`PortfolioChart` component (already exists) inside a bordered card. Range toggle `1W / 1M / 3M / 1Y / ALL` in top-right. On range change, call server action `fetchHoldingHistoryRange(holdingId, range)`. Card opacity dims to 0.7 while `useTransition` is pending (same pattern as `InvestmentsOverview`).

Chart `data` is `history.map(p => Number(p.value))`. `currencySymbol` from `portfolio.currency`.

Empty/single-point history → `PortfolioChart` already renders "Not enough history".

### 4.5 Edit panel
Rendered **only** when `holding.source === "manual"`. Always visible (not behind a button). Inline form with dark top border (`border-top: 2px solid T.primary`), same card style as `BrokerForm`/`ManualForm`.

Fields:
- **Quantity** — number input, pre-filled from `holding.quantity`
- **Avg cost** — number input, optional, pre-filled from `holding.avg_cost ?? ""`
- **As of date** — date input, optional, pre-filled from `holding.as_of_date` if set, otherwise empty

On submit → `updateHolding(holdingId, { quantity, avg_cost, as_of_date })` → `router.refresh()`. Error displayed inline. "Save changes" primary button + loading state.

## 5. New frontend API function

Add to `frontend/lib/api/investments.ts`:

```ts
export async function updateHolding(
  holdingId: string,
  payload: { quantity?: string; avg_cost?: string; as_of_date?: string },
): Promise<void> {
  await signedFetch("PATCH", `/api/investments/holdings/${holdingId}`, {
    body: payload,
  });
}
```

## 6. New server action

Add to `frontend/lib/actions/investments.ts`:

```ts
export async function fetchHoldingHistoryRange(holdingId: string, range: Range) {
  "use server";
  const { getHoldingHistory } = await import("@/lib/api/investments");
  const { from, to } = rangeToDates(range);
  return getHoldingHistory(holdingId, from, to);
}
```

## 7. Components

### New
- **`HoldingDetailView.tsx`** (client) — composes all sections, owns `range` + `history` state, handles edit submit

### Modified
- **`HoldingsTableHF.tsx`** — add row `onClick` + `cursor: pointer`; add `e.stopPropagation()` to the delete button click handler
- **`lib/api/investments.ts`** — add `updateHolding`
- **`lib/actions/investments.ts`** — add `fetchHoldingHistoryRange`
- **`app/(dashboard)/investments/[holdingId]/page.tsx`** — full rewrite

## 8. Edge cases

| Scenario | Behaviour |
|---|---|
| `holdingId` not found in `listHoldings()` | `notFound()` → 404 page |
| `avg_cost` is null | Stats cells show `—`; edit form shows empty avg cost field |
| `source !== "manual"` | Edit panel not rendered |
| History empty or 1 point | Chart shows "Not enough history" (existing fallback) |
| Edit save fails | Error shown inline, form stays open |

## 9. Testing

- Unit: `updateHolding` payload construction (mock `signedFetch`)
- Unit: `fetchHoldingHistoryRange` delegates correctly to `getHoldingHistory`
- RTL: `HoldingDetailView` with a manual holding renders edit panel; with IBKR holding hides it
- RTL: stats strip shows `—` for total return when `avg_cost` is null

## 10. File plan

```
frontend/
  app/(dashboard)/investments/[holdingId]/page.tsx     [rewrite]
  components/investments/HoldingDetailView.tsx          [new]
  components/investments/HoldingsTableHF.tsx            [modify — row click]
  lib/api/investments.ts                                [modify — updateHolding]
  lib/actions/investments.ts                            [modify — fetchHoldingHistoryRange]
```
