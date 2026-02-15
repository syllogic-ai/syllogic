"use client";

import { useMemo, useState } from "react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import { SubscriptionsSummaryRow } from "./subscriptions-summary-row";
import { CompanyLogo } from "@/components/ui/company-logo";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import {
  RiAddLine,
  RiCheckLine,
  RiCloseLine,
  RiDeleteBinLine,
  RiEditLine,
  RiMoreLine,
} from "@remixicon/react";
import type { SubscriptionOrSuggestion } from "./subscriptions-client";
import {
  calculateMonthlyEquivalent,
  getCurrencyFallback,
} from "./subscription-math";
import { WeightBarVisualizer } from "@/components/assets/weight-bar-visualizer";
import type { SubscriptionKpis } from "@/lib/actions/subscriptions";
import { SubscriptionsKpiGrid } from "./subscriptions-kpi-grid";

interface SubscriptionsGroupedListProps {
  data: SubscriptionOrSuggestion[];
  kpis: SubscriptionKpis;
  onAdd: () => void;
  onEdit: (row: SubscriptionOrSuggestion) => void;
  onDelete: (row: SubscriptionOrSuggestion) => void;
  onToggleActive: (row: SubscriptionOrSuggestion) => void;
  onRowClick: (row: SubscriptionOrSuggestion) => void;
  onVerify: (row: SubscriptionOrSuggestion) => void;
  onDismiss: (row: SubscriptionOrSuggestion) => void;
}

interface CategoryGroup {
  key: string;
  name: string;
  color: string;
  items: SubscriptionOrSuggestion[];
  monthlyTotal: number;
  count: number;
  percentage: number;
}

const frequencyColors: Record<string, string> = {
  monthly: "bg-blue-500/10 text-blue-700 dark:text-blue-400",
  weekly: "bg-green-500/10 text-green-700 dark:text-green-400",
  yearly: "bg-purple-500/10 text-purple-700 dark:text-purple-400",
  quarterly: "bg-orange-500/10 text-orange-700 dark:text-orange-400",
  biweekly: "bg-cyan-500/10 text-cyan-700 dark:text-cyan-400",
};

const frequencyLabels: Record<string, string> = {
  monthly: "Monthly",
  weekly: "Weekly",
  yearly: "Yearly",
  quarterly: "Quarterly",
  biweekly: "Bi-weekly",
};

const UNCATEGORIZED_KEY = "uncategorized";
const UNCATEGORIZED_COLOR = "#6B7280";

function groupByCategory(
  items: SubscriptionOrSuggestion[],
  totalMonthly: number
): CategoryGroup[] {
  const map = new Map<string, CategoryGroup>();

  items.forEach((item) => {
    const category = item.category;
    const key = category?.id ?? UNCATEGORIZED_KEY;
    const name = category?.name ?? "Uncategorized";
    const color = category?.color ?? UNCATEGORIZED_COLOR;
    const existing = map.get(key);
    const monthly = calculateMonthlyEquivalent(item);

    if (existing) {
      existing.items.push(item);
      existing.monthlyTotal += monthly;
      existing.count += 1;
      return;
    }

    map.set(key, {
      key,
      name,
      color,
      items: [item],
      monthlyTotal: monthly,
      count: 1,
      percentage: 0,
    });
  });

  return Array.from(map.values())
    .map((group) => ({
      ...group,
      percentage: totalMonthly > 0 ? (group.monthlyTotal / totalMonthly) * 100 : 0,
      items: group.items
        .slice()
        .sort(
          (a, b) =>
            Math.abs(parseFloat(b.amount || "0")) -
            Math.abs(parseFloat(a.amount || "0"))
        ),
    }))
    .sort((a, b) => {
    if (b.monthlyTotal !== a.monthlyTotal) {
      return b.monthlyTotal - a.monthlyTotal;
    }
    return a.name.localeCompare(b.name);
  });
}

export function SubscriptionsGroupedList({
  data,
  kpis,
  onAdd,
  onEdit,
  onDelete,
  onToggleActive,
  onRowClick,
  onVerify,
  onDismiss,
}: SubscriptionsGroupedListProps) {
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);
  const [rowToDelete, setRowToDelete] =
    useState<SubscriptionOrSuggestion | null>(null);

  const handleDeleteClick = (row: SubscriptionOrSuggestion) => {
    setRowToDelete(row);
    setDeleteDialogOpen(true);
  };

  const handleConfirmDelete = () => {
    if (rowToDelete) {
      onDelete(rowToDelete);
    }
    setDeleteDialogOpen(false);
    setRowToDelete(null);
  };

  const subscriptionCount = data.filter((d) => !d.isSuggestion).length;
  const suggestionCount = data.filter((d) => d.isSuggestion).length;

  const { activeGroups, inactiveGroups, suggestionRows } = useMemo(() => {
    const active = data.filter((d) => !d.isSuggestion && d.isActive);
    const inactive = data.filter((d) => !d.isSuggestion && !d.isActive);
    const suggestions = data.filter((d) => d.isSuggestion);

    const totalMonthlyActive = active.reduce(
      (sumValue, item) => sumValue + calculateMonthlyEquivalent(item),
      0
    );

    return {
      activeGroups: groupByCategory(active, totalMonthlyActive),
      inactiveGroups: groupByCategory(inactive, totalMonthlyActive),
      suggestionRows: suggestions,
    };
  }, [data]);

  const renderCategoryHeader = (group: CategoryGroup, muted = false) => {
    const currency = getCurrencyFallback(group.items);

    return (
      <div
        className={cn(
          "flex items-center justify-between px-4 py-2 bg-muted/40 text-xs font-semibold uppercase text-muted-foreground",
          muted && "opacity-60"
        )}
      >
        <div className="flex items-center gap-2">
          <span
            className="h-2.5 w-2.5"
            style={{ backgroundColor: group.color, borderRadius: 9999 }}
          />
          <span className="text-sm font-semibold text-foreground">
            {group.name}
          </span>
        </div>
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2">
            <WeightBarVisualizer percentage={group.percentage} color={group.color} />
            <span className="text-xs font-medium">
              {group.percentage.toFixed(0)}%
            </span>
          </div>
          <span className="text-xs font-mono text-muted-foreground whitespace-nowrap">
            {group.monthlyTotal.toFixed(2)} {currency} / mo
          </span>
        </div>
      </div>
    );
  };

  const renderImportance = (importance: number | undefined, muted = false) => {
    const normalized = Math.min(importance || 2, 3);
    return (
      <div className={cn("flex gap-1", muted && "opacity-50")}>
        {Array.from({ length: 3 }).map((_, i) => (
          <div
            key={i}
            className={cn(
              "h-3 w-5 border",
              i < normalized
                ? "bg-foreground border-foreground"
                : "bg-background border-border"
            )}
          />
        ))}
      </div>
    );
  };

  const renderSubscriptionRow = (
    item: SubscriptionOrSuggestion,
    muted = false
  ) => {
    const amount = parseFloat(item.amount || "0");
    const currency = item.currency || "EUR";
    const frequencyLabel = frequencyLabels[item.frequency] || item.frequency;
    const frequencyClass =
      frequencyColors[item.frequency] || "bg-gray-500/10 text-gray-700";

    return (
      <div
        key={item.id}
        className={cn(
          "flex items-center gap-4 px-4 py-3 hover:bg-muted/40",
          !item.isSuggestion && "cursor-pointer",
          muted && "opacity-60"
        )}
        onClick={() => {
          if (!item.isSuggestion) {
            onRowClick(item);
          }
        }}
      >
        <div className="flex min-w-0 flex-1 items-center gap-3">
          <CompanyLogo name={item.name} logoUrl={item.logoUrl || null} size="sm" />
          <div className="min-w-0">
            <div className="truncate font-medium">{item.name}</div>
            {item.merchant && (
              <div className="truncate text-sm text-muted-foreground">
                {item.merchant}
              </div>
            )}
            {item.isSuggestion && (
              <div className="truncate text-xs text-muted-foreground">
                {item.confidence}% confidence
                {item.matchCount &&
                  ` | ${item.matchCount} txn${item.matchCount !== 1 ? "s" : ""}`}
              </div>
            )}
          </div>
        </div>

        <div className="hidden items-center gap-3 md:flex">
          <Badge variant="secondary" className={frequencyClass}>
            {frequencyLabel}
          </Badge>
          {!item.isSuggestion && renderImportance(item.importance, muted)}
        </div>

        <div className="flex items-center gap-3">
          <span className="whitespace-nowrap font-mono text-sm">
            {amount.toFixed(2)} {currency}
          </span>
          {!item.isSuggestion && (
            item.isActive ? (
              <Badge variant="default" className="bg-green-500/10 text-green-700">
                <RiCheckLine className="mr-1 h-3 w-3" />
                Active
              </Badge>
            ) : (
              <Badge variant="secondary" className="opacity-50">
                <RiCloseLine className="mr-1 h-3 w-3" />
                Inactive
              </Badge>
            )
          )}
          <div onClick={(event) => event.stopPropagation()}>
            {item.isSuggestion ? (
              <div className="flex items-center gap-1">
                <Button size="sm" variant="default" onClick={() => onVerify(item)}>
                  <RiCheckLine className="mr-1 h-3 w-3" />
                  Verify
                </Button>
                <Button size="sm" variant="ghost" onClick={() => onDismiss(item)}>
                  <RiCloseLine className="h-4 w-4" />
                </Button>
              </div>
            ) : (
              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <Button variant="ghost" className="h-8 w-8 p-0">
                    <RiMoreLine className="h-4 w-4" />
                  </Button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="end">
                  <DropdownMenuItem onClick={() => onEdit(item)}>
                    <RiEditLine className="mr-2 h-4 w-4" />
                    Edit
                  </DropdownMenuItem>
                  <DropdownMenuItem onClick={() => onToggleActive(item)}>
                    {item.isActive ? (
                      <>
                        <RiCloseLine className="mr-2 h-4 w-4" />
                        Deactivate
                      </>
                    ) : (
                      <>
                        <RiCheckLine className="mr-2 h-4 w-4" />
                        Activate
                      </>
                    )}
                  </DropdownMenuItem>
                  <DropdownMenuSeparator />
                  <DropdownMenuItem
                    onClick={() => handleDeleteClick(item)}
                    className="text-destructive"
                  >
                    <RiDeleteBinLine className="mr-2 h-4 w-4" />
                    Delete
                  </DropdownMenuItem>
                </DropdownMenuContent>
              </DropdownMenu>
            )}
          </div>
        </div>
      </div>
    );
  };

  return (
    <>
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <h2 className="text-lg font-semibold">Subscriptions</h2>
          <span className="text-sm text-muted-foreground">
            ({subscriptionCount})
          </span>
          {suggestionCount > 0 && (
            <span className="text-sm text-yellow-600">
              +{suggestionCount} suggestion{suggestionCount !== 1 ? "s" : ""}
            </span>
          )}
        </div>
        <Button onClick={onAdd}>
          <RiAddLine className="mr-2 h-4 w-4" />
          Add Subscription
        </Button>
      </div>

      <SubscriptionsKpiGrid kpis={kpis} />

      {activeGroups.length > 0 ? (
        <div className="space-y-6">
          {activeGroups.map((group) => (
            <div
              key={group.key}
              className="border border-border rounded-sm overflow-hidden"
            >
              {renderCategoryHeader(group)}
              <div className="divide-y">
                {group.items.map((item) => renderSubscriptionRow(item))}
              </div>
            </div>
          ))}
        </div>
      ) : (
        <div className="flex h-24 items-center justify-center text-sm text-muted-foreground border border-dashed rounded-sm">
          No active subscriptions.
        </div>
      )}

      {suggestionRows.length > 0 && (
        <div className="border border-border rounded-sm overflow-hidden">
          <div className="bg-muted/40 px-4 py-2 text-xs font-semibold uppercase text-muted-foreground">
            Suggestions
          </div>
          <div className="divide-y">
            {suggestionRows.map((item) => renderSubscriptionRow(item))}
          </div>
        </div>
      )}

      {inactiveGroups.length > 0 && (
        <div className="space-y-6">
          {inactiveGroups.map((group) => (
            <div
              key={group.key}
              className="border border-border rounded-sm overflow-hidden"
            >
              {renderCategoryHeader(group, true)}
              <div className="divide-y">
                {group.items.map((item) => renderSubscriptionRow(item, true))}
              </div>
            </div>
          ))}
        </div>
      )}

      <SubscriptionsSummaryRow data={data} />

      <AlertDialog open={deleteDialogOpen} onOpenChange={setDeleteDialogOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete Subscription?</AlertDialogTitle>
            <AlertDialogDescription>
              Are you sure you want to delete "{rowToDelete?.name}"? This action
              cannot be undone. Linked transactions will be unlinked but not
              deleted.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
              onClick={handleConfirmDelete}
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
            >
              Delete
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  );
}
