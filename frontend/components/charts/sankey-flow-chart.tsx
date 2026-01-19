"use client";

import * as React from "react";
import { Sankey, Tooltip, Rectangle, ResponsiveContainer } from "recharts";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { formatCurrency } from "@/lib/utils";

interface SankeyNode {
  name: string;
}

interface SankeyLink {
  source: number;
  target: number;
  value: number;
}

interface SankeyFlowChartProps {
  data: {
    nodes: SankeyNode[];
    links: SankeyLink[];
  };
  currency: string;
  subtitle?: string;
  isLoading?: boolean;
}

function SankeyFlowChartSkeleton() {
  return (
    <Card className="col-span-full">
      <CardHeader>
        <Skeleton className="h-5 w-32" />
      </CardHeader>
      <CardContent>
        <Skeleton className="h-[400px] w-full" />
      </CardContent>
    </Card>
  );
}

interface CustomNodeProps {
  x?: number;
  y?: number;
  width?: number;
  height?: number;
  index?: number;
  payload?: SankeyNode & { value?: number; depth?: number };
}

// Custom node component for better styling
function CustomNode(props: CustomNodeProps) {
  const { x = 0, y = 0, width = 0, height = 0, index = 0, payload } = props;

  if (!payload) return null;

  // Use depth to determine side: depth 0 = income (left), depth 1 = expenses (right)
  const isLeftSide = payload.depth === 0;

  // Color based on position: income sources (left), expenses (right)
  let fillColor: string;
  if (isLeftSide) {
    fillColor = "#e7e5e4"; // stone-200
  } else {
    fillColor = "#a8a29e"; // stone-400
  }

  return (
    <g key={`node-${index}`}>
      <Rectangle
        x={x}
        y={y}
        width={width}
        height={height}
        fill={fillColor}
        fillOpacity={1}
      />
      <text
        x={isLeftSide ? x - 8 : x + width + 8}
        y={y + height / 2}
        textAnchor={isLeftSide ? "end" : "start"}
        dominantBaseline="middle"
        fill="#e7e5e4"
        fontSize={12}
        fontWeight={500}
        style={{ fontFamily: "var(--font-mono, monospace)" }}
      >
        {payload.name}
      </text>
    </g>
  );
}

interface TooltipPayload {
  name: string;
  value: number;
  payload: {
    source?: SankeyNode;
    target?: SankeyNode;
    value: number;
    name?: string;
  };
}

interface CustomTooltipProps {
  active?: boolean;
  payload?: TooltipPayload[];
  currency: string;
}

function CustomTooltip({ active, payload, currency }: CustomTooltipProps) {
  if (!active || !payload?.length) {
    return null;
  }

  const data = payload[0].payload;

  // Node tooltip
  if (data.name) {
    return (
      <div className="border-border/50 bg-background min-w-[140px] border px-3 py-2.5 text-xs shadow-xl">
        <div className="mb-1 font-medium">{data.name}</div>
        <div className="text-muted-foreground">
          Total: <span className="font-mono font-medium text-foreground">{formatCurrency(data.value, currency)}</span>
        </div>
      </div>
    );
  }

  // Link tooltip
  if (data.source && data.target) {
    return (
      <div className="border-border/50 bg-background min-w-[180px] border px-3 py-2.5 text-xs shadow-xl">
        <div className="mb-2 font-medium">
          {data.source.name} → {data.target.name}
        </div>
        <div className="text-muted-foreground">
          Amount: <span className="font-mono font-medium text-foreground">{formatCurrency(data.value, currency)}</span>
        </div>
      </div>
    );
  }

  return null;
}

export function SankeyFlowChart({
  data,
  currency,
  subtitle,
  isLoading = false,
}: SankeyFlowChartProps) {
  if (isLoading) {
    return <SankeyFlowChartSkeleton />;
  }

  // Don't render if no data
  if (!data.nodes.length || !data.links.length) {
    return (
      <Card className="col-span-full">
        <CardHeader className="pb-2">
          <CardTitle className="text-sm font-medium">Cash Flow</CardTitle>
          {subtitle && (
            <p className="text-xs text-muted-foreground">{subtitle}</p>
          )}
        </CardHeader>
        <CardContent className="flex h-[400px] items-center justify-center">
          <p className="text-muted-foreground text-sm">
            No transaction data available for cash flow visualization
          </p>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card className="col-span-full">
      <CardHeader className="pb-2">
        <CardTitle className="text-sm font-medium">Cash Flow</CardTitle>
        {subtitle && (
          <p className="text-xs text-muted-foreground">{subtitle}</p>
        )}
      </CardHeader>
      <CardContent className="pt-0">
        <div className="h-[400px] w-full">
          <ResponsiveContainer width="100%" height="100%">
            <Sankey
              data={data}
              nodePadding={24}
              nodeWidth={8}
              margin={{ top: 24, right: 180, bottom: 24, left: 180 }}
              iterations={64}
              node={<CustomNode />}
              link={{ stroke: "#78716c", strokeOpacity: 0.4 }}
            >
              <Tooltip
                content={<CustomTooltip currency={currency} />}
                cursor={false}
              />
            </Sankey>
          </ResponsiveContainer>
        </div>
      </CardContent>
    </Card>
  );
}
