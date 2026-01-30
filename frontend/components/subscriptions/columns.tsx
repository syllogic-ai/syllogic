"use client";

import { type ColumnDef } from "@tanstack/react-table";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import {
  RiMoreLine,
  RiEditLine,
  RiDeleteBinLine,
  RiCheckLine,
  RiCloseLine,
  RiLightbulbLine,
} from "@remixicon/react";
import type { SubscriptionOrSuggestion } from "./subscriptions-client";

interface ColumnsProps {
  onEdit: (row: SubscriptionOrSuggestion) => void;
  onDelete: (row: SubscriptionOrSuggestion) => void;
  onToggleActive: (row: SubscriptionOrSuggestion) => void;
  onVerify: (row: SubscriptionOrSuggestion) => void;
  onDismiss: (row: SubscriptionOrSuggestion) => void;
}

// Frequency badge colors
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

export const createSubscriptionColumns = ({
  onEdit,
  onDelete,
  onToggleActive,
  onVerify,
  onDismiss,
}: ColumnsProps): ColumnDef<SubscriptionOrSuggestion>[] => [
  {
    accessorKey: "name",
    header: "Name",
    cell: ({ row }) => {
      const isSuggestion = row.original.isSuggestion;
      const merchant = row.original.merchant;
      const isActive = row.original.isActive;
      const confidence = row.original.confidence;
      const matchCount = row.original.matchCount;

      return (
        <div className={!isSuggestion && !isActive ? "opacity-50" : ""}>
          <div className="flex items-center gap-2">
            {isSuggestion && (
              <RiLightbulbLine className="h-4 w-4 text-yellow-500 flex-shrink-0" />
            )}
            <div>
              <div className="font-medium">{row.getValue("name")}</div>
              {merchant && (
                <div className="text-sm text-muted-foreground">{merchant}</div>
              )}
              {isSuggestion && (
                <div className="text-xs text-muted-foreground">
                  {confidence}% confidence
                  {matchCount && ` | ${matchCount} transaction${matchCount !== 1 ? "s" : ""}`}
                </div>
              )}
            </div>
          </div>
        </div>
      );
    },
    size: 200,
  },
  {
    accessorKey: "amount",
    header: "Amount",
    cell: ({ row }) => {
      const amount = parseFloat(row.getValue("amount"));
      const currency = row.original.currency || "EUR";
      const isSuggestion = row.original.isSuggestion;
      const isActive = row.original.isActive;
      return (
        <span className={`font-mono ${!isSuggestion && !isActive ? "opacity-50" : ""}`}>
          {amount.toFixed(2)} {currency}
        </span>
      );
    },
    size: 120,
  },
  {
    accessorKey: "category",
    header: "Category",
    cell: ({ row }) => {
      const category = row.original.category;
      const isSuggestion = row.original.isSuggestion;
      const isActive = row.original.isActive;

      if (isSuggestion) {
        return (
          <span className="text-muted-foreground text-sm">-</span>
        );
      }

      return category ? (
        <span
          className={`inline-flex items-center px-2 py-0.5 text-xs text-white ${
            isActive ? "" : "opacity-50"
          }`}
          style={{ backgroundColor: category.color ?? "#6B7280" }}
        >
          {category.name}
        </span>
      ) : (
        <span className={`text-muted-foreground ${isActive ? "" : "opacity-50"}`}>
          Uncategorized
        </span>
      );
    },
    size: 160,
  },
  {
    accessorKey: "importance",
    header: "Importance",
    cell: ({ row }) => {
      const isSuggestion = row.original.isSuggestion;

      if (isSuggestion) {
        return <span className="text-muted-foreground text-sm">-</span>;
      }

      // Cap display at 3 for existing subscriptions with higher values
      const importance = Math.min((row.getValue("importance") as number) || 2, 3);
      const isActive = row.original.isActive;
      const importanceLabel = importance === 3 ? "High importance" : importance === 2 ? "Medium importance" : "Low importance";
      return (
        <div
          className={`flex gap-1 ${isActive ? "" : "opacity-50"}`}
          title={importanceLabel}
        >
          {Array.from({ length: 3 }).map((_, i) => (
            <div
              key={i}
              className={`h-3 w-5 border ${
                i < importance
                  ? "bg-foreground border-foreground"
                  : "bg-background border-border"
              }`}
            />
          ))}
        </div>
      );
    },
    size: 100,
  },
  {
    accessorKey: "frequency",
    header: "Frequency",
    cell: ({ row }) => {
      const frequency = row.getValue("frequency") as string;
      const isSuggestion = row.original.isSuggestion;
      const isActive = row.original.isActive;
      const colorClass = frequencyColors[frequency] || "bg-gray-500/10 text-gray-700";
      return (
        <Badge
          variant="secondary"
          className={`${colorClass} ${!isSuggestion && !isActive ? "opacity-50" : ""}`}
        >
          {frequencyLabels[frequency] || frequency}
        </Badge>
      );
    },
    size: 110,
  },
  {
    accessorKey: "isActive",
    header: "Status",
    cell: ({ row }) => {
      const isSuggestion = row.original.isSuggestion;

      if (isSuggestion) {
        return (
          <Badge variant="outline" className="bg-yellow-500/10 text-yellow-700 border-yellow-300">
            <RiLightbulbLine className="mr-1 h-3 w-3" />
            Suggested
          </Badge>
        );
      }

      const isActive = row.getValue("isActive") as boolean;
      return isActive ? (
        <Badge variant="default" className="bg-green-500/10 text-green-700">
          <RiCheckLine className="mr-1 h-3 w-3" />
          Active
        </Badge>
      ) : (
        <Badge variant="secondary" className="opacity-50">
          <RiCloseLine className="mr-1 h-3 w-3" />
          Inactive
        </Badge>
      );
    },
    size: 100,
  },
  {
    id: "actions",
    cell: ({ row }) => {
      const item = row.original;
      const isSuggestion = item.isSuggestion;

      if (isSuggestion) {
        // Show Verify and Dismiss buttons for suggestions
        return (
          <div onClick={(e) => e.stopPropagation()} className="flex items-center gap-1">
            <Button
              size="sm"
              variant="default"
              onClick={() => onVerify(item)}
            >
              <RiCheckLine className="mr-1 h-3 w-3" />
              Verify
            </Button>
            <Button
              size="sm"
              variant="ghost"
              onClick={() => onDismiss(item)}
            >
              <RiCloseLine className="h-4 w-4" />
            </Button>
          </div>
        );
      }

      // Regular subscription actions
      return (
        <div onClick={(e) => e.stopPropagation()}>
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
                onClick={() => onDelete(item)}
                className="text-destructive"
              >
                <RiDeleteBinLine className="mr-2 h-4 w-4" />
                Delete
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
      );
    },
    size: 120,
    enableSorting: false,
    enableHiding: false,
  },
];
