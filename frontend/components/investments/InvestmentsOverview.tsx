"use client";
import { useState, useTransition, useMemo, useRef } from "react";
import { useRouter } from "next/navigation";
import {
  fetchHistoryRange,
  syncAllInvestmentsAction,
  type Range,
} from "@/lib/actions/investments";
import {
  deleteHolding,
  type Holding,
  type PortfolioSummary,
  type ValuationPoint,
} from "@/lib/api/investments";
import { RiRefreshLine } from "@remixicon/react";
import { PortfolioHero } from "./PortfolioHero";
import { PortfolioChart } from "./PortfolioChart";
import { PortfolioStatsStrip, computeBestDay } from "./PortfolioStatsStrip";
import { AllocationRow } from "./AllocationRow";
import { HoldingsTableHF } from "./HoldingsTableHF";
import { T } from "./_tokens";

export function InvestmentsOverview({
  portfolio,
  holdings,
  initialHistory,
  initialRange = "1M",
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
  const activeRangeRef = useRef<Range>(initialRange);
  const [syncing, setSyncing] = useState(false);
  const [syncErr, setSyncErr] = useState<string | null>(null);

  const series = useMemo(
    () =>
      history
        .map((p) => Number(p.value))
        .filter((v) => Number.isFinite(v)),
    [history],
  );
  const first = series[0] ?? 0;
  const last = series[series.length - 1] ?? 0;
  const absChange = last - first;
  const pctChange = first > 0 ? (absChange / first) * 100 : 0;

  const totalValue = Number(portfolio.total_value);
  const costBasis = totalValue - absChange;
  const accountNames = Object.fromEntries(
    portfolio.accounts.map((a) => [a.id, a.name]),
  );
  const staleCount = holdings.filter((h) => h.is_stale).length;

  const bestDayRaw = computeBestDay(series);
  const bestDay =
    bestDayRaw && history[bestDayRaw.index]
      ? {
          delta: bestDayRaw.delta,
          label: new Date(history[bestDayRaw.index].date).toLocaleDateString(
            "en",
            { month: "short", day: "numeric" },
          ),
        }
      : null;

  const onRangeChange = (r: Range) => {
    setRange(r);
    activeRangeRef.current = r;
    startTransition(async () => {
      const next = await fetchHistoryRange(r);
      if (activeRangeRef.current === r) setHistory(next);
    });
  };

  const onDelete = async (id: string) => {
    if (!confirm("Delete this holding?")) return;
    await deleteHolding(id);
    router.refresh();
  };

  const onSync = async () => {
    setSyncing(true);
    setSyncErr(null);
    try {
      await syncAllInvestmentsAction();
      setTimeout(() => router.refresh(), 3000);
    } catch (e) {
      setSyncErr(e instanceof Error ? e.message : "Sync failed");
    } finally {
      setSyncing(false);
    }
  };

  const sym =
    portfolio.currency === "USD"
      ? "$"
      : portfolio.currency === "GBP"
        ? "£"
        : "€";

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
        <div style={{ display: "flex", alignItems: "flex-start", gap: 12 }}>
          <div style={{ flex: 1 }}>
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
          </div>
          <button
            onClick={onSync}
            disabled={syncing}
            title="Refresh prices"
            style={{
              display: "inline-flex",
              alignItems: "center",
              gap: 6,
              padding: "5px 12px",
              background: "transparent",
              border: `1px solid ${T.border}`,
              color: T.mutedFg,
              cursor: syncing ? "default" : "pointer",
              fontSize: 11,
              fontFamily: "inherit",
              opacity: syncing ? 0.5 : 1,
            }}
          >
            <RiRefreshLine
              size={12}
              style={{ animation: syncing ? "spin 1s linear infinite" : "none" }}
            />
            {syncing ? "Syncing…" : "Refresh prices"}
          </button>
        </div>
        {syncErr && (
          <div
            style={{
              fontSize: 11,
              color: "#ef4444",
              background: "rgba(239,68,68,0.08)",
              border: "1px solid rgba(239,68,68,0.3)",
              padding: "6px 10px",
            }}
          >
            Sync error: {syncErr}
          </div>
        )}
        <div
          style={{
            background: T.card,
            border: `1px solid ${T.border}`,
            opacity: pending ? 0.7 : 1,
            transition: "opacity 120ms",
          }}
        >
          <div style={{ padding: "16px 16px 0" }}>
            <PortfolioChart data={series} currencySymbol={sym} />
          </div>
          <PortfolioStatsStrip
            costBasis={costBasis}
            unrealizedPnl={absChange}
            returnPct={pctChange}
            holdingsCount={holdings.length}
            accountsCount={portfolio.accounts.length}
            bestDay={bestDay}
            currencySymbol={sym}
          />
        </div>
        <AllocationRow
          byInstrument={portfolio.allocation_by_type}
          byCurrency={portfolio.allocation_by_currency}
        />
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
