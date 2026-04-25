# Investments Revamp — Design Spec

_Date: 2026-04-25_
_Source: Claude Design handoff bundle `Investments` (chat 1, 2026-04-25 13:26 UTC)._
_Picked variants: `/investments` = **timeline-first (B)** + **empty state**; `/investments/connect` = **path-picker (B)**._

## 1. Goals

Replace the current bare-bones investments dashboard and connect page with the high-fidelity Syllogic-style mono UI specified in the handoff. Visual parity with `Investments.html`; functional parity with current backend (`lib/api/investments.ts`).

Out of scope:
- Editing holdings inline (only add + delete remain).
- Mobile-first reflow (responsive matches existing dashboard pages).
- New backend endpoints.

## 2. Surface map

| Route | Behavior |
|---|---|
| `/investments` (server) | If `holdings.length === 0` → render `InvestmentsEmpty`. Otherwise → render `InvestmentsOverview` (timeline-first). |
| `/investments/connect` | Path-picker (broker / manual). Selecting a card reveals the matching form panel inline. |

Topbar action on overview: secondary "Connect broker" button → `/investments/connect`.

## 3. Components to build

All under `frontend/components/investments/`. New components, then replace/repurpose old ones.

### New
- **`InvestmentsOverview.tsx`** (client) — composes hero, chart, stats strip, allocation, holdings table; owns `range`, `sortKey`, `sortDir`, `filterType` state. Receives `holdings`, `portfolio`, initial `history` from the server page.
- **`PortfolioHero.tsx`** — value, ▲/▼ change for selected range, "as of" timestamp, stale badge, `1W/1M/3M/1Y/ALL` segmented range toggle.
- **`PortfolioChart.tsx`** — SVG area + line chart with grid lines, Y-axis labels, X-axis date labels, end-of-series dot. Accepts `data: number[]` and `range`. Re-fetches via `getPortfolioHistory(from, to)` when range changes (client action wrapper) — server still does initial render to avoid flash.
- **`PortfolioStatsStrip.tsx`** — 5-cell strip (Cost basis, Unrealized P&L, Return, Holdings count, Best day). Compute from portfolio + history. "Best day" can be derived from history (max single-day delta).
- **`AllocationDonut.tsx`** — replaces existing `AllocationChart`. SVG donut + legend. Accepts `segments: { label, pct, color }[]`.
- **`AllocationRow.tsx`** — pair of donuts ("By instrument", "By currency").
- **`HoldingsTableHF.tsx`** — high-fidelity holdings table: sortable headers, type filter segmented control (All/ETF/Equity/Cash), stale-row tint, type badge, per-row kebab → delete. Footer totals row.
- **`InvestmentsEmpty.tsx`** — split path card (Connect / Add manually) — both buttons navigate to `/investments/connect`.
- **`ConnectPathPicker.tsx`** — page body for `/investments/connect`: intro copy, two `path-card`s with radio, then conditional `BrokerForm` or `ManualForm` panel with `border-top: 2px var(--app-primary)`.
- **`BrokerForm.tsx`** — repurpose `ConnectIBKRForm` content. Adds: IBKR badge header, "What you need" info block with link, base currency select, show/hide password toggle on token, "Connect & sync" CTA, "More brokers — coming soon" disabled cards (Trading 212, Degiro, Schwab).
- **`ManualForm.tsx`** — repurpose `AddManualHoldingForm`. Layout: row 1 = Account select (incl. "+ Create new account…") + Symbol search w/ live result dropdown. Row 2 = Quantity, Instrument type segmented control, Currency select, Avg cost (optional). Cancel deselects path; Submit creates holding.

### Repurposed / removed
- `HoldingsTable.tsx` → keep export but back it with `HoldingsTableHF`. Or replace usages and delete; prefer the latter (no other consumers).
- `AllocationChart.tsx` → replaced by `AllocationDonut`. Delete.
- `PortfolioSummaryCard.tsx` → unused after change. Delete.
- `ConnectIBKRForm.tsx`, `AddManualHoldingForm.tsx` → become `BrokerForm` / `ManualForm` rewrites.

## 4. Page composition

### `app/(dashboard)/investments/page.tsx`
```tsx
const [portfolio, holdings] = await Promise.all([getPortfolio(), listHoldings()]);
if (holdings.length === 0) return <InvestmentsEmpty />;
const today = new Date();
const monthAgo = new Date(today); monthAgo.setMonth(monthAgo.getMonth() - 1);
const history = await getPortfolioHistory(monthAgo.toISOString().slice(0,10), today.toISOString().slice(0,10));
return <InvestmentsOverview portfolio={portfolio} holdings={holdings} initialHistory={history} initialRange="1M" />;
```

### `app/(dashboard)/investments/connect/page.tsx`
Server component → renders `<ConnectPathPicker />` (client). Pre-loads `listInvestmentAccounts()` for the manual form's account dropdown.

## 5. Data flow

- **Range toggle**: client-side. On change, call a wrapper around `getPortfolioHistory` (move to a server action `fetchHistoryRange(range: "1W"|"1M"|"3M"|"1Y"|"ALL")` exposed from `lib/actions/investments.ts`). Cache last-fetched range to avoid refetches when toggling back. Show subtle loading on the chart only.
- **Symbol search**: existing `searchSymbols` exposed via server action. Debounce 200ms, render dropdown beneath input on focus.
- **Sort/filter**: pure client transformations of the holdings array.
- **Stale flag**: derived from `holding.is_stale` on each row + portfolio-level count.
- **"Best day"**: compute from history series (max consecutive-day positive delta).

## 6. Visual tokens

Add the **app token block** from `colors_and_type.css` (lines 34–58, 95) to `frontend/app/globals.css` under a `:root` block so `var(--app-*)` resolves. Do **not** import JetBrains Mono globally — scope the mono font + token usage to the investments pages by wrapping the page in a `data-surface="syllogic"` wrapper or by using a CSS module. Reason: avoid restyling other dashboard pages.

Pragmatic shortcut: inline token values in components (oklch literals copied from the design) instead of redefining a theme. Acceptable here because the design uses fixed values; if rolled out wider, promote to globals.

Tailwind classes for layout, raw style objects (matching the prototype) for color/typography to keep parity with the prototype's exact oklch values.

Include the Remix Icon stylesheet (`https://cdn.jsdelivr.net/npm/remixicon@4.2.0/fonts/remixicon.css`) in the dashboard layout `<head>` (via `next/font` is not applicable for icon fonts; load through `<link rel="stylesheet">` in `app/(dashboard)/layout.tsx`).

## 7. Edge cases

- `holdings.length > 0` but `portfolio.allocation_by_*` empty → show donut placeholder ("No allocation data").
- `history` empty / single point → render flat line, hide stats strip values that depend on history (Return, Best day) as `—`.
- Mixed currency: chart Y-axis label uses `portfolio.currency` symbol (€ for EUR, $ for USD, fallback prefix).
- Symbol search returns 0 → show "No matches" inside dropdown.
- Manual form submitted with `accountId === "__new__"`: prompt for new account name above symbol field (shown inline).
- IBKR form: token field defaults to password; eye toggle reveals.

## 8. Testing

- Snapshot/visual: render `InvestmentsOverview` with seeded `holdings` and `history`. Confirm sort + filter work via React Testing Library.
- Empty state: `holdings = []` → renders `InvestmentsEmpty`, both CTAs link to `/investments/connect`.
- Connect path picker: clicking a card sets selected state, shows the matching form, "Cancel" collapses it.
- Manual submit happy path: existing test in this area (if any) updated for new field IDs/labels.

## 9. File plan

```
frontend/
  app/(dashboard)/investments/page.tsx                      [edit]
  app/(dashboard)/investments/connect/page.tsx              [edit]
  app/(dashboard)/layout.tsx                                [edit — add remixicon <link>]
  app/globals.css                                           [edit — add --app-* tokens]
  components/investments/
    AllocationDonut.tsx                                     [new]
    AllocationRow.tsx                                       [new]
    BrokerForm.tsx                                          [new]
    ConnectPathPicker.tsx                                   [new]
    HoldingsTableHF.tsx                                     [new]
    InvestmentsEmpty.tsx                                    [new]
    InvestmentsOverview.tsx                                 [new]
    ManualForm.tsx                                          [new]
    PortfolioChart.tsx                                      [new]
    PortfolioHero.tsx                                       [new]
    PortfolioStatsStrip.tsx                                 [new]
    AddManualHoldingForm.tsx                                [delete]
    AllocationChart.tsx                                     [delete]
    ConnectIBKRForm.tsx                                     [delete]
    HoldingsTable.tsx                                       [delete]
    PortfolioSummaryCard.tsx                                [delete]
  lib/actions/investments.ts                                [new — server actions wrapping range fetch + symbol search]
```

## 10. Build sequence

1. Tokens + icon font load.
2. Primitives: `AllocationDonut`, `PortfolioChart`, `PortfolioHero`, `PortfolioStatsStrip`, `HoldingsTableHF`.
3. Compose `InvestmentsOverview` and the empty state.
4. Wire `/investments/page.tsx`.
5. Build `ManualForm`, `BrokerForm`, `ConnectPathPicker`.
6. Wire `/investments/connect/page.tsx`.
7. Delete old components; remove imports.
8. Manual smoke test (run dev server, log in, exercise both pages including empty state, sort/filter, range toggle, broker form, manual form).
