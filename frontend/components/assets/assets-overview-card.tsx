"use client";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { AssetsStackedBar } from "./assets-stacked-bar";
import { AssetsTable } from "./assets-table";
import type { AssetsOverviewData } from "./types";

interface AssetsOverviewCardProps {
  data: AssetsOverviewData;
}

function formatCurrency(value: number, currency: string): string {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency,
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  }).format(value);
}

export function AssetsOverviewCard({ data }: AssetsOverviewCardProps) {
  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <CardTitle>Assets Overview</CardTitle>
          <span className="text-2xl font-bold">
            {formatCurrency(data.total, data.currency)}
          </span>
        </div>
      </CardHeader>
      <CardContent className="space-y-6">
        <AssetsStackedBar categories={data.categories} total={data.total} />
        <AssetsTable categories={data.categories} currency={data.currency} />
      </CardContent>
    </Card>
  );
}
