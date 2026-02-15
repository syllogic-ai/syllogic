"use client";

import * as React from "react";
import { useRouter } from "next/navigation";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { formatCurrency } from "@/lib/utils";
import { buildTransactionsDrilldownQuery } from "@/lib/dashboard/drilldown-query";

interface CategoryData {
  id: string | null;
  name: string | null;
  amount: number;
  icon?: string | null;
  color?: string | null;
}

interface SpendingByCategoryChartProps {
  data: CategoryData[];
  total: number;
  currency: string;
  limit?: number;
  isLoading?: boolean;
  periodTitle?: string;
  accountIds?: string[];
  dateFrom?: string;
  dateTo?: string;
  horizon?: number;
}

// Graduated opacity levels for grayscale bars (highest first)
const OPACITY_LEVELS = [1, 0.8, 0.6, 0.45, 0.3];

function SpendingByCategoryChartSkeleton() {
  return (
    <Card className="col-span-2">
      <CardHeader className="flex flex-row items-center justify-between pb-2">
        <Skeleton className="h-5 w-32" />
        <Skeleton className="h-8 w-24" />
      </CardHeader>
      <CardContent className="space-y-4">
        {Array.from({ length: 5 }).map((_, i) => (
          <div key={i} className="space-y-2">
            <div className="flex items-center justify-between">
              <Skeleton className="h-4 w-24" />
              <Skeleton className="h-4 w-16" />
            </div>
            <Skeleton className="h-2 w-full" />
          </div>
        ))}
      </CardContent>
    </Card>
  );
}

export function SpendingByCategoryChart({
  data,
  total,
  currency,
  limit = 5,
  isLoading = false,
  periodTitle = "30-Day",
  accountIds,
  dateFrom,
  dateTo,
  horizon,
}: SpendingByCategoryChartProps) {
  const router = useRouter();

  const navigateToTransactions = React.useCallback(
    (categoryId: string | null) => {
      if (!categoryId) return;
      const query = buildTransactionsDrilldownQuery({
        categoryId,
        accountIds,
        dateFrom,
        dateTo,
        horizon,
      });
      router.push(`/transactions?${query}`);
    },
    [accountIds, dateFrom, dateTo, horizon, router]
  );

  if (isLoading) {
    return <SpendingByCategoryChartSkeleton />;
  }

  const displayData = data.slice(0, limit);
  const maxAmount = Math.max(...displayData.map((d) => d.amount), 1);

  return (
    <Card className="col-span-2">
      <CardHeader className="pb-4">
        <div className="flex flex-row items-center justify-between">
          <CardTitle className="text-sm font-medium">{periodTitle} Expenses</CardTitle>
          <span className="font-mono text-2xl font-semibold tracking-tight">
            {formatCurrency(total, currency)}
          </span>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        {displayData.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            No expense data for this period
          </p>
        ) : (
          displayData.map((category, index) => {
            const percentage = (category.amount / maxAmount) * 100;
            const opacity = OPACITY_LEVELS[index % OPACITY_LEVELS.length];
            const categoryKey = category.id ?? "uncategorized";

            return (
              <div
                key={category.id || index}
                className="space-y-1.5 rounded-md px-2 py-1 transition-colors hover:bg-muted/30 cursor-pointer"
                onClick={() => {
                  navigateToTransactions(categoryKey);
                }}
              >
                <div className="flex items-center justify-between text-sm">
                  <span className="truncate font-medium">{category.name || "Unknown"}</span>
                  <span className="font-mono text-muted-foreground">
                    {formatCurrency(category.amount, currency)}
                  </span>
                </div>
                <div className="relative h-2 w-full bg-muted">
                  <div
                    className="absolute left-0 top-0 h-full bg-foreground transition-all duration-500"
                    style={{
                      width: `${percentage}%`,
                      opacity: opacity,
                    }}
                  />
                </div>
              </div>
            );
          })
        )}
      </CardContent>
    </Card>
  );
}
