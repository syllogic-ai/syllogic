import Link from "next/link";
import { getPortfolio } from "@/lib/api/investments";

export async function PortfolioSummaryCard() {
  let portfolio;
  try {
    portfolio = await getPortfolio();
  } catch {
    return null;
  }
  const total = Number(portfolio.total_value);
  if (!total) return null;
  const change = Number(portfolio.total_value_today_change);
  return (
    <Link
      href="/investments"
      className="block rounded-xl border p-4 hover:bg-muted/40"
    >
      <div className="flex items-baseline justify-between">
        <h3 className="font-medium">Investments</h3>
        <span
          className={
            change >= 0
              ? "text-green-600 text-sm"
              : "text-red-600 text-sm"
          }
        >
          {change >= 0 ? "+" : ""}
          {change.toFixed(2)} today
        </span>
      </div>
      <p className="text-2xl mt-1">
        {portfolio.total_value} {portfolio.currency}
      </p>
    </Link>
  );
}
