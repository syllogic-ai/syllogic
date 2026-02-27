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
import { parseDashboardSearchParams } from "@/lib/dashboard/query-params";

interface PageProps {
  searchParams: Promise<{
    [key: string]: string | string[] | undefined;
  }>;
}

export default async function HomePage({ searchParams }: PageProps) {
  const params = await searchParams;
  const parsedParams = parseDashboardSearchParams(params);
  const accountIds = parsedParams.accountIds;
  const dateFromParam = parsedParams.dateFrom;
  const dateToParam = parsedParams.dateTo;
  const horizonValue = parsedParams.horizon;
  const effectiveHorizon = parsedParams.effectiveHorizon;

  // Parse filters from URL search params
  const filters: DashboardFiltersType = {};

  if (accountIds?.length) {
    filters.accountIds = accountIds;
  }

  if (dateFromParam) {
    filters.dateFrom = new Date(dateFromParam);
  }

  if (dateToParam) {
    filters.dateTo = new Date(dateToParam);
  }

  filters.horizon = horizonValue;

  // Fetch data in parallel
  const [data, accounts] = await Promise.all([
    getDashboardData(filters),
    getUserAccounts(),
  ]);

  const accountSubtitle = !accountIds?.length
    ? "Across all accounts"
    : accountIds.length === 1
      ? "Selected account"
      : "Selected accounts";

  return (
    <>
      <Header title="Dashboard" />
      <div className="flex flex-1 flex-col gap-4 p-4 pt-0">
        {/* Filters Row */}
        <div className="flex items-center justify-between" data-walkthrough="walkthrough-filters">
          <Suspense fallback={null}>
            <DashboardFilters accounts={accounts} />
          </Suspense>
          <SearchButton />
        </div>
        {/* Row 1: KPI Cards */}
        <div className="grid gap-4 md:grid-cols-4">
          <div data-walkthrough="walkthrough-balance">
            <KpiSparkCard
              title="Total Balance"
            value={data.balance.total}
            currency={data.balance.currency}
            subtitle={accountSubtitle}
            sparkData={data.balanceHistory}
          />
          </div>
          <div data-walkthrough="walkthrough-spending">
          <KpiSparkCard
            title={`${data.periodLabel.title} Spending`}
            value={data.periodSpending.total}
            currency={data.periodSpending.currency}
            subtitle={data.periodLabel.subtitle}
            sparkData={data.spendingHistory}
          />
          </div>
          <div data-walkthrough="walkthrough-income">
          <KpiSparkCard
            title={`${data.periodLabel.title} Income`}
            value={data.periodIncome.total}
            currency={data.periodIncome.currency}
            subtitle={data.periodLabel.subtitle}
            sparkData={data.incomeHistory}
          />
          </div>
          <div data-walkthrough="walkthrough-savings">
          <KpiSparkCard
            title="Savings Rate"
            value={data.savingsRate.amount}
            currency={data.savingsRate.currency}
            subtitle={data.periodLabel.subtitle}
            sparkData={[]}
            showSign
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
        </div>

        {/* Row 2: Charts */}
        <div className="grid gap-4 md:grid-cols-5">
          <div data-walkthrough="walkthrough-profit-loss" className="col-span-3">
          <ProfitLossChart
            data={data.incomeExpense}
            currency={data.balance.currency}
          />
          </div>
          <div data-walkthrough="walkthrough-category" className="col-span-2">
          <SpendingByCategoryChart
            data={data.spendingByCategory.categories}
            total={data.spendingByCategory.total}
            currency={data.balance.currency}
            periodTitle={data.periodLabel.title}
            accountIds={accountIds}
            dateFrom={dateFromParam}
            dateTo={dateToParam}
            horizon={effectiveHorizon}
          />
          </div>
        </div>

        {/* Row 3: Cash Flow Sankey */}
        <div className="grid gap-4">
          <div data-walkthrough="walkthrough-cash-flow">
          <SankeyFlowChart
            data={data.sankeyData}
            currency={data.balance.currency}
            subtitle={data.periodLabel.subtitle}
            accountIds={accountIds}
            dateFrom={dateFromParam}
            dateTo={dateToParam}
            horizon={effectiveHorizon}
          />
          </div>
        </div>

        {/* Row 4: Assets Overview */}
        <div className="grid gap-4">
          <AssetsOverviewCard data={data.assetsOverview} />
        </div>
      </div>
    </>
  );
}
