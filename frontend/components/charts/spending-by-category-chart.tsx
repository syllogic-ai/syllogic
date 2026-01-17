"use client";

import * as React from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";

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
}

function formatCurrency(value: number, currency: string): string {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: currency,
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  }).format(value);
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
}: SpendingByCategoryChartProps) {
  if (isLoading) {
    return <SpendingByCategoryChartSkeleton />;
  }

  const displayData = data.slice(0, limit);
  const maxAmount = Math.max(...displayData.map((d) => d.amount), 1);

  return (
    <Card className="col-span-2">
      <CardHeader className="flex flex-row items-center justify-between pb-4">
        <CardTitle className="text-sm font-medium">Monthly Expenses</CardTitle>
        <span className="font-mono text-2xl font-semibold tracking-tight">
          {formatCurrency(total, currency)}
        </span>
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

            return (
              <div key={category.id || index} className="space-y-1.5">
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
