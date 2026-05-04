# Holding Detail Page Revamp Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the bare-bones `/investments/[holdingId]` history table with a full Syllogic-style detail page — price chart with range toggle, stats strip, edit panel for manual holdings — and add row-click navigation from the holdings table.

**Architecture:** Server component fetches holding + 1M history + portfolio in parallel, passes props to a client `HoldingDetailView` that owns range state and the edit form. No new backend endpoints; the `PATCH /holdings/{id}` endpoint already exists.

**Tech Stack:** Next.js 16 App Router, React 19, Tailwind v4 (layout only), vitest + React Testing Library, existing `lib/api/investments.ts` + `lib/actions/investments.ts` server utilities.

**Reference spec:** `docs/superpowers/specs/2026-04-25-holding-detail-revamp-design.md`

---

## Pre-flight context

- All new components go in `frontend/components/investments/` and follow the Syllogic surface pattern: wrap in `<div className="syllogic-surface">`, use inline oklch style values from `T` in `./_tokens`.
- Shared form primitives (`Field`, `Input`, `btnPrimary`, `btnGhost`) live in `frontend/components/investments/_form-bits.tsx` — import from there, do not duplicate.
- `PortfolioChart` (renders SVG area+line from `number[]`) and `TypeBadge` (type badge span) already exist and should be reused.
- Tests run with: `cd frontend && npx vitest run <path>`. All tests must pass before committing.
- `lib/api/investments.ts` has a file-level `"use server"` directive. When testing components that import it, mock the module with `vi.mock` (see Task 3).
- `lib/actions/investments.ts` uses per-function `"use server"` — mock it the same way in tests.
- The `@` alias resolves to `frontend/` (see `vitest.config.ts`).

---

## Task 1: Add `updateHolding` API function + `fetchHoldingHistoryRange` server action

**Files:**
- Modify: `frontend/lib/api/investments.ts` (add `updateHolding` after the existing `deleteHolding` function)
- Modify: `frontend/lib/actions/investments.ts` (add `fetchHoldingHistoryRange`)
- Modify: `frontend/lib/actions/investments.test.ts` (add test for new action's date range)

- [ ] **Step 1: Write the failing test**

Add to `frontend/lib/actions/investments.test.ts`:

```ts
import { describe, it, expect } from "vitest";
import { rangeToDates, fetchHoldingHistoryRange } from "./investments";

// existing tests stay — add below:

describe("fetchHoldingHistoryRange export", () => {
  it("is an async function", () => {
    expect(typeof fetchHoldingHistoryRange).toBe("function");
  });
});
```

- [ ] **Step 2: Run — expect fail**

```bash
cd frontend && npx vitest run lib/actions/investments.test
```

Expected: FAIL — `fetchHoldingHistoryRange` not exported.

- [ ] **Step 3: Add `fetchHoldingHistoryRange` to `frontend/lib/actions/investments.ts`**

Append after the existing `searchSymbolsAction`:

```ts
export async function fetchHoldingHistoryRange(holdingId: string, range: Range) {
  "use server";
  const { getHoldingHistory } = await import("@/lib/api/investments");
  const { from, to } = rangeToDates(range);
  return getHoldingHistory(holdingId, from, to);
}
```

- [ ] **Step 4: Add `updateHolding` to `frontend/lib/api/investments.ts`**

Append after the existing `deleteHolding` function (around line 200):

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

- [ ] **Step 5: Run — expect pass**

```bash
cd frontend && npx vitest run lib/actions/investments.test
```

Expected: PASS (4 tests total).

- [ ] **Step 6: Commit**

```bash
git add frontend/lib/api/investments.ts frontend/lib/actions/investments.ts frontend/lib/actions/investments.test.ts
git commit -m "feat(investments): updateHolding API + fetchHoldingHistoryRange action"
```

---

## Task 2: Make `HoldingsTableHF` rows clickable

**Files:**
- Modify: `frontend/components/investments/HoldingsTableHF.tsx`
- Modify: `frontend/components/investments/HoldingsTableHF.test.tsx` (add click navigation test)

- [ ] **Step 1: Write the failing test**

Add to `frontend/components/investments/HoldingsTableHF.test.tsx`:

```tsx
import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";

// Add at top of file, after existing imports:
const mockPush = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ push: mockPush, refresh: vi.fn() }) }));

// Add as a new describe block (keep existing tests):
describe("HoldingsTableHF row navigation", () => {
  it("navigates to holding detail on row click", () => {
    render(
      <HoldingsTableHF
        holdings={H}
        accountNames={{ a: "Acct" }}
        accountsCount={1}
      />,
    );
    fireEvent.click(screen.getByText("VUAA"));
    expect(mockPush).toHaveBeenCalledWith("/investments/1");
  });

  it("does not navigate when delete button clicked", () => {
    mockPush.mockClear();
    const onDelete = vi.fn();
    render(
      <HoldingsTableHF
        holdings={H}
        accountNames={{ a: "Acct" }}
        accountsCount={1}
        onDelete={onDelete}
      />,
    );
    fireEvent.click(screen.getByTitle("Delete"));
    expect(onDelete).toHaveBeenCalledWith("2");
    expect(mockPush).not.toHaveBeenCalled();
  });
});
```

- [ ] **Step 2: Run — expect fail**

```bash
cd frontend && npx vitest run components/investments/HoldingsTableHF.test
```

Expected: FAIL — `mockPush` not called / navigation not wired.

- [ ] **Step 3: Update `HoldingsTableHF.tsx`**

Add `useRouter` import at the top:

```tsx
import { useRouter } from "next/navigation";
```

Inside the `HoldingsTableHF` function body, add after the existing state declarations:

```tsx
const router = useRouter();
```

Replace the `<tr>` opening tag in the `rows.map` (currently around line 220):

```tsx
<tr
  key={h.id}
  className={h.is_stale ? "stale" : ""}
  onClick={() => router.push(`/investments/${h.id}`)}
  style={{
    borderBottom: `1px solid ${T.muted}`,
    background: h.is_stale ? T.staleBg : undefined,
    cursor: "pointer",
  }}
>
```

Add `e.stopPropagation()` to the delete button's onClick (currently around line 302):

```tsx
onClick={(e) => { e.stopPropagation(); onDelete(h.id); }}
```

- [ ] **Step 4: Run — expect pass**

```bash
cd frontend && npx vitest run components/investments/HoldingsTableHF.test
```

Expected: PASS (4 tests total).

- [ ] **Step 5: Commit**

```bash
git add frontend/components/investments/HoldingsTableHF.tsx frontend/components/investments/HoldingsTableHF.test.tsx
git commit -m "feat(investments): clickable holdings rows → detail page"
```

---

## Task 3: Build `HoldingDetailView` client component

**Files:**
- Create: `frontend/components/investments/HoldingDetailView.tsx`
- Create: `frontend/components/investments/HoldingDetailView.test.tsx`

- [ ] **Step 1: Write the failing tests**

Create `frontend/components/investments/HoldingDetailView.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import { HoldingDetailView } from "./HoldingDetailView";
import type { Holding, PortfolioSummary, ValuationPoint } from "@/lib/api/investments";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), refresh: vi.fn() }),
}));
vi.mock("@/lib/actions/investments", () => ({
  fetchHoldingHistoryRange: vi.fn().mockResolvedValue([]),
}));
vi.mock("@/lib/api/investments", () => ({
  updateHolding: vi.fn(),
}));

const MANUAL_HOLDING: Holding = {
  id: "h1",
  account_id: "a1",
  symbol: "VUAA",
  name: "Vanguard S&P 500 UCITS ETF",
  currency: "USD",
  instrument_type: "etf",
  quantity: "100",
  avg_cost: "87.55",
  as_of_date: null,
  source: "manual",
  current_price: "98.42",
  current_value_user_currency: "9842",
  is_stale: false,
};

const IBKR_HOLDING: Holding = {
  ...MANUAL_HOLDING,
  id: "h2",
  source: "ibkr_flex",
};

const NO_COST_HOLDING: Holding = {
  ...MANUAL_HOLDING,
  id: "h3",
  avg_cost: null,
};

const PORTFOLIO: PortfolioSummary = {
  total_value: "50000",
  total_value_today_change: "100",
  currency: "EUR",
  accounts: [{ id: "a1", name: "My Account", balance: "9842", type: "manual" }],
  allocation_by_type: {},
  allocation_by_currency: {},
};

const HISTORY: ValuationPoint[] = [
  { date: "2026-03-25", value: "9500" },
  { date: "2026-04-25", value: "9842" },
];

describe("HoldingDetailView", () => {
  it("renders edit panel for manual holding", () => {
    render(
      <HoldingDetailView
        holding={MANUAL_HOLDING}
        portfolio={PORTFOLIO}
        initialHistory={HISTORY}
      />,
    );
    expect(screen.getByText("Edit holding")).toBeTruthy();
    expect(screen.getByRole("button", { name: /save changes/i })).toBeTruthy();
  });

  it("hides edit panel for IBKR holding", () => {
    render(
      <HoldingDetailView
        holding={IBKR_HOLDING}
        portfolio={PORTFOLIO}
        initialHistory={HISTORY}
      />,
    );
    expect(screen.queryByText("Edit holding")).toBeNull();
  });

  it("shows — for total return when avg_cost is null", () => {
    render(
      <HoldingDetailView
        holding={NO_COST_HOLDING}
        portfolio={PORTFOLIO}
        initialHistory={HISTORY}
      />,
    );
    // Stats strip has multiple cells — find the Total return cell
    const cells = screen.getAllByText("—");
    expect(cells.length).toBeGreaterThanOrEqual(1);
  });

  it("shows symbol and account name in header", () => {
    render(
      <HoldingDetailView
        holding={MANUAL_HOLDING}
        portfolio={PORTFOLIO}
        initialHistory={HISTORY}
      />,
    );
    expect(screen.getByText("VUAA")).toBeTruthy();
    expect(screen.getByText("My Account")).toBeTruthy();
  });
});
```

- [ ] **Step 2: Run — expect fail**

```bash
cd frontend && npx vitest run components/investments/HoldingDetailView.test
```

Expected: FAIL — module not found.

- [ ] **Step 3: Implement `HoldingDetailView.tsx`**

Create `frontend/components/investments/HoldingDetailView.tsx`:

```tsx
"use client";
import { useState, useTransition } from "react";
import { useRouter } from "next/navigation";
import { fetchHoldingHistoryRange, type Range } from "@/lib/actions/investments";
import {
  updateHolding,
  type Holding,
  type PortfolioSummary,
  type ValuationPoint,
} from "@/lib/api/investments";
import { PortfolioChart } from "./PortfolioChart";
import { TypeBadge } from "./HoldingsTableHF";
import { T } from "./_tokens";
import { Field, Input, btnPrimary } from "./_form-bits";

const RANGES: Range[] = ["1W", "1M", "3M", "1Y", "ALL"];

function currSym(currency: string) {
  return currency === "USD" ? "$" : currency === "GBP" ? "£" : "€";
}

function fmt(n: number, digits = 2) {
  return n.toLocaleString("en", {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });
}

export function HoldingDetailView({
  holding,
  portfolio,
  initialHistory,
}: {
  holding: Holding;
  portfolio: PortfolioSummary;
  initialHistory: ValuationPoint[];
}) {
  const router = useRouter();
  const [range, setRange] = useState<Range>("1M");
  const [history, setHistory] = useState<ValuationPoint[]>(initialHistory);
  const [pending, startTransition] = useTransition();

  const [qty, setQty] = useState(holding.quantity);
  const [avgCost, setAvgCost] = useState(holding.avg_cost ?? "");
  const [asOfDate, setAsOfDate] = useState(holding.as_of_date ?? "");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const series = history
    .map((p) => Number(p.value))
    .filter((v) => Number.isFinite(v));

  const portfolioCurrSym = currSym(portfolio.currency);
  const holdingCurrSym = currSym(holding.currency);
  const marketValue = Number(holding.current_value_user_currency ?? 0);
  const totalValue = Number(portfolio.total_value);
  const weight = totalValue > 0 ? (marketValue / totalValue) * 100 : 0;
  const costBasis =
    holding.avg_cost != null
      ? Number(holding.avg_cost) * Number(holding.quantity)
      : null;
  const totalReturn =
    costBasis != null && costBasis > 0
      ? ((marketValue - costBasis) / costBasis) * 100
      : null;

  const accountName =
    portfolio.accounts.find((a) => a.id === holding.account_id)?.name ??
    holding.account_id;

  const onRangeChange = (r: Range) => {
    setRange(r);
    startTransition(async () => {
      const next = await fetchHoldingHistoryRange(holding.id, r);
      setHistory(next);
    });
  };

  const onSave = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setErr(null);
    try {
      await updateHolding(holding.id, {
        quantity: qty,
        ...(avgCost ? { avg_cost: avgCost } : {}),
        ...(asOfDate ? { as_of_date: asOfDate } : {}),
      });
      router.refresh();
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const statCells: [string, string][] = [
    [
      "Current price",
      holding.current_price
        ? `${holdingCurrSym} ${fmt(Number(holding.current_price))}`
        : "—",
    ],
    ["Market value", `${portfolioCurrSym} ${fmt(marketValue)}`],
    [
      "Total return",
      totalReturn != null
        ? `${totalReturn >= 0 ? "▲ +" : "▼ "}${fmt(totalReturn)}%`
        : "—",
    ],
    [
      "Avg cost / share",
      holding.avg_cost
        ? `${holdingCurrSym} ${fmt(Number(holding.avg_cost))}`
        : "—",
    ],
    ["Portfolio weight", `${fmt(weight, 1)}%`],
  ];

  return (
    <div className="syllogic-surface" style={{ flex: 1, overflow: "auto" }}>
      <div
        style={{
          padding: 24,
          display: "flex",
          flexDirection: "column",
          gap: 16,
        }}
      >
        {/* Back */}
        <button
          onClick={() => router.push("/investments")}
          style={{
            alignSelf: "flex-start",
            background: "none",
            border: "none",
            cursor: "pointer",
            color: T.mutedFg,
            fontSize: 12,
            padding: 0,
            fontFamily: "inherit",
            display: "flex",
            alignItems: "center",
            gap: 4,
          }}
        >
          ← All holdings
        </button>

        {/* Header */}
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: 10,
            flexWrap: "wrap",
          }}
        >
          <span
            style={{
              fontSize: 26,
              fontWeight: 700,
              letterSpacing: "-0.02em",
            }}
          >
            {holding.symbol}
          </span>
          <TypeBadge type={holding.instrument_type} />
          <span style={{ color: T.mutedFg, fontSize: 13 }}>
            {holding.name ?? ""}
          </span>
          {holding.is_stale && (
            <span
              title="Price may be stale"
              style={{
                width: 8,
                height: 8,
                background: T.stale,
                borderRadius: "50%",
              }}
            />
          )}
          <span
            style={{
              marginLeft: "auto",
              padding: "2px 8px",
              border: `1px solid ${T.border}`,
              fontSize: 11,
              color: T.mutedFg,
              background: T.muted,
            }}
          >
            {accountName}
          </span>
        </div>

        {/* Stats strip */}
        <div
          style={{ display: "flex", gap: 0, border: `1px solid ${T.border}` }}
        >
          {statCells.map(([label, val], i) => (
            <div
              key={label}
              style={{
                flex: 1,
                padding: "12px 16px",
                borderRight:
                  i < statCells.length - 1
                    ? `1px solid ${T.border}`
                    : "none",
                display: "flex",
                flexDirection: "column",
                gap: 4,
              }}
            >
              <div
                style={{
                  fontSize: 10,
                  color: T.mutedFg,
                  textTransform: "uppercase",
                  letterSpacing: ".08em",
                }}
              >
                {label}
              </div>
              <div
                style={{
                  fontSize: 13,
                  fontWeight: 600,
                  fontVariantNumeric: "tabular-nums",
                }}
              >
                {val}
              </div>
            </div>
          ))}
        </div>

        {/* Chart card */}
        <div
          style={{
            background: T.card,
            border: `1px solid ${T.border}`,
            opacity: pending ? 0.7 : 1,
            transition: "opacity 120ms",
          }}
        >
          <div
            style={{
              display: "flex",
              justifyContent: "flex-end",
              padding: "12px 16px 0",
            }}
          >
            {RANGES.map((r) => {
              const active = range === r;
              return (
                <button
                  key={r}
                  onClick={() => onRangeChange(r)}
                  style={{
                    padding: "4px 10px",
                    fontSize: 11,
                    fontFamily: "inherit",
                    border: `1px solid ${active ? T.primary : T.border}`,
                    background: active ? T.primary : T.card,
                    color: active ? T.primaryFg : T.mutedFg,
                    cursor: "pointer",
                    marginLeft: -1,
                  }}
                >
                  {r}
                </button>
              );
            })}
          </div>
          <div style={{ padding: "8px 16px 16px" }}>
            <PortfolioChart data={series} currencySymbol={portfolioCurrSym} />
          </div>
        </div>

        {/* Edit panel — manual holdings only */}
        {holding.source === "manual" && (
          <form
            onSubmit={onSave}
            style={{
              borderTop: `2px solid ${T.primary}`,
              background: T.card,
              border: `1px solid ${T.border}`,
              padding: 24,
            }}
          >
            <div style={{ fontWeight: 600, fontSize: 13, marginBottom: 18 }}>
              Edit holding
            </div>
            <div style={{ display: "flex", gap: 14, flexWrap: "wrap" }}>
              <Field label="Quantity" flex={1}>
                <Input
                  type="number"
                  value={qty}
                  onChange={(e) => setQty(e.target.value)}
                  required
                />
              </Field>
              <Field
                label={
                  <>
                    Avg cost{" "}
                    <span style={{ fontWeight: 400, color: T.mutedFg }}>
                      (optional)
                    </span>
                  </>
                }
                flex={1}
              >
                <Input
                  type="number"
                  value={avgCost}
                  onChange={(e) => setAvgCost(e.target.value)}
                  placeholder="—"
                />
              </Field>
              <Field
                label={
                  <>
                    As of date{" "}
                    <span style={{ fontWeight: 400, color: T.mutedFg }}>
                      (optional)
                    </span>
                  </>
                }
                flex={1}
              >
                <Input
                  type="date"
                  value={asOfDate}
                  onChange={(e) => setAsOfDate(e.target.value)}
                />
              </Field>
            </div>
            {err && (
              <div style={{ color: T.negative, fontSize: 11, marginTop: 12 }}>
                {err}
              </div>
            )}
            <div
              style={{
                display: "flex",
                justifyContent: "flex-end",
                marginTop: 16,
              }}
            >
              <button type="submit" disabled={busy} style={btnPrimary}>
                {busy ? "Saving…" : "Save changes"}
              </button>
            </div>
          </form>
        )}
      </div>
    </div>
  );
}
```

- [ ] **Step 4: Run — expect pass**

```bash
cd frontend && npx vitest run components/investments/HoldingDetailView.test
```

Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add frontend/components/investments/HoldingDetailView.tsx frontend/components/investments/HoldingDetailView.test.tsx
git commit -m "feat(investments): HoldingDetailView — chart, stats, edit panel"
```

---

## Task 4: Rewrite `/investments/[holdingId]/page.tsx`

**Files:**
- Modify: `frontend/app/(dashboard)/investments/[holdingId]/page.tsx` (full rewrite)

- [ ] **Step 1: Rewrite the page**

Replace entire contents of `frontend/app/(dashboard)/investments/[holdingId]/page.tsx`:

```tsx
import { notFound } from "next/navigation";
import {
  listHoldings,
  getHoldingHistory,
  getPortfolio,
} from "@/lib/api/investments";
import { HoldingDetailView } from "@/components/investments/HoldingDetailView";
import { rangeToDates } from "@/lib/actions/investments";

export const dynamic = "force-dynamic";

export default async function HoldingDetailPage({
  params,
}: {
  params: Promise<{ holdingId: string }>;
}) {
  const { holdingId } = await params;
  const { from, to } = rangeToDates("1M");
  const [holdings, history, portfolio] = await Promise.all([
    listHoldings(),
    getHoldingHistory(holdingId, from, to),
    getPortfolio(),
  ]);
  const holding = holdings.find((h) => h.id === holdingId);
  if (!holding) notFound();
  return (
    <HoldingDetailView
      holding={holding}
      portfolio={portfolio}
      initialHistory={history}
    />
  );
}
```

- [ ] **Step 2: Run full test suite**

```bash
cd frontend && npx vitest run
```

Expected: all tests pass (previously 69; now 69 + 4 new HoldingDetailView + 1 new action = 74+ passing).

- [ ] **Step 3: Commit**

```bash
git add "frontend/app/(dashboard)/investments/[holdingId]/page.tsx"
git commit -m "feat(investments): wire holding detail page"
```

---

## Task 5: Smoke test

- [ ] **Step 1: Start dev server**

```bash
cd frontend && pnpm dev
```

- [ ] **Step 2: Manual checks**

1. Go to `/investments`. Click any row in the holdings table → should navigate to `/investments/<id>`.
2. Detail page shows: back link, symbol header, type badge, account badge, 5-cell stats strip, chart (with "Not enough history" if empty), range toggle buttons.
3. Toggle range 1W → 1Y → ALL. Chart opacity dims briefly then updates.
4. For a **manual** holding: edit panel is visible. Change quantity, click "Save changes" → page refreshes with new value.
5. For an **IBKR** holding: edit panel is absent.
6. Clicking "← All holdings" navigates back to `/investments`.
7. Click the delete button (kebab) in the holdings table row — confirms deletion without also navigating to the detail page.

- [ ] **Step 3: Run lint**

```bash
cd frontend && pnpm lint
```

Expected: 0 errors (pre-existing warnings are acceptable).
