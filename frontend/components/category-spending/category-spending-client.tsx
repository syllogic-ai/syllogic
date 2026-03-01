"use client";

import * as React from "react";
import { useRouter } from "next/navigation";
import { RiArrowDownLine, RiArrowUpLine, RiSubtractLine } from "@remixicon/react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { DashboardFilters } from "@/components/dashboard/dashboard-filters";
import { CategorySpendingDonutChart } from "@/components/category-spending/category-spending-donut-chart";
import { TransactionTable } from "@/components/transactions/transaction-table";
import { categorySpendingTransactionColumns } from "@/components/transactions/columns";
import type { CategorySpendingData } from "@/lib/actions/category-spending";
import type { TransactionWithRelations } from "@/lib/actions/transactions";
import type { ParsedCategorySpendingQueryParams } from "@/lib/category-spending/query-params";
import { buildCategorySpendingQuery } from "@/lib/category-spending/query-params";
import type { TransactionsQueryState } from "@/lib/transactions/query-state";
import type { AccountDisplay, CategoryDisplay } from "@/types";
import { formatCurrency } from "@/lib/utils";
import { cn } from "@/lib/utils";

interface CategorySpendingClientProps {
  data: CategorySpendingData;
  query: ParsedCategorySpendingQueryParams;
  initialSelectedCategoryIds: string[];
  transactions: TransactionWithRelations[];
  transactionsTotalCount: number;
  transactionsQueryState: TransactionsQueryState;
  accounts: AccountDisplay[];
  categories: CategoryDisplay[];
}

function formatSignedPercent(value: number): string {
  const rounded = Math.abs(value).toFixed(1);
  if (value > 0) {
    return `+${rounded}%`;
  }
  if (value < 0) {
    return `-${rounded}%`;
  }
  return "0.0%";
}

function formatSignedCurrency(value: number, currency: string): string {
  if (value > 0) {
    return `+${formatCurrency(value, currency)}`;
  }
  if (value < 0) {
    return `-${formatCurrency(Math.abs(value), currency)}`;
  }
  return formatCurrency(0, currency);
}

function areArraysEqual(left: string[], right: string[]): boolean {
  if (left.length !== right.length) {
    return false;
  }

  for (let i = 0; i < left.length; i += 1) {
    if (left[i] !== right[i]) {
      return false;
    }
  }

  return true;
}

export function CategorySpendingClient({
  data,
  query,
  initialSelectedCategoryIds,
  transactions,
  transactionsTotalCount,
  transactionsQueryState,
  accounts,
  categories,
}: CategorySpendingClientProps) {
  const router = useRouter();

  const [selectedCategoryIds, setSelectedCategoryIds] = React.useState<string[]>(
    initialSelectedCategoryIds
  );
  const [tableTransactions, setTableTransactions] = React.useState(transactions);

  React.useEffect(() => {
    setSelectedCategoryIds(initialSelectedCategoryIds);
  }, [initialSelectedCategoryIds]);

  React.useEffect(() => {
    setTableTransactions(transactions);
  }, [transactions]);

  const navigateWithCategories = React.useCallback(
    (
      nextCategoryIds: string[],
      options: {
        resetPage?: boolean;
        replace?: boolean;
      } = {}
    ) => {
      const queryString = buildCategorySpendingQuery({
        categoryIds: nextCategoryIds,
        accountIds: query.accountIds,
        dateFrom: query.dateFrom,
        dateTo: query.dateTo,
        horizon: query.effectiveHorizon,
        page: options.resetPage ?? true ? 1 : query.page,
        pageSize: query.pageSize,
        sort: query.sort,
        order: query.order,
      });

      const href = queryString ? `/category-spending?${queryString}` : "/category-spending";
      if (options.replace) {
        router.replace(href, { scroll: false });
      } else {
        router.push(href, { scroll: false });
      }
    },
    [
      query.accountIds,
      query.dateFrom,
      query.dateTo,
      query.effectiveHorizon,
      query.order,
      query.page,
      query.pageSize,
      query.sort,
      router,
    ]
  );

  React.useEffect(() => {
    if (selectedCategoryIds.length === 0) {
      return;
    }

    const validCategorySet = new Set(data.categories.map((category) => category.id));
    const sanitized = selectedCategoryIds.filter((id) => validCategorySet.has(id));

    if (areArraysEqual(sanitized, selectedCategoryIds)) {
      return;
    }

    setSelectedCategoryIds(sanitized);
    navigateWithCategories(sanitized, { resetPage: true, replace: true });
  }, [data.categories, navigateWithCategories, selectedCategoryIds]);

  const selectedCategories = React.useMemo(
    () =>
      data.categories.filter((category) =>
        selectedCategoryIds.includes(category.id)
      ),
    [data.categories, selectedCategoryIds]
  );

  const selectedTotal = React.useMemo(
    () => selectedCategories.reduce((sum, category) => sum + category.amount, 0),
    [selectedCategories]
  );

  const selectedAverageMonthly = React.useMemo(
    () =>
      selectedCategories.reduce(
        (sum, category) => sum + category.averageMonthlyAmount,
        0
      ),
    [selectedCategories]
  );

  const handleToggleCategory = React.useCallback(
    (categoryId: string) => {
      const nextCategoryIds = selectedCategoryIds.includes(categoryId)
        ? selectedCategoryIds.filter((id) => id !== categoryId)
        : [...selectedCategoryIds, categoryId];

      setSelectedCategoryIds(nextCategoryIds);
      navigateWithCategories(nextCategoryIds, { resetPage: true });
    },
    [navigateWithCategories, selectedCategoryIds]
  );

  const handleUpdateTransaction = React.useCallback(
    (id: string, updates: Partial<TransactionWithRelations>) => {
      setTableTransactions((prev) =>
        prev.map((transaction) =>
          transaction.id === id ? { ...transaction, ...updates } : transaction
        )
      );
    },
    []
  );

  const handleDeleteTransaction = React.useCallback((id: string) => {
    setTableTransactions((prev) => prev.filter((transaction) => transaction.id !== id));
  }, []);

  const handleBulkUpdate = React.useCallback(
    (transactionIds: string[], categoryId: string | null) => {
      const category = categoryId
        ? categories.find((value) => value.id === categoryId) ?? null
        : null;

      setTableTransactions((prev) =>
        prev.map((transaction) =>
          transactionIds.includes(transaction.id)
            ? { ...transaction, categoryId, category }
            : transaction
        )
      );
    },
    [categories]
  );

  return (
    <div className="flex flex-1 flex-col gap-4 p-4 pt-0">
      <div className="flex items-center justify-between">
        <DashboardFilters accounts={accounts} />
      </div>

      <div className="grid gap-4 md:grid-cols-3">
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium">Total Spending</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="font-mono text-2xl font-semibold tracking-tight">
              {formatCurrency(data.summary.totalSpend, data.currency)}
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium">
              {selectedCategories.length > 0 ? "Selected Categories" : "Top Category"}
            </CardTitle>
          </CardHeader>
          <CardContent>
            {selectedCategories.length > 0 ? (
              <>
                <p className="truncate text-sm font-medium">
                  {selectedCategories.length} categor{selectedCategories.length === 1 ? "y" : "ies"}
                </p>
                <p className="font-mono text-xl text-muted-foreground">
                  {formatCurrency(selectedTotal, data.currency)}
                </p>
                <p className="mt-1 text-xs text-muted-foreground">
                  {formatCurrency(selectedAverageMonthly, data.currency)}/mo
                </p>
              </>
            ) : data.summary.topCategory ? (
              <>
                <p className="truncate text-sm font-medium">{data.summary.topCategory.name}</p>
                <p className="font-mono text-xl text-muted-foreground">
                  {formatCurrency(data.summary.topCategory.amount, data.currency)}
                </p>
              </>
            ) : (
              <p className="text-sm text-muted-foreground">No spending data</p>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium">Average Monthly</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="font-mono text-2xl font-semibold tracking-tight">
              {formatCurrency(data.summary.averageMonthlySpend, data.currency)}
            </p>
            <p className="mt-1 text-xs text-muted-foreground">
              Based on {data.range.monthCount} month{data.range.monthCount === 1 ? "" : "s"}
            </p>
          </CardContent>
        </Card>
      </div>

      <div className="grid min-h-0 flex-1 gap-4 lg:grid-cols-12">
        <div className="flex min-h-0 flex-col gap-4 lg:col-span-4">
          <CategorySpendingDonutChart
            data={data.categories}
            total={data.summary.totalSpend}
            currency={data.currency}
            selectedCategoryIds={selectedCategoryIds}
            selectedTotal={selectedTotal}
            onToggleCategory={handleToggleCategory}
          />

          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm font-medium">Category Breakdown</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              {data.categories.length === 0 ? (
                <p className="text-sm text-muted-foreground">No category spending for this period</p>
              ) : (
                data.categories.map((category) => {
                  const isSelected = selectedCategoryIds.includes(category.id);
                  const deltaPositive = category.deltaAmount > 0;
                  const deltaNegative = category.deltaAmount < 0;

                  return (
                    <button
                      key={category.id}
                      type="button"
                      className={cn(
                        "w-full rounded-md border px-3 py-2 text-left transition-colors",
                        isSelected
                          ? "border-foreground bg-muted/50"
                          : "border-border hover:bg-muted/30"
                      )}
                      onClick={() => handleToggleCategory(category.id)}
                    >
                      <div className="flex items-center justify-between gap-3">
                        <div className="flex min-w-0 items-center gap-2">
                          <span
                            className="h-2.5 w-2.5 shrink-0"
                            style={{ backgroundColor: category.fill }}
                          />
                          <span className="truncate text-sm font-medium">{category.name}</span>
                        </div>
                        <span className="shrink-0 font-mono text-sm text-muted-foreground">
                          {formatCurrency(category.amount, data.currency)}
                        </span>
                      </div>

                      <div className="mt-2 h-2 w-full bg-muted">
                        <div
                          className="h-full"
                          style={{
                            width: `${Math.max(category.sharePct, category.sharePct > 0 ? 2 : 0)}%`,
                            backgroundColor: category.fill,
                          }}
                        />
                      </div>

                      <div className="mt-2 grid grid-cols-[1fr_auto_1fr] items-center gap-2 text-xs text-muted-foreground">
                        <span className="justify-self-start text-left">
                          {category.sharePct.toFixed(1)}% of total
                        </span>
                        <span
                          className={cn(
                            "flex items-center gap-1 justify-self-center text-center",
                            deltaPositive && "text-rose-600",
                            deltaNegative && "text-emerald-600"
                          )}
                        >
                          {deltaPositive ? (
                            <RiArrowUpLine className="h-3.5 w-3.5" />
                          ) : deltaNegative ? (
                            <RiArrowDownLine className="h-3.5 w-3.5" />
                          ) : (
                            <RiSubtractLine className="h-3.5 w-3.5" />
                          )}
                          {formatSignedCurrency(category.deltaAmount, data.currency)} ({formatSignedPercent(category.deltaPct)})
                        </span>
                        <span className="justify-self-end text-right font-mono">
                          {formatCurrency(category.averageMonthlyAmount, data.currency)}/mo
                        </span>
                      </div>
                    </button>
                  );
                })
              )}
            </CardContent>
          </Card>
        </div>

        <Card className="flex min-h-0 flex-col lg:col-span-8">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium">Transactions</CardTitle>
          </CardHeader>
          <CardContent className="min-h-0 flex-1 pb-0">
            <TransactionTable
              transactions={tableTransactions}
              totalCount={transactionsTotalCount}
              filteredTotals={null}
              queryState={transactionsQueryState}
              categories={categories}
              accounts={accounts}
              onUpdateTransaction={handleUpdateTransaction}
              onDeleteTransaction={handleDeleteTransaction}
              onBulkUpdate={handleBulkUpdate}
              basePath="/category-spending"
              showToolbar={false}
              columns={categorySpendingTransactionColumns}
            />
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
