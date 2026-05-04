# Investments Revamp Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the Syllogic high-fidelity timeline-first `/investments` page (with empty state) and path-picker `/investments/connect` page from the Claude Design handoff.

**Architecture:** Server components fetch portfolio + holdings + 1M history; an interactive client subtree handles range toggling, sort/filter, and the path-picker forms. Visual styling uses inline oklch values from the prototype + JetBrains Mono scoped to the investments surface (no global theme change).

**Tech Stack:** Next.js 16 (App Router) + React 19, Tailwind v4, `@remixicon/react`, vitest + React Testing Library, existing `lib/api/investments.ts` server actions. No new backend.

**Reference spec:** `docs/superpowers/specs/2026-04-25-investments-revamp-design.md`
**Design source:** `Investments.html` from the handoff bundle (read it for exact values).

---

## Pre-flight

- Existing API surface in `frontend/lib/api/investments.ts`: `getPortfolio`, `listHoldings`, `getPortfolioHistory`, `searchSymbols`, `createBrokerConnection`, `createManualAccount`, `addManualHolding`, `listInvestmentAccounts`, `deleteHolding`. No new endpoints needed.
- Tests use vitest. Add React Testing Library if not present (check first; if missing, install `@testing-library/react @testing-library/jest-dom jsdom` and configure).
- Tailwind v4 is in use; tokens go via `@theme` in `app/globals.css`, but per the spec we keep them scoped — see Task 1.
- All new components live in `frontend/components/investments/`.

---

## Task 1: Add JetBrains Mono font + scoped surface class

**Files:**
- Modify: `frontend/app/(dashboard)/investments/page.tsx` (will use later)
- Modify: `frontend/app/globals.css`
- Create: `frontend/components/investments/_tokens.ts` (color constants used inline)

- [ ] **Step 1: Add JetBrains Mono via `next/font`**

In `frontend/app/(dashboard)/layout.tsx` add at top:

```tsx
import { JetBrains_Mono } from "next/font/google";
const jbMono = JetBrains_Mono({ subsets: ["latin"], variable: "--font-jb-mono", weight: ["400","500","600","700"] });
```

Apply class to the `<SidebarInset>` wrapper change: replace `<SidebarInset>{children}</SidebarInset>` with `<SidebarInset className={jbMono.variable}>{children}</SidebarInset>`.

- [ ] **Step 2: Add a `.syllogic-surface` utility to `globals.css`**

Append to `frontend/app/globals.css`:

```css
.syllogic-surface {
  font-family: var(--font-jb-mono), ui-monospace, SFMono-Regular, Menlo, Monaco, monospace;
  --app-background: oklch(1 0 0);
  --app-foreground: oklch(0.147 0.004 49.25);
  --app-card: oklch(1 0 0);
  --app-primary: oklch(0.216 0.006 56.043);
  --app-primary-foreground: oklch(0.985 0.001 106.423);
  --app-muted: oklch(0.97 0.001 106.424);
  --app-muted-foreground: oklch(0.553 0.013 58.071);
  --app-border: oklch(0.923 0.003 48.717);
  --app-positive: oklch(0.52 0.13 150);
  --app-negative: oklch(0.577 0.245 27.325);
  --app-stale: oklch(0.75 0.12 70);
  --app-stale-bg: oklch(0.99 0.016 80);
  --app-stale-border: oklch(0.85 0.08 80);
  background: oklch(0.985 0.001 106.423);
  color: var(--app-foreground);
}
.syllogic-surface * { box-sizing: border-box; }
```

- [ ] **Step 3: Create `_tokens.ts`**

```ts
// frontend/components/investments/_tokens.ts
export const T = {
  bg: "oklch(0.985 0.001 106.423)",
  fg: "oklch(0.147 0.004 49.25)",
  card: "oklch(1 0 0)",
  primary: "oklch(0.216 0.006 56.043)",
  primaryFg: "oklch(0.985 0.001 106.423)",
  muted: "oklch(0.97 0.001 106.424)",
  mutedFg: "oklch(0.553 0.013 58.071)",
  border: "oklch(0.923 0.003 48.717)",
  positive: "oklch(0.52 0.13 150)",
  negative: "oklch(0.577 0.245 27.325)",
  stale: "oklch(0.75 0.12 70)",
  staleBg: "oklch(0.99 0.016 80)",
  staleBorder: "oklch(0.85 0.08 80)",
  chart1: "oklch(0.145 0 0)",
  chart2: "oklch(0.553 0 0)",
  chart3: "oklch(0.869 0 0)",
} as const;
```

- [ ] **Step 4: Commit**

```bash
git add frontend/app/(dashboard)/layout.tsx frontend/app/globals.css frontend/components/investments/_tokens.ts
git commit -m "feat(investments): scoped Syllogic surface tokens + JB Mono font"
```

---

## Task 2: Server actions wrapper

**Files:**
- Create: `frontend/lib/actions/investments.ts`
- Test: `frontend/lib/actions/investments.test.ts`

- [ ] **Step 1: Write the failing test**

```ts
// frontend/lib/actions/investments.test.ts
import { describe, it, expect } from "vitest";
import { rangeToDates } from "./investments";

describe("rangeToDates", () => {
  const ref = new Date("2026-04-25T00:00:00Z");
  it("1W spans 7 days", () => {
    const { from, to } = rangeToDates("1W", ref);
    expect(to).toBe("2026-04-25");
    expect(from).toBe("2026-04-18");
  });
  it("1M spans 30 days", () => {
    expect(rangeToDates("1M", ref).from).toBe("2026-03-26");
  });
  it("ALL uses a far-back date", () => {
    expect(rangeToDates("ALL", ref).from).toBe("2010-01-01");
  });
});
```

- [ ] **Step 2: Run test — expect fail**

```
cd frontend && npx vitest run lib/actions/investments.test.ts
```
Expected: FAIL — module not found.

- [ ] **Step 3: Implement**

```ts
// frontend/lib/actions/investments.ts
"use server";
import { getPortfolioHistory, searchSymbols } from "@/lib/api/investments";

export type Range = "1W" | "1M" | "3M" | "1Y" | "ALL";

export function rangeToDates(range: Range, now: Date = new Date()) {
  const to = now.toISOString().slice(0, 10);
  if (range === "ALL") return { from: "2010-01-01", to };
  const days = { "1W": 7, "1M": 30, "3M": 90, "1Y": 365 }[range];
  const d = new Date(now);
  d.setUTCDate(d.getUTCDate() - days);
  return { from: d.toISOString().slice(0, 10), to };
}

export async function fetchHistoryRange(range: Range) {
  const { from, to } = rangeToDates(range);
  return getPortfolioHistory(from, to);
}

export async function searchSymbolsAction(q: string) {
  if (!q.trim()) return [];
  return searchSymbols(q);
}
```

- [ ] **Step 4: Run — expect pass**

- [ ] **Step 5: Commit**

```bash
git add frontend/lib/actions/investments.ts frontend/lib/actions/investments.test.ts
git commit -m "feat(investments): range + symbol-search server actions"
```

---

## Task 3: `AllocationDonut` component

**Files:**
- Create: `frontend/components/investments/AllocationDonut.tsx`
- Test: `frontend/components/investments/AllocationDonut.test.tsx`

- [ ] **Step 1: Write the failing test**

```tsx
import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import { AllocationDonut } from "./AllocationDonut";

describe("AllocationDonut", () => {
  it("renders one circle per segment + a track", () => {
    const { container } = render(
      <AllocationDonut segments={[{ label:"ETF", pct:60, color:"#000" }, { label:"Cash", pct:40, color:"#888" }]} />
    );
    expect(container.querySelectorAll("circle").length).toBe(3); // track + 2 segments
  });
});
```

- [ ] **Step 2: Run — expect fail.**

- [ ] **Step 3: Implement**

```tsx
// frontend/components/investments/AllocationDonut.tsx
import { T } from "./_tokens";
export type DonutSegment = { label: string; pct: number; color: string };

export function AllocationDonut({ segments, size = 72 }: { segments: DonutSegment[]; size?: number }) {
  const r = 28, cx = 40, cy = 40, C = 2 * Math.PI * r;
  let acc = 0;
  return (
    <svg width={size} height={size} viewBox="0 0 80 80">
      <circle cx={cx} cy={cy} r={r} fill="none" stroke={T.border} strokeWidth="12" />
      {segments.map((s, i) => {
        const dash = (s.pct / 100) * C;
        const offset = -(acc / 100) * C;
        acc += s.pct;
        return (
          <circle key={i} cx={cx} cy={cy} r={r} fill="none"
            stroke={s.color} strokeWidth="12"
            strokeDasharray={`${dash} ${C}`} strokeDashoffset={offset}
            transform="rotate(-90 40 40)" />
        );
      })}
    </svg>
  );
}
```

- [ ] **Step 4: Run — expect pass.**

- [ ] **Step 5: Commit**

```bash
git add frontend/components/investments/AllocationDonut.tsx frontend/components/investments/AllocationDonut.test.tsx
git commit -m "feat(investments): AllocationDonut primitive"
```

---

## Task 4: `AllocationRow` (two donuts + legends)

**Files:**
- Create: `frontend/components/investments/AllocationRow.tsx`

- [ ] **Step 1: Implement (no tests — pure presentational)**

```tsx
// frontend/components/investments/AllocationRow.tsx
import { AllocationDonut, type DonutSegment } from "./AllocationDonut";
import { T } from "./_tokens";

const PALETTE = [T.chart1, T.chart2, T.chart3];

function toSegments(data: Record<string, string | number>): DonutSegment[] {
  const entries = Object.entries(data);
  const total = entries.reduce((s, [, v]) => s + Number(v), 0) || 1;
  return entries.map(([label, v], i) => ({
    label,
    pct: Math.round((Number(v) / total) * 100),
    color: PALETTE[i % PALETTE.length],
  }));
}

export function AllocationRow({
  byInstrument, byCurrency,
}: { byInstrument: Record<string, string>; byCurrency: Record<string, string> }) {
  const groups = [
    { title: "By instrument", segs: toSegments(byInstrument) },
    { title: "By currency", segs: toSegments(byCurrency) },
  ];
  return (
    <div style={{ display:"grid", gridTemplateColumns:"1fr 1fr", gap:12 }}>
      {groups.map((g, gi) => (
        <div key={gi} style={{ background:T.card, border:`1px solid ${T.border}`, padding:18, display:"flex", gap:20, alignItems:"center" }}>
          <AllocationDonut segments={g.segs} size={72} />
          <div style={{ flex:1 }}>
            <div style={{ fontSize:11, fontWeight:600, marginBottom:10 }}>{g.title}</div>
            <div style={{ display:"flex", flexDirection:"column", gap:5 }}>
              {g.segs.map((s, i) => (
                <div key={i} style={{ display:"flex", alignItems:"center", gap:8, fontSize:11 }}>
                  <span style={{ width:8, height:8, background:s.color, flexShrink:0 }} />
                  <span style={{ flex:1, color:T.mutedFg }}>{s.label}</span>
                  <span style={{ fontWeight:600, fontVariantNumeric:"tabular-nums" }}>{s.pct}%</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/components/investments/AllocationRow.tsx
git commit -m "feat(investments): AllocationRow with paired donuts"
```

---

## Task 5: `PortfolioChart`

**Files:**
- Create: `frontend/components/investments/PortfolioChart.tsx`

- [ ] **Step 1: Implement**

Translate `PortfolioChart` from `Investments.html` lines 102–169. Replace hardcoded `now` with a prop. Replace euro symbol with prop `currencySymbol`. Keep SVG markup identical.

```tsx
// frontend/components/investments/PortfolioChart.tsx
"use client";
import { T } from "./_tokens";

export function PortfolioChart({ data, currencySymbol = "€" }: { data: number[]; currencySymbol?: string }) {
  if (data.length < 2) {
    return <div style={{ height:180, display:"flex", alignItems:"center", justifyContent:"center", color:T.mutedFg, fontSize:12 }}>Not enough history</div>;
  }
  const min = Math.min(...data), max = Math.max(...data);
  const pad = (max - min) * 0.12 || 1;
  const lo = min - pad, hi = max + pad;
  const W = 800, H = 160;
  const toY = (v: number) => H - ((v - lo) / (hi - lo)) * H;
  const toX = (i: number, len: number) => (i / (len - 1)) * W;
  const pts = data.map((v, i) => [toX(i, data.length), toY(v)] as const);
  const linePath = pts.map((p, i) => `${i===0?"M":"L"}${p[0].toFixed(1)},${p[1].toFixed(1)}`).join(" ");
  const areaPath = `${linePath} L${W},${H} L0,${H} Z`;
  const yTicks = [0.25, 0.5, 0.75].map(f => lo + (hi - lo) * f);
  const lastX = toX(data.length - 1, data.length);
  const lastY = toY(data[data.length - 1]);

  return (
    <svg viewBox={`-44 -4 ${W + 52} ${H + 24}`} style={{ width:"100%", height:180, display:"block" }} preserveAspectRatio="none">
      <defs>
        <linearGradient id="invAreaGrad" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={T.primary} stopOpacity="0.12" />
          <stop offset="100%" stopColor={T.primary} stopOpacity="0" />
        </linearGradient>
      </defs>
      {yTicks.map((v, i) => <line key={i} x1="0" y1={toY(v)} x2={W} y2={toY(v)} stroke={T.border} strokeWidth="1" />)}
      {yTicks.map((v, i) => (
        <text key={i} x="-6" y={toY(v) + 4} textAnchor="end" fontSize="9" style={{ fill:T.mutedFg }}>
          {v >= 1000 ? `${currencySymbol}${(v/1000).toFixed(0)}k` : `${currencySymbol}${v.toFixed(0)}`}
        </text>
      ))}
      <path d={areaPath} fill="url(#invAreaGrad)" />
      <path d={linePath} fill="none" stroke={T.primary} strokeWidth="1.5" strokeLinecap="square" strokeLinejoin="miter" />
      <circle cx={lastX} cy={lastY} r="3.5" fill={T.primary} />
      <circle cx={lastX} cy={lastY} r="6" fill={T.primary} fillOpacity="0.2" />
    </svg>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/components/investments/PortfolioChart.tsx
git commit -m "feat(investments): PortfolioChart SVG area+line"
```

---

## Task 6: `PortfolioHero` with range toggle

**Files:**
- Create: `frontend/components/investments/PortfolioHero.tsx`

- [ ] **Step 1: Implement**

```tsx
// frontend/components/investments/PortfolioHero.tsx
"use client";
import { RiAlertLine } from "@remixicon/react";
import { T } from "./_tokens";
import type { Range } from "@/lib/actions/investments";

const RANGES: Range[] = ["1W","1M","3M","1Y","ALL"];

export function PortfolioHero({
  totalValue, currency, absChange, pctChange, range, onRangeChange, asOf, staleCount,
}: {
  totalValue: number; currency: string; absChange: number; pctChange: number;
  range: Range; onRangeChange: (r: Range) => void; asOf?: string; staleCount: number;
}) {
  const positive = absChange >= 0;
  const sym = currency === "USD" ? "$" : currency === "GBP" ? "£" : "€";
  const rangeLabel = { "1W":"this week","1M":"this month","3M":"this 3 months","1Y":"this year","ALL":"all time" }[range];
  return (
    <div style={{ display:"flex", alignItems:"flex-end", gap:0, flexWrap:"wrap" }}>
      <div style={{ flex:1, minWidth:260 }}>
        <div style={{ fontSize:11, color:T.mutedFg, letterSpacing:".08em", textTransform:"uppercase", marginBottom:6 }}>Portfolio value</div>
        <div style={{ fontSize:32, fontWeight:700, letterSpacing:"-0.025em", fontVariantNumeric:"tabular-nums", lineHeight:1 }}>
          {sym} {totalValue.toLocaleString("en",{minimumFractionDigits:2, maximumFractionDigits:2})}
        </div>
        <div style={{ display:"flex", alignItems:"center", gap:10, marginTop:8, flexWrap:"wrap" }}>
          <span style={{ fontSize:13, fontWeight:600, color: positive ? T.positive : T.negative, fontVariantNumeric:"tabular-nums" }}>
            {positive ? "▲" : "▼"} {positive ? "+" : "-"}{sym} {Math.abs(absChange).toLocaleString("en",{minimumFractionDigits:2,maximumFractionDigits:2})} ({positive?"+":""}{pctChange.toFixed(2)}%)
          </span>
          <span style={{ fontSize:11, color:T.mutedFg }}>{rangeLabel}</span>
          {asOf && <><span style={{ fontSize:11, color:T.mutedFg }}>·</span><span style={{ fontSize:11, color:T.mutedFg }}>as of {asOf}</span></>}
          {staleCount > 0 && (
            <span style={{ display:"inline-flex", alignItems:"center", gap:4, padding:"2px 8px", background:T.staleBg, border:`1px solid ${T.staleBorder}`, fontSize:10, color:"oklch(0.6 0.1 70)" }}>
              <RiAlertLine size={10} /> {staleCount} stale price{staleCount > 1 ? "s" : ""}
            </span>
          )}
        </div>
      </div>
      <div style={{ display:"flex", gap:0, alignSelf:"flex-end" }}>
        {RANGES.map(r => {
          const active = range === r;
          return (
            <button key={r} onClick={() => onRangeChange(r)}
              style={{
                padding:"4px 10px", fontSize:11, fontFamily:"inherit",
                border:`1px solid ${active ? T.primary : T.border}`,
                background: active ? T.primary : T.card,
                color: active ? T.primaryFg : T.mutedFg,
                cursor:"pointer", marginLeft:-1, position:active?"relative":"static", zIndex:active?1:0,
              }}>{r}</button>
          );
        })}
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/components/investments/PortfolioHero.tsx
git commit -m "feat(investments): PortfolioHero with range toggle"
```

---

## Task 7: `PortfolioStatsStrip`

**Files:**
- Create: `frontend/components/investments/PortfolioStatsStrip.tsx`
- Test: `frontend/components/investments/PortfolioStatsStrip.test.tsx`

- [ ] **Step 1: Write the failing test**

```tsx
import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import { PortfolioStatsStrip, computeBestDay } from "./PortfolioStatsStrip";

describe("computeBestDay", () => {
  it("returns the largest single-day positive delta", () => {
    expect(computeBestDay([100, 90, 130, 120, 200])).toEqual({ delta: 80, index: 4 });
  });
  it("returns null for flat or empty series", () => {
    expect(computeBestDay([])).toBeNull();
    expect(computeBestDay([100])).toBeNull();
  });
});
```

- [ ] **Step 2: Run — expect fail.**

- [ ] **Step 3: Implement**

```tsx
// frontend/components/investments/PortfolioStatsStrip.tsx
import { T } from "./_tokens";

export function computeBestDay(series: number[]): { delta: number; index: number } | null {
  if (series.length < 2) return null;
  let best = { delta: -Infinity, index: -1 };
  for (let i = 1; i < series.length; i++) {
    const d = series[i] - series[i - 1];
    if (d > best.delta) best = { delta: d, index: i };
  }
  return best.delta > 0 ? best : null;
}

export function PortfolioStatsStrip({
  costBasis, unrealizedPnl, returnPct, holdingsCount, accountsCount, bestDay, currencySymbol = "€",
}: {
  costBasis: number; unrealizedPnl: number; returnPct: number;
  holdingsCount: number; accountsCount: number;
  bestDay: { delta: number; label: string } | null;
  currencySymbol?: string;
}) {
  const cells: [string, string][] = [
    ["Cost basis", `${currencySymbol} ${costBasis.toLocaleString("en",{minimumFractionDigits:2,maximumFractionDigits:2})}`],
    ["Unrealized P&L", `${unrealizedPnl >= 0 ? "▲ +" : "▼ -"}${currencySymbol} ${Math.abs(unrealizedPnl).toLocaleString("en",{minimumFractionDigits:2,maximumFractionDigits:2})}`],
    ["Return", `${returnPct >= 0 ? "+" : ""}${returnPct.toFixed(1)}%`],
    ["Holdings", `${holdingsCount} across ${accountsCount} account${accountsCount !== 1 ? "s" : ""}`],
    ["Best day", bestDay ? `▲ +${currencySymbol} ${bestDay.delta.toLocaleString("en",{maximumFractionDigits:0})} (${bestDay.label})` : "—"],
  ];
  return (
    <div style={{ display:"flex", gap:0, borderTop:`1px solid ${T.border}` }}>
      {cells.map(([label, val], i) => (
        <div key={i} style={{ flex:1, padding:"12px 16px", borderRight: i < cells.length - 1 ? `1px solid ${T.border}` : "none", display:"flex", flexDirection:"column", gap:3 }}>
          <div style={{ fontSize:10, color:T.mutedFg, textTransform:"uppercase", letterSpacing:".08em" }}>{label}</div>
          <div style={{ fontSize:12, fontWeight:600, fontVariantNumeric:"tabular-nums" }}>{val}</div>
        </div>
      ))}
    </div>
  );
}
```

- [ ] **Step 4: Run — expect pass.**

- [ ] **Step 5: Commit**

```bash
git add frontend/components/investments/PortfolioStatsStrip.tsx frontend/components/investments/PortfolioStatsStrip.test.tsx
git commit -m "feat(investments): PortfolioStatsStrip + best-day calc"
```

---

## Task 8: `HoldingsTableHF` with sort + filter + delete

**Files:**
- Create: `frontend/components/investments/HoldingsTableHF.tsx`
- Test: `frontend/components/investments/HoldingsTableHF.test.tsx`

- [ ] **Step 1: Write the failing test**

```tsx
import { render, screen, within, fireEvent } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import { HoldingsTableHF } from "./HoldingsTableHF";
import type { Holding } from "@/lib/api/investments";

const H: Holding[] = [
  { id:"1", account_id:"a", symbol:"VUAA", name:"Vanguard", currency:"USD", instrument_type:"etf", quantity:"10", source:"manual", current_price:"100", current_value_user_currency:"1000", is_stale:false },
  { id:"2", account_id:"a", symbol:"MSFT", name:"Microsoft", currency:"USD", instrument_type:"equity", quantity:"5", source:"manual", current_price:"400", current_value_user_currency:"2000", is_stale:true },
];

describe("HoldingsTableHF", () => {
  it("filters to ETF only when filter clicked", () => {
    render(<HoldingsTableHF holdings={H} accountNames={{ a: "Acct" }} accountsCount={1} />);
    fireEvent.click(screen.getByRole("button", { name: "ETF" }));
    expect(screen.queryByText("MSFT")).toBeNull();
    expect(screen.getByText("VUAA")).toBeTruthy();
  });
  it("flags stale rows", () => {
    const { container } = render(<HoldingsTableHF holdings={H} accountNames={{ a: "Acct" }} accountsCount={1} />);
    expect(container.querySelectorAll("tr.stale").length).toBe(1);
  });
});
```

- [ ] **Step 2: Run — expect fail.**

- [ ] **Step 3: Implement**

```tsx
// frontend/components/investments/HoldingsTableHF.tsx
"use client";
import { useState } from "react";
import { RiAddLine, RiArrowDownSLine, RiArrowUpSLine, RiArrowUpDownLine, RiMore2Fill } from "@remixicon/react";
import type { Holding } from "@/lib/api/investments";
import { T } from "./_tokens";

type Filter = "All" | "ETF" | "Equity" | "Cash";
type SortKey = "sym" | "acct" | "type" | "qty" | "price" | "value" | "pnl";

export function TypeBadge({ type }: { type: "etf"|"equity"|"cash" }) {
  const s = {
    etf: { background:T.primary, color:T.primaryFg, border:`1px solid ${T.primary}` },
    equity: { background:T.muted, color:T.fg, border:`1px solid ${T.border}` },
    cash: { background:"transparent", color:T.mutedFg, border:`1px solid ${T.border}` },
  }[type];
  return <span style={{ display:"inline-flex", padding:"1px 6px", fontSize:10, letterSpacing:".04em", ...s }}>
    {type === "etf" ? "ETF" : type === "equity" ? "Equity" : "Cash"}
  </span>;
}

export function HoldingsTableHF({
  holdings, accountNames, accountsCount, onAddClick, onDelete,
}: {
  holdings: Holding[];
  accountNames: Record<string, string>;
  accountsCount: number;
  onAddClick?: () => void;
  onDelete?: (id: string) => void;
}) {
  const [filter, setFilter] = useState<Filter>("All");
  const [sortKey, setSortKey] = useState<SortKey>("value");
  const [sortDir, setSortDir] = useState<-1 | 1>(-1);

  const handleSort = (k: SortKey) => {
    if (k === sortKey) setSortDir(d => (d * -1) as -1 | 1);
    else { setSortKey(k); setSortDir(-1); }
  };

  const rows = holdings
    .filter(h => filter === "All"
      || (filter === "ETF" && h.instrument_type === "etf")
      || (filter === "Equity" && h.instrument_type === "equity")
      || (filter === "Cash" && h.instrument_type === "cash"))
    .map(h => ({
      ...h,
      _qty: Number(h.quantity), _price: Number(h.current_price ?? 0),
      _value: Number(h.current_value_user_currency ?? 0),
      _acct: accountNames[h.account_id] ?? h.account_id,
    }))
    .sort((a, b) => {
      const get = (r: typeof a) => ({ sym:r.symbol, acct:r._acct, type:r.instrument_type, qty:r._qty, price:r._price, value:r._value, pnl:0 }[sortKey]);
      const av = get(a) ?? 0, bv = get(b) ?? 0;
      return typeof av === "string" ? av.localeCompare(bv as string) * sortDir : ((av as number) - (bv as number)) * sortDir;
    });

  const SortIcon = ({ k }: { k: SortKey }) =>
    sortKey === k
      ? (sortDir === -1 ? <RiArrowDownSLine size={11} /> : <RiArrowUpSLine size={11} />)
      : <RiArrowUpDownLine size={10} style={{ opacity:0.3 }} />;

  const totalValue = rows.reduce((s, r) => s + r._value, 0);

  return (
    <div style={{ background:T.card, border:`1px solid ${T.border}` }}>
      <div style={{ display:"flex", alignItems:"center", padding:"12px 18px", gap:12, borderBottom:`1px solid ${T.border}`, flexWrap:"wrap" }}>
        <span style={{ fontWeight:600, fontSize:13 }}>All holdings</span>
        <span style={{ fontSize:11, color:T.mutedFg }}>{holdings.length} positions · {accountsCount} account{accountsCount !== 1 ? "s" : ""}</span>
        <div style={{ flex:1 }} />
        <div style={{ display:"flex", gap:0 }}>
          {(["All","ETF","Equity","Cash"] as Filter[]).map(t => {
            const active = filter === t;
            return (
              <button key={t} onClick={() => setFilter(t)} style={{
                padding:"4px 10px", fontSize:11, fontFamily:"inherit",
                border:`1px solid ${active ? T.primary : T.border}`,
                background: active ? T.primary : T.card,
                color: active ? T.primaryFg : T.mutedFg,
                cursor:"pointer", marginLeft:-1,
              }}>{t}</button>
            );
          })}
        </div>
        {onAddClick && (
          <button onClick={onAddClick} style={{ display:"inline-flex", alignItems:"center", gap:6, padding:"5px 12px", background:T.primary, color:T.primaryFg, border:"none", cursor:"pointer", fontSize:11 }}>
            <RiAddLine size={12} /> Add holding
          </button>
        )}
      </div>
      <table style={{ width:"100%", borderCollapse:"collapse", fontSize:12 }}>
        <thead>
          <tr style={{ borderBottom:`1px solid ${T.border}` }}>
            {([
              ["sym","Symbol","left"],["acct","Account","left"],["type","Type","left"],
              ["qty","Qty","right"],["price","Price","right"],["value","Value","right"],
            ] as const).map(([k, label, align]) => (
              <th key={k} onClick={() => handleSort(k as SortKey)} style={{
                textAlign:align, padding:"9px 18px", fontSize:10, color:T.mutedFg, fontWeight:500,
                textTransform:"uppercase", letterSpacing:".08em", cursor:"pointer", userSelect:"none",
              }}>
                <span style={{ display:"inline-flex", alignItems:"center", gap:2 }}>{label}<SortIcon k={k as SortKey} /></span>
              </th>
            ))}
            <th style={{ width:36 }} />
          </tr>
        </thead>
        <tbody>
          {rows.map(h => (
            <tr key={h.id} className={h.is_stale ? "stale" : ""} style={{ borderBottom:`1px solid ${T.muted}`, background: h.is_stale ? T.staleBg : undefined }}>
              <td style={{ padding:"11px 18px" }}>
                <div style={{ display:"flex", alignItems:"center", gap:6 }}>
                  <span style={{ fontWeight:700, fontSize:13 }}>{h.symbol}</span>
                  {h.is_stale && <span title="Price may be stale" style={{ width:6, height:6, background:T.stale, borderRadius:"50%" }} />}
                </div>
                <div style={{ fontSize:10, color:T.mutedFg, marginTop:1 }}>{h.name ?? ""}</div>
              </td>
              <td style={{ padding:"11px 18px" }}>
                <span style={{ padding:"2px 6px", border:`1px solid ${T.border}`, fontSize:10, color:T.mutedFg, background:T.muted }}>{h._acct}</span>
              </td>
              <td style={{ padding:"11px 18px" }}><TypeBadge type={h.instrument_type} /></td>
              <td style={{ padding:"11px 18px", textAlign:"right", fontVariantNumeric:"tabular-nums" }}>{h._qty.toLocaleString()}</td>
              <td style={{ padding:"11px 18px", textAlign:"right", fontVariantNumeric:"tabular-nums", color:T.mutedFg }}>
                {h.current_price ? `${h.currency === "USD" ? "$" : "€"} ${h._price.toFixed(2)}` : "—"}
              </td>
              <td style={{ padding:"11px 18px", textAlign:"right", fontVariantNumeric:"tabular-nums", fontWeight:600 }}>
                € {h._value.toLocaleString("en",{minimumFractionDigits:2,maximumFractionDigits:2})}
              </td>
              <td style={{ padding:"11px 10px", textAlign:"center" }}>
                {onDelete && h.source === "manual" && (
                  <button onClick={() => onDelete(h.id)} title="Delete" style={{ background:"transparent", border:"none", cursor:"pointer", color:T.mutedFg }}>
                    <RiMore2Fill size={14} />
                  </button>
                )}
              </td>
            </tr>
          ))}
        </tbody>
        <tfoot>
          <tr style={{ borderTop:`1px solid ${T.border}`, background:T.bg }}>
            <td colSpan={5} style={{ padding:"10px 18px", fontSize:11, fontWeight:600, color:T.mutedFg }}>Total</td>
            <td style={{ padding:"10px 18px", textAlign:"right", fontWeight:700, fontVariantNumeric:"tabular-nums", fontSize:13 }}>€ {totalValue.toLocaleString("en",{minimumFractionDigits:2,maximumFractionDigits:2})}</td>
            <td />
          </tr>
        </tfoot>
      </table>
    </div>
  );
}
```

- [ ] **Step 4: Run — expect pass.**

- [ ] **Step 5: Commit**

```bash
git add frontend/components/investments/HoldingsTableHF.tsx frontend/components/investments/HoldingsTableHF.test.tsx
git commit -m "feat(investments): HoldingsTableHF with sort/filter/stale"
```

---

## Task 9: `InvestmentsOverview` composer

**Files:**
- Create: `frontend/components/investments/InvestmentsOverview.tsx`

- [ ] **Step 1: Implement**

```tsx
// frontend/components/investments/InvestmentsOverview.tsx
"use client";
import { useState, useTransition, useMemo } from "react";
import { useRouter } from "next/navigation";
import { fetchHistoryRange, type Range } from "@/lib/actions/investments";
import { deleteHolding, type Holding, type PortfolioSummary, type ValuationPoint } from "@/lib/api/investments";
import { PortfolioHero } from "./PortfolioHero";
import { PortfolioChart } from "./PortfolioChart";
import { PortfolioStatsStrip, computeBestDay } from "./PortfolioStatsStrip";
import { AllocationRow } from "./AllocationRow";
import { HoldingsTableHF } from "./HoldingsTableHF";
import { T } from "./_tokens";

export function InvestmentsOverview({
  portfolio, holdings, initialHistory, initialRange = "1M",
}: {
  portfolio: PortfolioSummary;
  holdings: Holding[];
  initialHistory: ValuationPoint[];
  initialRange?: Range;
}) {
  const router = useRouter();
  const [range, setRange] = useState<Range>(initialRange);
  const [history, setHistory] = useState<ValuationPoint[]>(initialHistory);
  const [pending, startTransition] = useTransition();

  const series = useMemo(() => history.map(p => Number(p.value)).filter(v => Number.isFinite(v)), [history]);
  const first = series[0] ?? 0, last = series[series.length - 1] ?? 0;
  const absChange = last - first;
  const pctChange = first > 0 ? (absChange / first) * 100 : 0;

  const totalValue = Number(portfolio.total_value);
  const costBasis = totalValue - absChange;
  const accountNames = Object.fromEntries(portfolio.accounts.map(a => [a.id, a.name]));
  const staleCount = holdings.filter(h => h.is_stale).length;

  const bestDayRaw = computeBestDay(series);
  const bestDay = bestDayRaw && history[bestDayRaw.index]
    ? { delta: bestDayRaw.delta, label: new Date(history[bestDayRaw.index].date).toLocaleDateString("en", { month: "short", day: "numeric" }) }
    : null;

  const onRangeChange = (r: Range) => {
    setRange(r);
    startTransition(async () => {
      const next = await fetchHistoryRange(r);
      setHistory(next);
    });
  };

  const onDelete = async (id: string) => {
    if (!confirm("Delete this holding?")) return;
    await deleteHolding(id);
    router.refresh();
  };

  return (
    <div className="syllogic-surface" style={{ flex:1, overflow:"auto" }}>
      <div style={{ padding:24, display:"flex", flexDirection:"column", gap:16 }}>
        <PortfolioHero
          totalValue={totalValue}
          currency={portfolio.currency}
          absChange={absChange}
          pctChange={pctChange}
          range={range}
          onRangeChange={onRangeChange}
          asOf="moments ago"
          staleCount={staleCount}
        />
        <div style={{ background:T.card, border:`1px solid ${T.border}`, opacity: pending ? 0.7 : 1, transition:"opacity 120ms" }}>
          <div style={{ padding:"16px 16px 0" }}>
            <PortfolioChart data={series} currencySymbol={portfolio.currency === "USD" ? "$" : "€"} />
          </div>
          <PortfolioStatsStrip
            costBasis={costBasis}
            unrealizedPnl={absChange}
            returnPct={pctChange}
            holdingsCount={holdings.length}
            accountsCount={portfolio.accounts.length}
            bestDay={bestDay}
            currencySymbol={portfolio.currency === "USD" ? "$" : "€"}
          />
        </div>
        <AllocationRow byInstrument={portfolio.allocation_by_type} byCurrency={portfolio.allocation_by_currency} />
        <HoldingsTableHF
          holdings={holdings}
          accountNames={accountNames}
          accountsCount={portfolio.accounts.length}
          onAddClick={() => router.push("/investments/connect")}
          onDelete={onDelete}
        />
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/components/investments/InvestmentsOverview.tsx
git commit -m "feat(investments): InvestmentsOverview composer with range fetch"
```

---

## Task 10: `InvestmentsEmpty` state

**Files:**
- Create: `frontend/components/investments/InvestmentsEmpty.tsx`

- [ ] **Step 1: Implement**

Translate `InvestmentsEmpty` from `Investments.html` lines 526–594. Both buttons → `router.push("/investments/connect")`.

```tsx
// frontend/components/investments/InvestmentsEmpty.tsx
"use client";
import { useRouter } from "next/navigation";
import { RiAddLine, RiLineChartLine, RiLinksLine, RiPencilLine } from "@remixicon/react";
import { T } from "./_tokens";

export function InvestmentsEmpty() {
  const router = useRouter();
  const go = () => router.push("/investments/connect");
  return (
    <div className="syllogic-surface" style={{ flex:1, display:"flex", alignItems:"center", justifyContent:"center", padding:40 }}>
      <div style={{ maxWidth:520, width:"100%", display:"flex", flexDirection:"column" }}>
        <div style={{ padding:"32px 32px 24px", background:T.card, border:`1px solid ${T.border}`, display:"flex", flexDirection:"column", gap:12, alignItems:"center", textAlign:"center" }}>
          <div style={{ width:44, height:44, border:`1px solid ${T.border}`, display:"flex", alignItems:"center", justifyContent:"center", background:T.bg }}>
            <RiLineChartLine size={20} color={T.mutedFg} />
          </div>
          <div style={{ display:"flex", flexDirection:"column", gap:6 }}>
            <div style={{ fontSize:15, fontWeight:600 }}>No holdings yet</div>
            <div style={{ fontSize:12, color:T.mutedFg, lineHeight:1.7, maxWidth:340 }}>
              Track your portfolio by connecting a broker for automatic sync, or add holdings manually.
            </div>
          </div>
        </div>
        <div style={{ display:"flex", gap:0, borderLeft:`1px solid ${T.border}`, borderRight:`1px solid ${T.border}`, borderBottom:`1px solid ${T.border}` }}>
          <div style={{ flex:1, padding:24, display:"flex", flexDirection:"column", gap:12, borderRight:`1px solid ${T.border}` }}>
            <div style={{ display:"flex", alignItems:"center", gap:8 }}>
              <RiLinksLine size={16} />
              <span style={{ fontWeight:600, fontSize:13 }}>Connect broker</span>
              <span style={{ marginLeft:"auto", padding:"1px 6px", background:T.primary, color:T.primaryFg, fontSize:9, letterSpacing:".06em" }}>RECOMMENDED</span>
            </div>
            <div style={{ fontSize:11, color:T.mutedFg, lineHeight:1.7 }}>Connect Interactive Brokers via Flex Query. Positions and trades sync automatically.</div>
            <ul style={{ margin:"4px 0 0", padding:"0 0 0 16px", display:"flex", flexDirection:"column", gap:5 }}>
              {["Automatic position sync","Trade history imported","No manual entry needed"].map(t => <li key={t} style={{ fontSize:11, color:T.mutedFg }}>{t}</li>)}
            </ul>
            <button onClick={go} style={{ marginTop:4, padding:"8px 0", background:T.primary, color:T.primaryFg, border:"none", cursor:"pointer", fontFamily:"inherit", fontSize:12, fontWeight:500, display:"flex", alignItems:"center", justifyContent:"center", gap:6 }}>
              <RiLinksLine size={13} /> Connect IBKR
            </button>
          </div>
          <div style={{ flex:1, padding:24, display:"flex", flexDirection:"column", gap:12 }}>
            <div style={{ display:"flex", alignItems:"center", gap:8 }}>
              <RiPencilLine size={16} />
              <span style={{ fontWeight:600, fontSize:13 }}>Add manually</span>
            </div>
            <div style={{ fontSize:11, color:T.mutedFg, lineHeight:1.7 }}>Create an account, search by symbol, and enter quantities. Prices are fetched automatically.</div>
            <ul style={{ margin:"4px 0 0", padding:"0 0 0 16px", display:"flex", flexDirection:"column", gap:5 }}>
              {["No broker needed","Prices updated daily","You manage quantities"].map(t => <li key={t} style={{ fontSize:11, color:T.mutedFg }}>{t}</li>)}
            </ul>
            <button onClick={go} style={{ marginTop:4, padding:"8px 0", background:T.card, color:T.fg, border:`1px solid ${T.border}`, cursor:"pointer", fontFamily:"inherit", fontSize:12, fontWeight:500, display:"flex", alignItems:"center", justifyContent:"center", gap:6 }}>
              <RiAddLine size={13} /> Add holding
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/components/investments/InvestmentsEmpty.tsx
git commit -m "feat(investments): empty-state split path card"
```

---

## Task 11: Wire `/investments/page.tsx`

**Files:**
- Modify: `frontend/app/(dashboard)/investments/page.tsx`

- [ ] **Step 1: Replace contents**

```tsx
import { getPortfolio, listHoldings, getPortfolioHistory } from "@/lib/api/investments";
import { InvestmentsOverview } from "@/components/investments/InvestmentsOverview";
import { InvestmentsEmpty } from "@/components/investments/InvestmentsEmpty";
import { rangeToDates } from "@/lib/actions/investments";

export const dynamic = "force-dynamic";

export default async function InvestmentsPage() {
  const [portfolio, holdings] = await Promise.all([getPortfolio(), listHoldings()]);
  if (holdings.length === 0) return <InvestmentsEmpty />;
  const { from, to } = rangeToDates("1M");
  const history = await getPortfolioHistory(from, to);
  return <InvestmentsOverview portfolio={portfolio} holdings={holdings} initialHistory={history} initialRange="1M" />;
}
```

- [ ] **Step 2: Run dev server smoke test**

```bash
cd frontend && pnpm dev
```

Visit `/investments` while signed in. Confirm: timeline-first overview renders; range toggle changes the chart; sort/filter work; stale row visibly tinted.

- [ ] **Step 3: Commit**

```bash
git add frontend/app/(dashboard)/investments/page.tsx
git commit -m "feat(investments): wire timeline-first page + empty branch"
```

---

## Task 12: `BrokerForm`

**Files:**
- Create: `frontend/components/investments/BrokerForm.tsx`

- [ ] **Step 1: Implement**

Translate the broker form from `Investments.html` lines 743–824. Submit calls `createBrokerConnection`. Reproduce: IBKR badge header, "What you need" info block, base currency select, account name field, eye/eye-off toggle on token, two query ID fields, "Connect & sync" CTA, "More brokers — coming soon" disabled cards (Trading 212, Degiro, Schwab).

```tsx
// frontend/components/investments/BrokerForm.tsx
"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";
import { RiBankLine, RiExternalLinkLine, RiEyeLine, RiEyeOffLine, RiRefreshLine, RiArrowDownSLine } from "@remixicon/react";
import { createBrokerConnection } from "@/lib/api/investments";
import { T } from "./_tokens";

export function BrokerForm({ onCancel }: { onCancel: () => void }) {
  const router = useRouter();
  const [accountName, setAccountName] = useState("IBKR Main");
  const [baseCurrency, setBaseCurrency] = useState("EUR");
  const [token, setToken] = useState("");
  const [tokenVisible, setTokenVisible] = useState(false);
  const [qPos, setQPos] = useState("");
  const [qTrades, setQTrades] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true); setErr(null);
    try {
      await createBrokerConnection({
        provider: "ibkr_flex", flex_token: token, query_id_positions: qPos,
        query_id_trades: qTrades, account_name: accountName, base_currency: baseCurrency,
      });
      router.push("/investments");
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally { setBusy(false); }
  };

  return (
    <form onSubmit={submit} style={{ borderTop:`2px solid ${T.primary}`, background:T.card, border:`1px solid ${T.border}`, padding:24 }}>
      <div style={{ display:"flex", alignItems:"center", gap:12, marginBottom:20 }}>
        <div style={{ width:36, height:36, border:`1px solid ${T.border}`, display:"flex", alignItems:"center", justifyContent:"center", fontWeight:700, fontSize:11, color:T.mutedFg }}>IBKR</div>
        <div>
          <div style={{ fontWeight:600, fontSize:13 }}>Interactive Brokers · Flex Query</div>
          <div style={{ fontSize:11, color:T.mutedFg, marginTop:2 }}>Positions and trade history sync automatically via the Flex Web Service</div>
        </div>
      </div>
      <div style={{ background:T.bg, border:`1px solid ${T.border}`, padding:"12px 16px", marginBottom:20, display:"flex", flexDirection:"column", gap:8 }}>
        <div style={{ fontSize:10, color:T.mutedFg, textTransform:"uppercase", letterSpacing:".1em" }}>What you need</div>
        {[
          "A Flex Web Service token — from IBKR Account Management → Reports → Flex Queries",
          "A Positions Flex Query ID configured to export account positions",
          "A Trades Flex Query ID configured to export trade history",
        ].map(t => (<div key={t} style={{ display:"flex", gap:8, fontSize:11, color:T.mutedFg }}><span>·</span><span>{t}</span></div>))}
        <a href="https://www.interactivebrokers.com/en/index.php?f=1325" target="_blank" rel="noreferrer" style={{ fontSize:11, color:T.fg, marginTop:4, display:"inline-flex", alignItems:"center", gap:4 }}>
          <RiExternalLinkLine size={11} /> How to set up Flex Queries →
        </a>
      </div>
      <div style={{ display:"flex", flexDirection:"column", gap:14 }}>
        <div style={{ display:"flex", gap:14 }}>
          <Field label="Account name" flex={2}>
            <Input value={accountName} onChange={e => setAccountName(e.target.value)} />
          </Field>
          <Field label="Base currency" flex={1}>
            <SelectWithChevron value={baseCurrency} onChange={e => setBaseCurrency(e.target.value)}>
              <option>EUR</option><option>USD</option>
            </SelectWithChevron>
          </Field>
        </div>
        <Field label="Flex token">
          <div style={{ position:"relative" }}>
            <Input type={tokenVisible ? "text" : "password"} placeholder="Paste your Flex Web Service token" value={token} onChange={e => setToken(e.target.value)} style={{ paddingRight:36 }} />
            <button type="button" onClick={() => setTokenVisible(v => !v)} style={{ position:"absolute", right:10, top:"50%", transform:"translateY(-50%)", background:"transparent", border:"none", cursor:"pointer", color:T.mutedFg }}>
              {tokenVisible ? <RiEyeOffLine size={13} /> : <RiEyeLine size={13} />}
            </button>
          </div>
        </Field>
        <div style={{ display:"flex", gap:14 }}>
          <Field label="Positions query ID" flex={1}><Input placeholder="e.g. 123456" value={qPos} onChange={e => setQPos(e.target.value)} /></Field>
          <Field label="Trades query ID" flex={1}><Input placeholder="e.g. 789012" value={qTrades} onChange={e => setQTrades(e.target.value)} /></Field>
        </div>
        {err && <div style={{ color:T.negative, fontSize:11 }}>{err}</div>}
        <div style={{ display:"flex", justifyContent:"space-between", alignItems:"center", marginTop:4 }}>
          <button type="button" onClick={onCancel} style={btnGhost}>Cancel</button>
          <button type="submit" disabled={busy} style={btnPrimary}>
            <RiRefreshLine size={13} /> {busy ? "Syncing…" : "Connect & sync"}
          </button>
        </div>
      </div>
      <div style={{ marginTop:24, paddingTop:20, borderTop:`1px solid ${T.border}` }}>
        <div style={{ fontSize:10, color:T.mutedFg, textTransform:"uppercase", letterSpacing:".1em", marginBottom:10 }}>More brokers — coming soon</div>
        <div style={{ display:"flex", gap:10 }}>
          {["Trading 212","Degiro","Schwab"].map(b => (
            <div key={b} style={{ flex:1, padding:"10px 14px", border:`1px solid ${T.border}`, display:"flex", alignItems:"center", gap:8, opacity:.45 }}>
              <RiBankLine size={14} color={T.mutedFg} />
              <span style={{ fontSize:12, color:T.mutedFg }}>{b}</span>
            </div>
          ))}
        </div>
      </div>
    </form>
  );
}

const inputStyle: React.CSSProperties = { background:T.card, border:`1px solid ${T.border}`, padding:"7px 10px", fontSize:12, fontFamily:"inherit", color:T.fg, width:"100%", outline:"none" };
function Input(props: React.InputHTMLAttributes<HTMLInputElement>) {
  const { style, ...rest } = props;
  return <input {...rest} style={{ ...inputStyle, ...style }} />;
}
function SelectWithChevron(props: React.SelectHTMLAttributes<HTMLSelectElement> & { children: React.ReactNode }) {
  return (
    <div style={{ position:"relative" }}>
      <select {...props} style={{ ...inputStyle, appearance:"none", paddingRight:28, cursor:"pointer" }} />
      <RiArrowDownSLine size={14} style={{ position:"absolute", right:8, top:"50%", transform:"translateY(-50%)", color:T.mutedFg, pointerEvents:"none" }} />
    </div>
  );
}
function Field({ label, flex, children }: { label: React.ReactNode; flex?: number; children: React.ReactNode }) {
  return (
    <div style={{ display:"flex", flexDirection:"column", gap:4, flex }}>
      <div style={{ fontSize:10, color:T.mutedFg, letterSpacing:".08em", textTransform:"uppercase" }}>{label}</div>
      {children}
    </div>
  );
}
const btnGhost: React.CSSProperties = { padding:"7px 16px", background:"transparent", border:`1px solid ${T.border}`, fontFamily:"inherit", fontSize:12, cursor:"pointer", color:T.mutedFg };
const btnPrimary: React.CSSProperties = { display:"inline-flex", alignItems:"center", gap:6, padding:"7px 18px", background:T.primary, color:T.primaryFg, border:"none", fontFamily:"inherit", fontSize:12, cursor:"pointer", fontWeight:500 };
```

- [ ] **Step 2: Commit**

```bash
git add frontend/components/investments/BrokerForm.tsx
git commit -m "feat(investments): hi-fi BrokerForm (IBKR Flex)"
```

---

## Task 13: `ManualForm`

**Files:**
- Create: `frontend/components/investments/ManualForm.tsx`

- [ ] **Step 1: Implement**

Translate the manual form from `Investments.html` lines 666–740. Layout: row 1 = Account select + Symbol search w/ live results dropdown. Row 2 = Quantity, Instrument type segmented control, Currency select, Avg cost optional. Submit calls `addManualHolding`; if account is `"__new__"` create one first via `createManualAccount` (prompt for name inline). Cancel calls `onCancel`.

Reuse `Field`, `Input`, `SelectWithChevron`, `btnGhost`, `btnPrimary` from `BrokerForm` — to share, **promote them to `frontend/components/investments/_form-bits.tsx`** in this task and import from there in both forms.

Search dropdown: debounce 200ms, calls `searchSymbolsAction` server action; clicking result fills the symbol input + auto-selects matching instrument type/currency.

```tsx
// frontend/components/investments/ManualForm.tsx
"use client";
import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { RiSearchLine } from "@remixicon/react";
import { addManualHolding, createManualAccount, type InvestmentAccount, type SymbolSearchResult } from "@/lib/api/investments";
import { searchSymbolsAction } from "@/lib/actions/investments";
import { T } from "./_tokens";
import { Field, Input, SelectWithChevron, btnGhost, btnPrimary } from "./_form-bits";
import { TypeBadge } from "./HoldingsTableHF";

const NEW = "__new__";
type Inst = "etf" | "equity" | "cash";

export function ManualForm({ accounts, onCancel }: { accounts: InvestmentAccount[]; onCancel: () => void }) {
  const router = useRouter();
  const [accountId, setAccountId] = useState<string>(accounts[0]?.id ?? NEW);
  const [newName, setNewName] = useState("My Brokerage");
  const [baseCcy, setBaseCcy] = useState("EUR");
  const [symbol, setSymbol] = useState("");
  const [matches, setMatches] = useState<SymbolSearchResult[]>([]);
  const [showResults, setShowResults] = useState(false);
  const [qty, setQty] = useState("");
  const [type, setType] = useState<Inst>("etf");
  const [currency, setCurrency] = useState("EUR");
  const [avgCost, setAvgCost] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const debounce = useRef<number | null>(null);

  useEffect(() => {
    if (debounce.current) window.clearTimeout(debounce.current);
    if (!symbol) { setMatches([]); return; }
    debounce.current = window.setTimeout(async () => {
      try { setMatches(await searchSymbolsAction(symbol)); } catch { setMatches([]); }
    }, 200);
  }, [symbol]);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true); setErr(null);
    try {
      const target = accountId === NEW
        ? (await createManualAccount(newName, baseCcy)).account_id
        : accountId;
      await addManualHolding(target, {
        symbol, quantity: qty, instrument_type: type, currency,
        ...(avgCost ? { avg_cost: avgCost } : {}),
      });
      router.push("/investments");
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally { setBusy(false); }
  };

  return (
    <form onSubmit={submit} style={{ borderTop:`2px solid ${T.primary}`, background:T.card, border:`1px solid ${T.border}`, padding:24 }}>
      <div style={{ fontWeight:600, fontSize:13, marginBottom:18 }}>Add a holding</div>
      <div style={{ display:"flex", flexDirection:"column", gap:16 }}>
        <div style={{ display:"flex", gap:14 }}>
          <Field label="Account" flex={1.2}>
            <SelectWithChevron value={accountId} onChange={e => setAccountId(e.target.value)}>
              {accounts.map(a => <option key={a.id} value={a.id}>{a.name} · {a.base_currency}</option>)}
              <option value={NEW}>+ Create new account…</option>
            </SelectWithChevron>
          </Field>
          <Field label="Symbol" flex={2}>
            <div style={{ position:"relative" }}>
              <RiSearchLine size={12} style={{ position:"absolute", left:10, top:"50%", transform:"translateY(-50%)", color:T.mutedFg }} />
              <Input placeholder="Search symbol or name…" style={{ paddingLeft:30 }}
                value={symbol}
                onChange={e => setSymbol(e.target.value)}
                onFocus={() => setShowResults(true)}
                onBlur={() => setTimeout(() => setShowResults(false), 150)} />
              {showResults && matches.length > 0 && (
                <div style={{ position:"absolute", top:"100%", left:0, right:0, background:T.card, border:`1px solid ${T.border}`, zIndex:10, boxShadow:"0 4px 12px -2px rgb(0 0 0 / .08)" }}>
                  {matches.map((r, i) => (
                    <div key={i} onMouseDown={e => { e.preventDefault(); setSymbol(r.symbol); if (r.currency) setCurrency(r.currency); }}
                      style={{ display:"flex", alignItems:"center", gap:10, padding:"9px 12px", borderBottom: i < matches.length - 1 ? `1px solid ${T.muted}` : "none", cursor:"pointer" }}>
                      <span style={{ fontWeight:700, fontSize:12, minWidth:44 }}>{r.symbol}</span>
                      <span style={{ flex:1, fontSize:11, color:T.mutedFg }}>{r.name}</span>
                      {r.exchange && <span style={{ fontSize:10, padding:"1px 5px", border:`1px solid ${T.border}`, color:T.mutedFg }}>{r.exchange}</span>}
                    </div>
                  ))}
                </div>
              )}
            </div>
          </Field>
        </div>
        {accountId === NEW && (
          <div style={{ display:"flex", gap:14 }}>
            <Field label="New account name" flex={2}><Input value={newName} onChange={e => setNewName(e.target.value)} /></Field>
            <Field label="Base currency" flex={1}>
              <SelectWithChevron value={baseCcy} onChange={e => setBaseCcy(e.target.value)}>
                <option>EUR</option><option>USD</option><option>GBP</option>
              </SelectWithChevron>
            </Field>
          </div>
        )}
        <div style={{ display:"flex", gap:14 }}>
          <Field label="Quantity" flex={1}><Input type="number" placeholder="0.00" value={qty} onChange={e => setQty(e.target.value)} /></Field>
          <Field label="Instrument type" flex={1}>
            <div style={{ display:"flex", gap:0 }}>
              {(["etf","equity","cash"] as Inst[]).map((t, i) => {
                const active = type === t;
                return (
                  <button type="button" key={t} onClick={() => setType(t)} style={{
                    padding:"6px 14px", fontSize:12, fontFamily:"inherit",
                    border:`1px solid ${active ? T.primary : T.border}`,
                    background: active ? T.primary : T.card,
                    color: active ? T.primaryFg : T.mutedFg,
                    cursor:"pointer", marginLeft: i === 0 ? 0 : -1, textTransform:"capitalize",
                  }}>{t === "etf" ? "ETF" : t}</button>
                );
              })}
            </div>
          </Field>
          <Field label="Currency" flex={1}>
            <SelectWithChevron value={currency} onChange={e => setCurrency(e.target.value)}>
              <option>EUR</option><option>USD</option><option>GBP</option>
            </SelectWithChevron>
          </Field>
          <Field label={<>Avg cost <span style={{ fontWeight:400, color:T.mutedFg }}>(optional)</span></>} flex={1}>
            <Input type="number" placeholder="—" value={avgCost} onChange={e => setAvgCost(e.target.value)} />
          </Field>
        </div>
        {err && <div style={{ color:T.negative, fontSize:11 }}>{err}</div>}
        <div style={{ display:"flex", justifyContent:"flex-end", gap:8, marginTop:4 }}>
          <button type="button" onClick={onCancel} style={btnGhost}>Cancel</button>
          <button type="submit" disabled={busy} style={btnPrimary}>{busy ? "Adding…" : "Add holding"}</button>
        </div>
      </div>
    </form>
  );
}
```

- [ ] **Step 2: Create `_form-bits.tsx`** by extracting `Field`, `Input`, `SelectWithChevron`, `btnGhost`, `btnPrimary` from `BrokerForm.tsx`. Update `BrokerForm.tsx` to import them. Remove duplicates from `BrokerForm`.

- [ ] **Step 3: Commit**

```bash
git add frontend/components/investments/ManualForm.tsx frontend/components/investments/_form-bits.tsx frontend/components/investments/BrokerForm.tsx
git commit -m "feat(investments): hi-fi ManualForm + shared form bits"
```

---

## Task 14: `ConnectPathPicker`

**Files:**
- Create: `frontend/components/investments/ConnectPathPicker.tsx`

- [ ] **Step 1: Implement**

Translate path-picker from `Investments.html` lines 599–663. Two cards toggle a `picked` state; selecting one mounts the matching form below.

```tsx
// frontend/components/investments/ConnectPathPicker.tsx
"use client";
import { useState } from "react";
import { RiLinksLine, RiPencilLine } from "@remixicon/react";
import type { InvestmentAccount } from "@/lib/api/investments";
import { BrokerForm } from "./BrokerForm";
import { ManualForm } from "./ManualForm";
import { T } from "./_tokens";

type Path = "broker" | "manual" | null;

export function ConnectPathPicker({ accounts }: { accounts: InvestmentAccount[] }) {
  const [picked, setPicked] = useState<Path>(null);

  const paths: { id: "broker" | "manual"; icon: React.ReactNode; title: string; sub: string; badge: string | null; detail: string }[] = [
    { id: "broker", icon: <RiLinksLine size={17} />, title: "Connect broker",
      sub: "Positions and trades sync automatically. Best for IBKR users.",
      badge: "RECOMMENDED",
      detail: "Interactive Brokers via Flex Query — no manual entry once connected." },
    { id: "manual", icon: <RiPencilLine size={17} />, title: "Add manually",
      sub: "Search by symbol, enter quantity and optional cost basis.",
      badge: null,
      detail: "Prices are fetched automatically. You manage quantity updates yourself." },
  ];

  return (
    <div className="syllogic-surface" style={{ flex:1, overflow:"auto" }}>
      <div style={{ padding:"28px 32px", maxWidth:720, display:"flex", flexDirection:"column", gap:20 }}>
        <div style={{ fontSize:13, color:T.mutedFg, lineHeight:1.8, maxWidth:560 }}>
          Choose how to track your investments. You can use both methods across different accounts — a brokerage account synced from IBKR alongside a manually-managed account for assets held elsewhere.
        </div>
        <div style={{ display:"flex", gap:12 }}>
          {paths.map(p => {
            const sel = picked === p.id;
            return (
              <div key={p.id} onClick={() => setPicked(p.id)}
                style={{
                  flex:1, padding:24, cursor:"pointer", display:"flex", flexDirection:"column", gap:14,
                  background: sel ? T.bg : T.card,
                  border: sel ? `2px solid ${T.primary}` : `1px solid ${T.border}`,
                  transition:"border-color 120ms, background 120ms",
                }}>
                <div style={{ display:"flex", alignItems:"flex-start", justifyContent:"space-between" }}>
                  <div style={{ width:36, height:36, border:`1px solid ${T.border}`, display:"flex", alignItems:"center", justifyContent:"center", background: sel ? T.primary : T.card, color: sel ? T.primaryFg : T.mutedFg }}>{p.icon}</div>
                  {p.badge && <span style={{ padding:"2px 8px", background:T.primary, color:T.primaryFg, fontSize:9, letterSpacing:".08em" }}>{p.badge}</span>}
                </div>
                <div>
                  <div style={{ fontWeight:700, fontSize:14, marginBottom:6 }}>{p.title}</div>
                  <div style={{ fontSize:12, color:T.mutedFg, lineHeight:1.7 }}>{p.sub}</div>
                </div>
                <div style={{ fontSize:11, color:T.mutedFg, borderTop:`1px solid ${T.border}`, paddingTop:12, marginTop:"auto", lineHeight:1.6 }}>{p.detail}</div>
                <div style={{ display:"flex", alignItems:"center", gap:7, marginTop:4 }}>
                  <div style={{ width:14, height:14, border:`1.5px solid ${sel ? T.primary : T.border}`, borderRadius:"50%", display:"flex", alignItems:"center", justifyContent:"center" }}>
                    {sel && <div style={{ width:6, height:6, background:T.primary, borderRadius:"50%" }} />}
                  </div>
                  <span style={{ fontSize:11, color: sel ? T.fg : T.mutedFg, fontWeight: sel ? 600 : 400 }}>{sel ? "Selected" : "Select this path"}</span>
                </div>
              </div>
            );
          })}
        </div>
        {picked === "manual" && <ManualForm accounts={accounts} onCancel={() => setPicked(null)} />}
        {picked === "broker" && <BrokerForm onCancel={() => setPicked(null)} />}
        {!picked && <div style={{ fontSize:11, color:T.mutedFg, textAlign:"center", paddingTop:4 }}>Select a path above to continue</div>}
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/components/investments/ConnectPathPicker.tsx
git commit -m "feat(investments): ConnectPathPicker shell"
```

---

## Task 15: Wire `/investments/connect/page.tsx`

**Files:**
- Modify: `frontend/app/(dashboard)/investments/connect/page.tsx`

- [ ] **Step 1: Replace contents**

```tsx
import { listInvestmentAccounts } from "@/lib/api/investments";
import { ConnectPathPicker } from "@/components/investments/ConnectPathPicker";

export const dynamic = "force-dynamic";

export default async function ConnectPage() {
  const accounts = await listInvestmentAccounts();
  return <ConnectPathPicker accounts={accounts} />;
}
```

- [ ] **Step 2: Smoke test**

```bash
cd frontend && pnpm dev
```

Visit `/investments/connect`. Confirm: two cards, click manual → form panel slides in below with dark top border; click broker → broker form replaces it; symbol search shows live results; cancel collapses the form.

- [ ] **Step 3: Commit**

```bash
git add frontend/app/(dashboard)/investments/connect/page.tsx
git commit -m "feat(investments): wire connect page to PathPicker"
```

---

## Task 16: Delete obsolete components

**Files:**
- Delete: `frontend/components/investments/AddManualHoldingForm.tsx`
- Delete: `frontend/components/investments/AllocationChart.tsx`
- Delete: `frontend/components/investments/ConnectIBKRForm.tsx`
- Delete: `frontend/components/investments/HoldingsTable.tsx`
- Delete: `frontend/components/investments/PortfolioSummaryCard.tsx`

- [ ] **Step 1: Confirm no remaining importers**

```bash
cd frontend && grep -rE "AddManualHoldingForm|AllocationChart|ConnectIBKRForm|HoldingsTable[^H]|PortfolioSummaryCard" app components lib
```

Expected: no matches (or only matches inside the files being deleted).

- [ ] **Step 2: Delete**

```bash
git rm frontend/components/investments/AddManualHoldingForm.tsx frontend/components/investments/AllocationChart.tsx frontend/components/investments/ConnectIBKRForm.tsx frontend/components/investments/HoldingsTable.tsx frontend/components/investments/PortfolioSummaryCard.tsx
```

- [ ] **Step 3: Run typecheck + tests**

```bash
cd frontend && npx tsc --noEmit && npx vitest run
```

Expected: green.

- [ ] **Step 4: Commit**

```bash
git commit -m "chore(investments): remove old single-purpose components"
```

---

## Task 17: Final smoke test + lint

- [ ] **Step 1: Lint**

```bash
cd frontend && pnpm lint
```

Fix anything that blocks. Don't refactor unrelated lint issues.

- [ ] **Step 2: Manual UI check**

Run dev server, log in. Test:

1. `/investments` with **no** holdings → empty state, both CTAs go to `/investments/connect`.
2. Use the manual form to add VUAA, qty 10, ETF, EUR. After submit, `/investments` shows the timeline-first page.
3. Toggle range 1W/1M/3M/1Y/ALL — chart updates without flicker; pending opacity shows briefly.
4. Sort by Value (default), click Symbol → re-sorts.
5. Filter ETF/Equity/Cash → table filters; counts in header stay constant.
6. Mark a holding stale (or use existing stale) → row visibly tinted, badge in hero shows count.
7. From `/investments/connect`, switch between path cards — only the selected card's form is visible.

- [ ] **Step 3: Final commit (if anything was tweaked)**

```bash
git status
git commit -am "chore(investments): post-smoke-test fixes" || true
```

---

## Self-review notes

- Spec coverage: ✔ overview, empty, connect, donuts, range, sort/filter, stale, broker form, manual form, "more brokers" card row, deletion of legacy components.
- Type/name consistency: `Range` defined once in `lib/actions/investments.ts`, imported elsewhere. `Holding` from `lib/api/investments`. `TypeBadge` exported from `HoldingsTableHF` (used by `ManualForm` dropdown — verify import resolves; if not, move it into `_form-bits.tsx`).
- No placeholders left.
