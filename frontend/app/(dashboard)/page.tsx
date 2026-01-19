import { Suspense } from "react";
import { Header } from "@/components/layout/header";
import { KpiSparkCard } from "@/components/charts/kpi-spark-card";
import { ProfitLossChart } from "@/components/charts/profit-loss-chart";
import { SpendingByCategoryChart } from "@/components/charts/spending-by-category-chart";
import { SankeyFlowChart } from "@/components/charts/sankey-flow-chart";
import { AssetsOverviewCard } from "@/components/assets";
import { DashboardFilters } from "@/components/dashboard/dashboard-filters";
import { SearchButton } from "@/components/dashboard/search-button";
import {
  getDashboardData,
  getUserAccounts,
  type DashboardFilters as DashboardFiltersType,
} from "@/lib/actions/dashboard";

interface PageProps {
  searchParams: Promise<{
    account?: string;
    from?: string;
    to?: string;
    horizon?: string;
  }>;
}

export default async function HomePage({ searchParams }: PageProps) {
  const params = await searchParams;

  // Parse filters from URL search params
  const filters: DashboardFiltersType = {};

  if (params.account && params.account !== "all") {
    filters.accountId = params.account;
  }

  if (params.from) {
    filters.dateFrom = new Date(params.from);
  }

  if (params.to) {
    filters.dateTo = new Date(params.to);
  }

  if (params.horizon) {
    filters.horizon = parseInt(params.horizon, 10);
  }

  // Fetch data in parallel
  const [data, accounts] = await Promise.all([
    getDashboardData(filters),
    getUserAccounts(),
  ]);

  // Build Sankey subtitle based on date range
  const formatDateShort = (date: Date) => {
    return date.toLocaleDateString("en-US", { month: "short", year: "numeric" });
  };

  let sankeySubtitle: string;
  if (filters.dateFrom && filters.dateTo) {
    sankeySubtitle = `${formatDateShort(filters.dateFrom)} - ${formatDateShort(filters.dateTo)}`;
  } else if (filters.dateFrom) {
    sankeySubtitle = `From ${formatDateShort(filters.dateFrom)}`;
  } else if (filters.dateTo) {
    sankeySubtitle = `Until ${formatDateShort(filters.dateTo)}`;
  } else {
    sankeySubtitle = "Last 3 months";
  }

  return (
    <>
      <Header title="Dashboard" />
      <div className="flex flex-1 flex-col gap-4 p-4 pt-0">
        {/* Filters Row */}
        <div className="flex items-center justify-between">
          <Suspense fallback={null}>
            <DashboardFilters accounts={accounts} />
          </Suspense>
          <SearchButton />
        </div>
        {/* Row 1: KPI Cards */}
        <div className="grid gap-4 md:grid-cols-4">
          <KpiSparkCard
            title="Total Balance"
            value={data.balance.total}
            currency={data.balance.currency}
            subtitle={filters.accountId ? "Selected account" : "Across all accounts"}
            sparkData={data.balanceHistory}
          />
          <KpiSparkCard
            title="Monthly Spending"
            value={data.monthlySpending.total}
            currency={data.monthlySpending.currency}
            subtitle={data.referencePeriod.label}
            sparkData={data.spendingHistory}
          />
          <KpiSparkCard
            title="Monthly Income"
            value={data.monthlyIncome.total}
            currency={data.monthlyIncome.currency}
            subtitle={data.referencePeriod.label}
            sparkData={data.incomeHistory}
          />
          <KpiSparkCard
            title="Savings Rate"
            value={data.savingsRate.amount}
            currency={data.savingsRate.currency}
            subtitle={data.referencePeriod.label}
            sparkData={[]}
            trend={
              data.savingsRate.amount !== 0
                ? {
                    value: Math.abs(data.savingsRate.percentage),
                    isPositive: data.savingsRate.amount > 0,
                  }
                : undefined
            }
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

        {/* Row 3: Cash Flow Sankey */}
        <div className="grid gap-4">
          <SankeyFlowChart
            data={data.sankeyData}
            currency={data.balance.currency}
            subtitle={sankeySubtitle}
          />
        </div>

        {/* Row 4: Assets Overview */}
        <div className="grid gap-4">
          <AssetsOverviewCard data={data.assetsOverview} />
        </div>
      </div>
    </>
  );
}
