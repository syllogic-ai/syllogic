"use client";

import * as React from "react";
import { Label, Pie, PieChart, Sector } from "recharts";
import type { PieSectorDataItem } from "recharts/types/polar/Pie";
import { Card, CardContent, CardFooter, CardHeader, CardTitle } from "@/components/ui/card";
import {
  ChartContainer,
  ChartTooltip,
  ChartTooltipContent,
  type ChartConfig,
} from "@/components/ui/chart";
import { formatCurrency } from "@/lib/utils";
import type { CategorySpendingCategory } from "@/lib/actions/category-spending";

interface CategorySpendingDonutChartProps {
  data: CategorySpendingCategory[];
  total: number;
  currency: string;
  selectedCategoryIds: string[];
  selectedTotal: number;
  onToggleCategory: (categoryId: string) => void;
}

const chartConfig = {
  amount: {
    label: "Spending",
  },
} satisfies ChartConfig;

export function CategorySpendingDonutChart({
  data,
  total,
  currency,
  selectedCategoryIds,
  selectedTotal,
  onToggleCategory,
}: CategorySpendingDonutChartProps) {
  const selectedCategorySet = React.useMemo(
    () => new Set(selectedCategoryIds),
    [selectedCategoryIds]
  );

  const selectedCategories = React.useMemo(
    () => data.filter((item) => selectedCategorySet.has(item.id)),
    [data, selectedCategorySet]
  );

  const activeIndex = React.useMemo(() => {
    const indexes = data
      .map((item, index) => (selectedCategorySet.has(item.id) ? index : -1))
      .filter((index) => index >= 0);

    return indexes.length > 0 ? indexes : undefined;
  }, [data, selectedCategorySet]);

  const selectedSharePct = total > 0 ? (selectedTotal / total) * 100 : 0;

  return (
    <Card className="flex flex-col">
      <CardHeader className="pb-2">
        <CardTitle className="text-sm font-medium">Spending Share</CardTitle>
      </CardHeader>
      <CardContent className="pb-0">
        {data.length === 0 ? (
          <div className="flex h-[220px] items-center justify-center text-sm text-muted-foreground">
            No category spending for this period
          </div>
        ) : (
          <ChartContainer
            config={chartConfig}
            className="mx-auto aspect-square max-h-[220px] max-w-[220px]"
          >
            <PieChart>
              <ChartTooltip
                cursor={false}
                content={
                  <ChartTooltipContent
                    hideLabel
                    formatter={(value, name, item) => {
                      const sharePct =
                        typeof item?.payload?.sharePct === "number"
                          ? item.payload.sharePct
                          : 0;

                      return (
                        <div className="w-full space-y-1">
                          <div className="font-medium text-foreground">{String(name)}</div>
                          <div className="flex items-center justify-between gap-3">
                            <span className="text-muted-foreground">Amount</span>
                            <span className="font-mono font-medium text-foreground">
                              {formatCurrency(Number(value), currency)}
                            </span>
                          </div>
                          <div className="flex items-center justify-between gap-3">
                            <span className="text-muted-foreground">Share</span>
                            <span className="font-mono font-medium text-foreground">
                              {sharePct.toFixed(1)}%
                            </span>
                          </div>
                        </div>
                      );
                    }}
                  />
                }
              />
              <Pie
                data={data}
                dataKey="amount"
                nameKey="name"
                innerRadius={60}
                strokeWidth={5}
                activeIndex={activeIndex}
                activeShape={({ outerRadius = 0, ...props }: PieSectorDataItem) => (
                  <Sector {...props} outerRadius={outerRadius + 10} />
                )}
                onClick={(_, index) => {
                  const nextCategory = data[index];
                  if (nextCategory) {
                    onToggleCategory(nextCategory.id);
                  }
                }}
              >
                <Label
                  position="center"
                  content={({ viewBox }) => {
                    if (
                      !viewBox ||
                      !("cx" in viewBox) ||
                      !("cy" in viewBox) ||
                      typeof viewBox.cx !== "number" ||
                      typeof viewBox.cy !== "number"
                    ) {
                      return null;
                    }

                    const centerX = viewBox.cx;
                    const centerY = viewBox.cy;

                    return (
                      <text
                        x={centerX}
                        y={centerY}
                        textAnchor="middle"
                        dominantBaseline="middle"
                      >
                        <tspan
                          x={centerX}
                          y={centerY - 2}
                          className="fill-foreground font-mono text-sm font-semibold"
                        >
                          {formatCurrency(total, currency)}
                        </tspan>
                        <tspan
                          x={centerX}
                          y={centerY + 14}
                          className="fill-muted-foreground text-[11px]"
                        >
                          Total spend
                        </tspan>
                      </text>
                    );
                  }}
                />
              </Pie>
            </PieChart>
          </ChartContainer>
        )}
      </CardContent>
      <CardFooter className="pt-2">
        {selectedCategories.length === 1 ? (
          <div className="flex w-full items-center justify-between gap-3 text-sm">
            <span className="truncate font-medium">{selectedCategories[0].name}</span>
            <span className="shrink-0 font-mono text-muted-foreground">
              {formatCurrency(selectedCategories[0].amount, currency)} ({selectedCategories[0].sharePct.toFixed(1)}%)
            </span>
          </div>
        ) : selectedCategories.length > 1 ? (
          <div className="flex w-full items-center justify-between gap-3 text-sm">
            <span className="truncate font-medium">
              {selectedCategories.length} selected categories
            </span>
            <span className="shrink-0 font-mono text-muted-foreground">
              {formatCurrency(selectedTotal, currency)} ({selectedSharePct.toFixed(1)}%)
            </span>
          </div>
        ) : (
          <p className="text-sm text-muted-foreground">Select one or more slices for details</p>
        )}
      </CardFooter>
    </Card>
  );
}
