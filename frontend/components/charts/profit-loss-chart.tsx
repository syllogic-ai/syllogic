"use client";

import * as React from "react";
import {
  Bar,
  ComposedChart,
  ReferenceLine,
  XAxis,
  YAxis,
  CartesianGrid,
  Legend,
} from "recharts";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import {
  ChartContainer,
  ChartConfig,
  ChartTooltip,
  ChartTooltipContent,
} from "@/components/ui/chart";

interface IncomeExpenseDataPoint {
  month: string;
  income: number;
  expenses: number;
}

interface ProfitLossChartProps {
  data: IncomeExpenseDataPoint[];
  currency: string;
  average?: number;
  isLoading?: boolean;
}

function formatCompactNumber(value: number): string {
  if (Math.abs(value) >= 1000) {
    return `${(value / 1000).toFixed(0)}k`;
  }
  return value.toString();
}

function formatCurrency(value: number, currency: string): string {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: currency,
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  }).format(value);
}

const chartConfig = {
  income: {
    label: "Income",
    theme: {
      light: "oklch(0.147 0.004 49.25)",   // near black in light mode
      dark: "oklch(0.985 0.001 106.423)",  // near white in dark mode
    },
  },
  expenses: {
    label: "Expenses",
    theme: {
      light: "oklch(0.553 0.013 58.071)",  // muted gray in light mode
      dark: "oklch(0.553 0.013 58.071)",   // muted gray in dark mode
    },
  },
} satisfies ChartConfig;

function ProfitLossChartSkeleton() {
  return (
    <Card className="col-span-3">
      <CardHeader>
        <Skeleton className="h-5 w-32" />
      </CardHeader>
      <CardContent>
        <Skeleton className="h-[300px] w-full" />
      </CardContent>
    </Card>
  );
}

export function ProfitLossChart({
  data,
  currency,
  average,
  isLoading = false,
}: ProfitLossChartProps) {
  if (isLoading) {
    return <ProfitLossChartSkeleton />;
  }

  return (
    <Card className="col-span-3">
      <CardHeader className="flex flex-row items-center justify-between pb-2">
        <CardTitle className="text-sm font-medium">Income vs Expenses</CardTitle>
      </CardHeader>
      <CardContent className="pt-0">
        <ChartContainer config={chartConfig} className="h-[300px] w-full">
          <ComposedChart
            data={data}
            margin={{ top: 20, right: 20, left: 0, bottom: 0 }}
            barCategoryGap="20%"
          >
            <CartesianGrid
              strokeDasharray="3 3"
              stroke="var(--border)"
              vertical={false}
            />
            <XAxis
              dataKey="month"
              axisLine={false}
              tickLine={false}
              tick={{ fontSize: 12, fill: "var(--muted-foreground)" }}
              tickMargin={8}
            />
            <YAxis
              axisLine={false}
              tickLine={false}
              tick={{ fontSize: 12, fill: "var(--muted-foreground)" }}
              tickFormatter={(value) => formatCompactNumber(value)}
              tickMargin={8}
              width={50}
            />
            <ChartTooltip
              content={
                <ChartTooltipContent
                  formatter={(value, name) => (
                    <span className="font-mono">
                      {formatCurrency(value as number, currency)}
                    </span>
                  )}
                />
              }
            />
            <Legend
              verticalAlign="top"
              align="right"
              wrapperStyle={{ paddingBottom: 20 }}
              formatter={(value) => (
                <span className="text-xs text-muted-foreground">{value}</span>
              )}
            />
            {average !== undefined && (
              <ReferenceLine
                y={average}
                stroke="var(--muted-foreground)"
                strokeDasharray="5 5"
                strokeWidth={1}
                label={{
                  value: `Avg: ${formatCompactNumber(average)}`,
                  position: "right",
                  fill: "var(--muted-foreground)",
                  fontSize: 11,
                }}
              />
            )}
            <Bar
              dataKey="income"
              fill="var(--color-income)"
              radius={[0, 0, 0, 0]}
              maxBarSize={40}
            />
            <Bar
              dataKey="expenses"
              fill="var(--color-expenses)"
              radius={[0, 0, 0, 0]}
              maxBarSize={40}
            />
          </ComposedChart>
        </ChartContainer>
      </CardContent>
    </Card>
  );
}
