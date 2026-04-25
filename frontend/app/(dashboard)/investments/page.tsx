import Link from "next/link";
import { getPortfolio, listHoldings } from "@/lib/api/investments";
import { HoldingsTable } from "@/components/investments/HoldingsTable";
import { AllocationChart } from "@/components/investments/AllocationChart";

export const dynamic = "force-dynamic";

export default async function InvestmentsPage() {
  const [portfolio, holdings] = await Promise.all([
    getPortfolio(),
    listHoldings(),
  ]);
  const change = Number(portfolio.total_value_today_change);
  return (
    <div className="space-y-6 p-6">
      <header className="flex items-end justify-between">
        <div>
          <h1 className="text-2xl font-semibold">Investments</h1>
          <p className="text-3xl mt-2">
            {portfolio.total_value} {portfolio.currency}
          </p>
          <p
            className={`text-sm ${change >= 0 ? "text-green-600" : "text-red-600"}`}
          >
            {portfolio.total_value_today_change} today
          </p>
        </div>
        <Link
          className="rounded bg-primary text-primary-foreground px-3 py-2 text-sm"
          href="/investments/connect"
        >
          Add account
        </Link>
      </header>
      <section className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <div>
          <h2 className="font-medium mb-2">By type</h2>
          <AllocationChart allocation={portfolio.allocation_by_type} />
        </div>
        <div>
          <h2 className="font-medium mb-2">By currency</h2>
          <AllocationChart allocation={portfolio.allocation_by_currency} />
        </div>
      </section>
      <section>
        <h2 className="font-medium mb-2">Holdings</h2>
        <HoldingsTable holdings={holdings} />
      </section>
    </div>
  );
}
