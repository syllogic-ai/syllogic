"use client";
import { useMemo, useRef, useState, useTransition } from "react";
import { useRouter } from "next/navigation";
import { toast } from "sonner";
import { RiRefreshLine } from "@remixicon/react";
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
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { currencySymbol } from "@/lib/utils/currency";
import { PortfolioHero } from "./PortfolioHero";
import { PortfolioChart } from "./PortfolioChart";
import { PortfolioStatsStrip, computeBestDay } from "./PortfolioStatsStrip";
import { AllocationRow } from "./AllocationRow";
import { HoldingsTableHF } from "./HoldingsTableHF";

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

  const series = useMemo(
    () => history.map((p) => Number(p.value)).filter((v) => Number.isFinite(v)),
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
          label: new Date(history[bestDayRaw.index].date).toLocaleDateString("en", {
            month: "short",
            day: "numeric",
          }),
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
    try {
      await deleteHolding(id);
      toast.success("Holding deleted");
      router.refresh();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Delete failed");
    }
  };

  const onSync = async () => {
    setSyncing(true);
    try {
      await syncAllInvestmentsAction();
      toast.success("Prices refreshed");
      router.refresh();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Sync failed");
    } finally {
      setSyncing(false);
    }
  };

  const sym = currencySymbol(portfolio.currency);

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-start gap-3">
        <div className="flex-1">
          <PortfolioHero
            totalValue={totalValue}
            currency={portfolio.currency}
            absChange={absChange}
            pctChange={pctChange}
            range={range}
            onRangeChange={onRangeChange}
            asOf={null}
            staleCount={staleCount}
          />
        </div>
        <Button
          variant="outline"
          size="sm"
          onClick={onSync}
          disabled={syncing}
          title="Refresh prices"
        >
          <RiRefreshLine className={syncing ? "size-3 animate-spin" : "size-3"} />
          {syncing ? "Syncing…" : "Refresh prices"}
        </Button>
      </div>

      <Card className={pending ? "opacity-70 transition-opacity" : "transition-opacity"}>
        <CardContent className="p-4">
          <PortfolioChart data={series} currencySymbol={sym} />
          <PortfolioStatsStrip
            costBasis={costBasis}
            unrealizedPnl={absChange}
            returnPct={pctChange}
            holdingsCount={holdings.length}
            accountsCount={portfolio.accounts.length}
            bestDay={bestDay}
            currencySymbol={sym}
          />
        </CardContent>
      </Card>

      <AllocationRow
        byInstrument={portfolio.allocation_by_type}
        byCurrency={portfolio.allocation_by_currency}
      />
      <HoldingsTableHF
        holdings={holdings}
        accountNames={accountNames}
        accountsCount={portfolio.accounts.length}
        portfolioCurrencySymbol={sym}
        onAddClick={() => router.push("/investments/connect")}
        onDelete={onDelete}
      />
    </div>
  );
}
