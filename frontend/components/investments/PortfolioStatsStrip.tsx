export function computeBestDay(
  series: number[],
): { delta: number; index: number } | null {
  if (series.length < 2) return null;
  let best = { delta: -Infinity, index: -1 };
  for (let i = 1; i < series.length; i++) {
    const d = series[i] - series[i - 1];
    if (d > best.delta) best = { delta: d, index: i };
  }
  return best.delta > 0 ? best : null;
}

type Tone = "positive" | "negative" | "neutral";

export function PortfolioStatsStrip({
  costBasis,
  unrealizedPnl,
  returnPct,
  holdingsCount,
  accountsCount,
  bestDay,
  currencySymbol = "€",
}: {
  costBasis: number;
  unrealizedPnl: number;
  returnPct: number;
  holdingsCount: number;
  accountsCount: number;
  bestDay: { delta: number; label: string } | null;
  currencySymbol?: string;
}) {
  const cells: { label: string; value: string; tone: Tone }[] = [
    {
      label: "Cost basis",
      value: `${currencySymbol} ${costBasis.toLocaleString("en", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`,
      tone: "neutral",
    },
    {
      label: "Unrealized P&L",
      value: `${unrealizedPnl >= 0 ? "▲ +" : "▼ -"}${currencySymbol} ${Math.abs(unrealizedPnl).toLocaleString("en", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`,
      tone: unrealizedPnl >= 0 ? "positive" : "negative",
    },
    {
      label: "Return",
      value: `${returnPct >= 0 ? "+" : ""}${returnPct.toFixed(1)}%`,
      tone: returnPct >= 0 ? "positive" : "negative",
    },
    {
      label: "Holdings",
      value: `${holdingsCount}`,
      tone: "neutral",
    },
    {
      label: "Accounts",
      value: `${accountsCount}`,
      tone: "neutral",
    },
    {
      label: "Best day",
      value: bestDay
        ? `▲ +${currencySymbol} ${bestDay.delta.toLocaleString("en", { maximumFractionDigits: 0 })} (${bestDay.label})`
        : "—",
      tone: "neutral",
    },
  ];
  return (
    <div className="grid grid-cols-2 md:grid-cols-6 gap-px bg-border border border-border rounded-md overflow-hidden">
      {cells.map(({ label, value, tone }) => (
        <div key={label} className="flex flex-col gap-1 bg-card p-3">
          <div className="text-[10px] uppercase tracking-wider text-muted-foreground">
            {label}
          </div>
          <div
            className={`text-sm font-semibold tabular-nums ${
              tone === "positive"
                ? "text-emerald-600 dark:text-emerald-400"
                : tone === "negative"
                  ? "text-destructive"
                  : ""
            }`}
          >
            {value}
          </div>
        </div>
      ))}
    </div>
  );
}
