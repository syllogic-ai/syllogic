"use client";

import * as React from "react";
import { Sankey, Tooltip, Rectangle, ResponsiveContainer } from "recharts";
import { useRouter } from "next/navigation";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { formatCurrency } from "@/lib/utils";
import { buildTransactionsDrilldownQuery } from "@/lib/dashboard/drilldown-query";

interface SankeyNode {
  name: string;
  categoryId?: string | null;
  categoryType?: "income" | "expense";
  total?: number;
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
  accountIds?: string[];
  dateFrom?: string;
  dateTo?: string;
  horizon?: number;
}

const getCategoryKey = (node?: SankeyNode | null) =>
  node?.categoryId ?? node?.name ?? "uncategorized";

interface SelectedCategory {
  key: string;
  type: "income" | "expense";
}

const INCOME_HIGHLIGHT = "#10B981";
const EXPENSE_HIGHLIGHT = "#EF4444";

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
  selectedCategory?: SelectedCategory | null;
}

function CustomNode(props: CustomNodeProps) {
  const {
    x = 0,
    y = 0,
    width = 0,
    height = 0,
    index = 0,
    payload,
    selectedCategory,
  } = props;

  if (!payload) return null;

  const isLeftSide = payload.depth === 0;
  const isClickable =
    payload.categoryType === "income" ||
    payload.categoryType === "expense" ||
    payload.depth === 0 ||
    payload.depth === 1;
  const nodeKey = getCategoryKey(payload);
  const isSelected = Boolean(selectedCategory && nodeKey === selectedCategory.key);

  let fillColor: string;
  if (isLeftSide) {
    fillColor = "#e7e5e4"; // stone-200
  } else {
    fillColor = "#a8a29e"; // stone-400
  }

  if (isSelected) {
    fillColor = selectedCategory?.type === "income" ? INCOME_HIGHLIGHT : EXPENSE_HIGHLIGHT;
  }

  return (
    <g key={`node-${index}`} style={{ cursor: isClickable ? "pointer" : "default" }}>
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

interface CustomLinkProps {
  sourceX?: number;
  sourceY?: number;
  targetX?: number;
  targetY?: number;
  sourceControlX?: number;
  targetControlX?: number;
  linkWidth?: number;
  index?: number;
  payload?: {
    source?: SankeyNode;
    target?: SankeyNode;
    value?: number;
  };
  selectedCategory?: SelectedCategory | null;
}

function CustomLink({
  sourceX = 0,
  sourceY = 0,
  targetX = 0,
  targetY = 0,
  sourceControlX = 0,
  targetControlX = 0,
  linkWidth = 1,
  index = 0,
  payload,
  selectedCategory,
}: CustomLinkProps) {
  const targetKey = getCategoryKey(payload?.target);
  const sourceKey = getCategoryKey(payload?.source);
  const hasSelection = Boolean(selectedCategory);
  const isSelected = selectedCategory
    ? selectedCategory.type === "income"
      ? sourceKey === selectedCategory.key
      : targetKey === selectedCategory.key
    : false;
  const highlightColor = selectedCategory?.type === "income" ? INCOME_HIGHLIGHT : EXPENSE_HIGHLIGHT;
  const strokeColor = isSelected ? highlightColor : "#78716c";
  const gradientStartOpacity = isSelected ? 0.85 : hasSelection ? 0.15 : 0.5;
  const gradientEndOpacity = isSelected ? 0.12 : hasSelection ? 0.04 : 0.15;
  const reverseGradient = isSelected && selectedCategory?.type === "expense";
  const gradientId = `sankey-link-${index}-${isSelected ? "active" : "idle"}-${selectedCategory?.type ?? "none"}`;
  const gradientX1 = reverseGradient ? targetX : sourceX;
  const gradientY1 = reverseGradient ? targetY : sourceY;
  const gradientX2 = reverseGradient ? sourceX : targetX;
  const gradientY2 = reverseGradient ? sourceY : targetY;

  return (
    <g>
      <defs>
        <linearGradient
          id={gradientId}
          gradientUnits="userSpaceOnUse"
          x1={gradientX1}
          y1={gradientY1}
          x2={gradientX2}
          y2={gradientY2}
        >
          <stop offset="0%" stopColor={strokeColor} stopOpacity={gradientStartOpacity} />
          <stop offset="100%" stopColor={strokeColor} stopOpacity={gradientEndOpacity} />
        </linearGradient>
      </defs>
      <path
        d={`M${sourceX},${sourceY}C${sourceControlX},${sourceY} ${targetControlX},${targetY} ${targetX},${targetY}`}
        stroke={`url(#${gradientId})`}
        strokeWidth={Math.max(1, linkWidth)}
        fill="none"
      />
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
    total?: number;
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

  if (data.name) {
    const total = data.total ?? data.value ?? 0;
    return (
      <div className="border-border/50 bg-background min-w-[140px] border px-3 py-2.5 text-xs shadow-xl">
        <div className="mb-1 font-medium">{data.name}</div>
        <div className="text-muted-foreground">
          Total: <span className="font-mono font-medium text-foreground">{formatCurrency(total, currency)}</span>
        </div>
      </div>
    );
  }

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
  accountIds,
  dateFrom,
  dateTo,
  horizon,
}: SankeyFlowChartProps) {
  const router = useRouter();
  const [selectedCategory, setSelectedCategory] = React.useState<SelectedCategory | null>(null);

  const navigateToTransactions = React.useCallback(
    (categoryId?: string | null) => {
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

  const selectedNode = selectedCategory?.key
    ? data.nodes.find((node) => getCategoryKey(node) === selectedCategory.key) ?? null
    : null;

  const selectedTotal = (() => {
    if (!selectedCategory?.key) return null;
    if (typeof selectedNode?.total === "number") {
      return selectedNode.total;
    }
    let total = 0;
    data.links.forEach((link) => {
      if (selectedCategory.type === "income") {
        const sourceNode = data.nodes[link.source];
        if (getCategoryKey(sourceNode) === selectedCategory.key) {
          total += link.value;
        }
      } else {
        const targetNode = data.nodes[link.target];
        if (getCategoryKey(targetNode) === selectedCategory.key) {
          total += link.value;
        }
      }
    });
    return total;
  })();

  React.useEffect(() => {
    if (!selectedCategory?.key) return;
    const stillExists = data.nodes.some(
      (node) => getCategoryKey(node) === selectedCategory.key
    );
    if (!stillExists) {
      setSelectedCategory(null);
    }
  }, [data.nodes, selectedCategory?.key]);

  interface SankeyClickEvent {
    payload?: SankeyNode & { depth?: number };
  }

  const handleSankeyClick = React.useCallback(
    (el: SankeyClickEvent | undefined, type: string) => {
      if (type !== "node" || !el?.payload) return;
      const categoryKey = getCategoryKey(el.payload);
      const categoryId = el.payload.categoryId;
      const categoryType: SelectedCategory["type"] =
        el.payload.categoryType ?? (el.payload.depth === 0 ? "income" : "expense");

      if (selectedCategory?.key === categoryKey) {
        if (categoryId) {
          navigateToTransactions(categoryId);
        }
        return;
      }

      setSelectedCategory({ key: categoryKey, type: categoryType });
    },
    [navigateToTransactions, selectedCategory?.key]
  );

  if (isLoading) {
    return <SankeyFlowChartSkeleton />;
  }

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
        {selectedNode && selectedTotal !== null && (
          <p className="text-xs text-muted-foreground mt-1">
            <span className="font-medium text-foreground">
              {selectedNode.name || "Unknown"}
            </span>
            <span className="ml-2 font-mono">
              {formatCurrency(selectedTotal, currency)}
            </span>
            <span className="ml-2">Click again to view transactions</span>
          </p>
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
              node={<CustomNode selectedCategory={selectedCategory} />}
              link={<CustomLink selectedCategory={selectedCategory} />}
              onClick={handleSankeyClick}
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
