import Link from "next/link";
import { Header } from "@/components/layout/header";
import { KpiSparkCard } from "@/components/charts/kpi-spark-card";
import { ProfitLossChart } from "@/components/charts/profit-loss-chart";
import { SpendingByCategoryChart } from "@/components/charts/spending-by-category-chart";
import { AssetsOverviewCard } from "@/components/assets";
import { getDashboardData } from "@/lib/actions/dashboard";
import {
  RiWalletLine,
  RiArrowDownLine,
  RiArrowUpLine,
  RiAddLine,
} from "@remixicon/react";

export default async function HomePage() {
  const data = await getDashboardData();

  return (
    <>
      <Header
        title="Dashboard"
        action={
          <Link
            href="/transactions"
            className="inline-flex items-center justify-center whitespace-nowrap text-xs font-medium h-8 gap-1.5 px-2.5 bg-primary text-primary-foreground hover:bg-primary/80 transition-all"
          >
            <RiAddLine className="h-4 w-4" />
            Add Transaction
          </Link>
        }
      />
      <div className="flex flex-1 flex-col gap-4 p-4 pt-0">
        {/* Row 1: KPI Cards */}
        <div className="grid gap-4 md:grid-cols-3">
          <KpiSparkCard
            title="Total Balance"
            value={data.balance.total}
            currency={data.balance.currency}
            subtitle="Across all accounts"
            sparkData={data.balanceHistory}
            icon={<RiWalletLine className="h-4 w-4" />}
          />
          <KpiSparkCard
            title="Monthly Spending"
            value={data.monthlySpending.total}
            currency={data.monthlySpending.currency}
            subtitle="This month"
            sparkData={data.spendingHistory}
            icon={<RiArrowDownLine className="h-4 w-4" />}
          />
          <KpiSparkCard
            title="Monthly Income"
            value={data.monthlyIncome.total}
            currency={data.monthlyIncome.currency}
            subtitle="This month"
            sparkData={data.incomeHistory}
            icon={<RiArrowUpLine className="h-4 w-4" />}
          />
        </div>

        {/* Row 2: Charts */}
        <div className="grid gap-4 md:grid-cols-5">
          <ProfitLossChart
            data={data.incomeExpense}
            currency={data.balance.currency}
          />
          <SpendingByCategoryChart
            data={data.spendingByCategory.categories}
            total={data.spendingByCategory.total}
            currency={data.balance.currency}
          />
        </div>

        {/* Row 3: Assets Overview */}
        <div className="grid gap-4">
          <AssetsOverviewCard data={data.assetsOverview} />
        </div>
      </div>
    </>
  );
}
