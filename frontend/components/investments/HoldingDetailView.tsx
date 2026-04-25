"use client";
import { useState, useTransition, useRef } from "react";
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
  return ({ USD: "$", GBP: "£", EUR: "€" } as Record<string, string>)[currency] ?? currency;
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
  const activeRangeRef = useRef<Range>("1M");

  const [qty, setQty] = useState(holding.quantity);
  const [avgCost, setAvgCost] = useState(holding.avg_cost ?? "");
  const [asOfDate, setAsOfDate] = useState(holding.as_of_date ?? "");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [chartErr, setChartErr] = useState<string | null>(null);

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
    const prev = range;
    setRange(r);
    setChartErr(null);
    activeRangeRef.current = r;
    startTransition(async () => {
      try {
        const next = await fetchHoldingHistoryRange(holding.id, r);
        if (activeRangeRef.current === r) setHistory(next);
      } catch {
        if (activeRangeRef.current === r) {
          activeRangeRef.current = prev;
          setRange(prev);
          setChartErr("Could not load history.");
        }
      }
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
        ? `${totalReturn >= 0 ? "▲ +" : "▼ -"}${fmt(Math.abs(totalReturn))}%`
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
          {chartErr && (
            <div style={{ color: T.negative, fontSize: 11, padding: "0 16px 8px" }}>
              {chartErr}
            </div>
          )}
          <div style={{ padding: "8px 16px 16px" }}>
            <PortfolioChart data={series} currencySymbol={portfolioCurrSym} />
          </div>
        </div>

        {/* Edit panel — manual holdings only */}
        {holding.source === "manual" && (
          <form
            onSubmit={onSave}
            style={{
              border: `1px solid ${T.border}`,
              borderTop: `2px solid ${T.primary}`,
              background: T.card,
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
