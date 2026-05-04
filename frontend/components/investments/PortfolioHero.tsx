"use client";
import { RiAlertLine } from "@remixicon/react";
import { Card, CardContent } from "@/components/ui/card";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { currencySymbol } from "@/lib/utils/currency";
import type { Range } from "@/lib/actions/investments";

const RANGES: Range[] = ["1W", "1M", "3M", "1Y", "ALL"];

const RANGE_LABEL: Record<Range, string> = {
  "1W": "this week",
  "1M": "this month",
  "3M": "this 3 months",
  "1Y": "this year",
  ALL: "all time",
};

export function PortfolioHero({
  totalValue,
  currency,
  absChange,
  pctChange,
  range,
  onRangeChange,
  asOf,
  staleCount,
  headerAction,
}: {
  totalValue: number;
  currency: string;
  absChange: number;
  pctChange: number;
  range: Range;
  onRangeChange: (r: Range) => void;
  asOf: string | null;
  staleCount: number;
  headerAction?: React.ReactNode;
}) {
  const positive = absChange >= 0;
  const sym = currencySymbol(currency);
  const changeClass = positive
    ? "text-emerald-600 dark:text-emerald-400"
    : "text-destructive";
  return (
    <Card>
      <CardContent className="flex flex-col gap-2 p-6">
        <div className="flex items-start justify-between gap-3">
          <div className="text-xs uppercase tracking-wider text-muted-foreground">
            Portfolio value
          </div>
          {headerAction}
        </div>
        <div className="flex items-baseline gap-3 flex-wrap">
          <span className="text-4xl font-bold tabular-nums">
            {sym}{" "}
            {totalValue.toLocaleString("en", {
              minimumFractionDigits: 2,
              maximumFractionDigits: 2,
            })}
          </span>
          <span className={`text-sm font-medium tabular-nums ${changeClass}`}>
            {positive ? "▲" : "▼"} {positive ? "+" : "-"}
            {sym}{" "}
            {Math.abs(absChange).toLocaleString("en", {
              minimumFractionDigits: 2,
              maximumFractionDigits: 2,
            })}{" "}
            ({positive ? "+" : ""}
            {pctChange.toFixed(2)}%)
          </span>
          <span className="text-xs text-muted-foreground">
            {RANGE_LABEL[range]}
          </span>
          {asOf && (
            <span className="text-xs text-muted-foreground">· as of {asOf}</span>
          )}
          {staleCount > 0 && (
            <span className="inline-flex items-center gap-1 px-2 py-0.5 text-[10px] text-amber-600 dark:text-amber-400 border border-amber-600/30 rounded">
              <RiAlertLine size={10} /> {staleCount} stale price
              {staleCount > 1 ? "s" : ""}
            </span>
          )}
        </div>
        <div className="mt-2">
          <ToggleGroup
            multiple={false}
            value={[range]}
            onValueChange={(v) => v[0] && onRangeChange(v[0] as Range)}
            variant="outline"
            size="sm"
          >
            {RANGES.map((r) => (
              <ToggleGroupItem key={r} value={r} aria-label={`Range ${r}`}>
                {r}
              </ToggleGroupItem>
            ))}
          </ToggleGroup>
        </div>
      </CardContent>
    </Card>
  );
}
