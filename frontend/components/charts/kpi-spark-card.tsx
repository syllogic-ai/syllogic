"use client";

import * as React from "react";
import { Area, AreaChart, ResponsiveContainer } from "recharts";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { cn, formatCurrency } from "@/lib/utils";

interface SparkDataPoint {
  date: string;
  value: number;
}

interface KpiSparkCardProps {
  title: string;
  value: number;
  currency: string;
  subtitle: string;
  sparkData: SparkDataPoint[];
  trend?: {
    value: number;
    isPositive: boolean;
  };
  icon?: React.ReactNode;
  isLoading?: boolean;
}

function KpiSparkCardSkeleton() {
  return (
    <Card>
      <CardContent className="flex items-center justify-between p-6">
        <div className="space-y-2">
          <Skeleton className="h-3 w-20" />
          <Skeleton className="h-8 w-32" />
          <Skeleton className="h-3 w-24" />
        </div>
        <Skeleton className="h-12 w-24" />
      </CardContent>
    </Card>
  );
}

export function KpiSparkCard({
  title,
  value,
  currency,
  subtitle,
  sparkData,
  trend,
  icon,
  isLoading = false,
}: KpiSparkCardProps) {
  // Generate unique ID for gradient to avoid conflicts with multiple charts
  const gradientId = React.useId();

  if (isLoading) {
    return <KpiSparkCardSkeleton />;
  }

  const formattedValue = formatCurrency(value, currency);

  return (
    <Card>
      <CardContent className="flex items-center justify-between p-6">
        <div className="space-y-1">
          <div className="flex items-center gap-2">
            {icon && (
              <span className="text-muted-foreground">{icon}</span>
            )}
            <p className="text-xs font-medium text-muted-foreground">
              {title}
            </p>
          </div>
          <p className="font-mono text-2xl font-semibold tracking-tight">
            {formattedValue}
          </p>
          <div className="flex items-center gap-2">
            <p className="text-xs text-muted-foreground">{subtitle}</p>
            {trend && (
              <span
                className={cn(
                  "text-xs font-medium",
                  trend.isPositive ? "text-emerald-600" : "text-red-600"
                )}
              >
                {trend.isPositive ? "+" : ""}
                {trend.value.toFixed(1)}%
              </span>
            )}
          </div>
        </div>
        {sparkData.length > 0 && (
          <div className="h-12 w-24 text-foreground">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart
                data={sparkData}
                margin={{ top: 0, right: 0, left: 0, bottom: 0 }}
              >
                <defs>
                  <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
                    <stop
                      offset="0%"
                      stopColor="currentColor"
                      stopOpacity={0.3}
                    />
                    <stop
                      offset="100%"
                      stopColor="currentColor"
                      stopOpacity={0}
                    />
                  </linearGradient>
                </defs>
                <Area
                  type="monotone"
                  dataKey="value"
                  stroke="currentColor"
                  strokeWidth={1.5}
                  fill={`url(#${gradientId})`}
                  dot={false}
                  isAnimationActive={false}
                />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
