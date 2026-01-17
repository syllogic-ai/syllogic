"use client";

import { useState } from "react";
import { RiArrowDownLine, RiArrowUpLine } from "@remixicon/react";
import { Checkbox } from "@/components/ui/checkbox";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import { format } from "date-fns";
import type { PreviewTransaction } from "@/lib/actions/csv-import";

interface CsvPreviewTableProps {
  transactions: PreviewTransaction[];
  selectedIndices: number[];
  onSelectionChange: (indices: number[]) => void;
  showCheckboxes?: boolean;
}

export function CsvPreviewTable({
  transactions,
  selectedIndices,
  onSelectionChange,
  showCheckboxes = true,
}: CsvPreviewTableProps) {
  const [sortBy, setSortBy] = useState<"date" | "amount">("date");
  const [sortOrder, setSortOrder] = useState<"asc" | "desc">("desc");

  const sortedTransactions = [...transactions].sort((a, b) => {
    if (sortBy === "date") {
      const dateA = new Date(a.date).getTime();
      const dateB = new Date(b.date).getTime();
      return sortOrder === "asc" ? dateA - dateB : dateB - dateA;
    } else {
      return sortOrder === "asc" ? a.amount - b.amount : b.amount - a.amount;
    }
  });

  const handleSelectAll = (checked: boolean) => {
    if (checked) {
      onSelectionChange(transactions.map((tx) => tx.rowIndex));
    } else {
      onSelectionChange([]);
    }
  };

  const handleSelectOne = (rowIndex: number, checked: boolean) => {
    if (checked) {
      onSelectionChange([...selectedIndices, rowIndex]);
    } else {
      onSelectionChange(selectedIndices.filter((i) => i !== rowIndex));
    }
  };

  const toggleSort = (field: "date" | "amount") => {
    if (sortBy === field) {
      setSortOrder(sortOrder === "asc" ? "desc" : "asc");
    } else {
      setSortBy(field);
      setSortOrder("desc");
    }
  };

  const allSelected = transactions.length > 0 && selectedIndices.length === transactions.length;
  const someSelected = selectedIndices.length > 0 && selectedIndices.length < transactions.length;

  if (transactions.length === 0) {
    return (
      <div className="flex h-32 items-center justify-center text-muted-foreground">
        No transactions in this view.
      </div>
    );
  }

  return (
    <table className="w-full text-sm">
      <thead className="bg-muted sticky top-0 z-10 border-b">
        <tr>
          {showCheckboxes && (
            <th className="w-10 px-4 py-3">
              <Checkbox
                checked={allSelected}
                ref={(el) => {
                  if (el) {
                    (el as HTMLButtonElement & { indeterminate: boolean }).indeterminate = someSelected;
                  }
                }}
                onCheckedChange={handleSelectAll}
              />
            </th>
          )}
          <th
            className="cursor-pointer px-4 py-3 text-left font-medium"
            onClick={() => toggleSort("date")}
          >
            <div className="flex items-center gap-1">
              Date
              {sortBy === "date" &&
                (sortOrder === "asc" ? (
                  <RiArrowUpLine className="h-4 w-4" />
                ) : (
                  <RiArrowDownLine className="h-4 w-4" />
                ))}
            </div>
          </th>
          <th className="px-4 py-3 text-left font-medium">Description</th>
          <th className="px-4 py-3 text-left font-medium">Merchant</th>
          <th className="px-4 py-3 text-left font-medium">Type</th>
          <th
            className="cursor-pointer px-4 py-3 text-right font-medium"
            onClick={() => toggleSort("amount")}
          >
            <div className="flex items-center justify-end gap-1">
              Amount
              {sortBy === "amount" &&
                (sortOrder === "asc" ? (
                  <RiArrowUpLine className="h-4 w-4" />
                ) : (
                  <RiArrowDownLine className="h-4 w-4" />
                ))}
            </div>
          </th>
        </tr>
      </thead>
      <tbody>
        {sortedTransactions.map((tx) => (
          <tr
            key={tx.rowIndex}
            className={cn(
              "border-b",
              tx.isDuplicate && "bg-muted/30"
            )}
          >
            {showCheckboxes && (
              <td className="px-4 py-3">
                <Checkbox
                  checked={selectedIndices.includes(tx.rowIndex)}
                  onCheckedChange={(checked) =>
                    handleSelectOne(tx.rowIndex, !!checked)
                  }
                />
              </td>
            )}
            <td className="whitespace-nowrap px-4 py-3">
              {format(new Date(tx.date), "MMM d, yyyy")}
            </td>
            <td className="max-w-xs truncate px-4 py-3" title={tx.description}>
              {tx.description}
            </td>
            <td className="px-4 py-3">
              {tx.merchant || <span className="text-muted-foreground">-</span>}
            </td>
            <td className="px-4 py-3">
              <Badge variant={tx.transactionType === "credit" ? "default" : "secondary"}>
                {tx.transactionType === "credit" ? "Income" : "Expense"}
              </Badge>
            </td>
            <td className="whitespace-nowrap px-4 py-3 text-right font-mono">
              {tx.transactionType === "credit" ? "+" : "-"}
              {tx.amount.toFixed(2)}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
