"use client";

import { type ColumnDef } from "@tanstack/react-table";
import { useRouter } from "next/navigation";
import { Checkbox } from "@/components/ui/checkbox";
import { Badge } from "@/components/ui/badge";
import type { TransactionWithRelations } from "@/lib/actions/transactions";
import { RiArrowUpLine, RiArrowDownLine, RiCheckLine } from "@remixicon/react";
import { format } from "date-fns";
import { buildCategorySpendingQuery } from "@/lib/category-spending/query-params";

function CategoryCell({
  transaction,
  maxWidth,
}: {
  transaction: TransactionWithRelations;
  maxWidth: number;
}) {
  const router = useRouter();
  const displayCategory = transaction.category ?? transaction.categorySystem;

  if (!displayCategory) {
    return <span className="text-muted-foreground">Uncategorized</span>;
  }

  return (
    <button
      type="button"
      className="inline-flex items-center px-2 py-0.5 text-xs text-white truncate transition-opacity hover:opacity-90"
      style={{
        backgroundColor: displayCategory.color ?? "#6B7280",
        maxWidth: `${maxWidth}px`,
      }}
      title={displayCategory.name}
      onClick={(event) => {
        event.stopPropagation();
        const query = buildCategorySpendingQuery({
          categoryId: displayCategory.id,
          accountIds: [transaction.accountId],
        });
        router.push(query ? `/category-spending?${query}` : "/category-spending");
      }}
    >
      {displayCategory.name}
    </button>
  );
}

export const accountTransactionColumns: ColumnDef<TransactionWithRelations>[] = [
  {
    id: "select",
    header: ({ table }) => {
      const allRowsSelected = table.getIsAllRowsSelected();
      const allPageRowsSelected = table.getIsAllPageRowsSelected();
      const someRowsSelected = table.getIsSomeRowsSelected();

      const isChecked = allRowsSelected;
      const isIndeterminate = !allRowsSelected && (allPageRowsSelected || someRowsSelected);

      const handleClick = () => {
        if (allRowsSelected) {
          table.toggleAllRowsSelected(false);
        } else if (allPageRowsSelected) {
          table.toggleAllRowsSelected(true);
        } else {
          table.toggleAllPageRowsSelected(true);
        }
      };

      return (
        <Checkbox
          checked={isChecked}
          indeterminate={isIndeterminate}
          onCheckedChange={handleClick}
          aria-label="Select all"
        />
      );
    },
    cell: ({ row }) => (
      <div onClick={(e) => e.stopPropagation()}>
        <Checkbox
          checked={row.getIsSelected()}
          onCheckedChange={(value) => row.toggleSelected(!!value)}
          aria-label="Select row"
        />
      </div>
    ),
    size: 50,
    enableSorting: false,
    enableHiding: false,
    enableResizing: false,
  },
  {
    accessorKey: "bookedAt",
    header: ({ column }) => {
      const sorted = column.getIsSorted();
      return (
        <div
          className="flex items-center gap-1 cursor-pointer"
          onClick={() => column.toggleSorting(column.getIsSorted() === "asc")}
        >
          Date
          {sorted === "asc" ? (
            <RiArrowUpLine className="h-4 w-4" />
          ) : sorted === "desc" ? (
            <RiArrowDownLine className="h-4 w-4" />
          ) : null}
        </div>
      );
    },
    cell: ({ row }) => (
      <span className="whitespace-nowrap">
        {format(new Date(row.getValue("bookedAt")), "MMM d, yyyy")}
      </span>
    ),
    size: 120,
    sortingFn: "datetime",
    filterFn: (row, id, filterValue) => {
      if (!filterValue || !filterValue.from) return true;
      const rowDate = row.getValue("bookedAt") as Date;
      const from = new Date(filterValue.from);
      const to = filterValue.to ? new Date(filterValue.to) : from;
      from.setHours(0, 0, 0, 0);
      to.setHours(23, 59, 59, 999);
      return rowDate >= from && rowDate <= to;
    },
  },
  {
    accessorKey: "description",
    header: "Description",
    cell: ({ row, column }) => {
      const columnSize = column.getSize();
      return (
        <div
          className="truncate"
          style={{ maxWidth: `${columnSize}px` }}
          title={row.getValue("description") || ""}
        >
          {row.getValue("description")}
        </div>
      );
    },
    size: 300,
    filterFn: "includesString",
  },
  {
    accessorKey: "merchant",
    header: "Merchant",
    cell: ({ row, column }) => {
      const merchant = row.original.merchant;
      const columnSize = column.getSize();
      return merchant ? (
        <div
          className="truncate"
          style={{ maxWidth: `${columnSize}px` }}
          title={merchant}
        >
          {merchant}
        </div>
      ) : (
        <span className="text-muted-foreground">-</span>
      );
    },
    size: 150,
  },
  {
    accessorKey: "category",
    header: "Category",
    cell: ({ row, column }) => {
      const columnSize = column.getSize();
      return (
        <CategoryCell
          transaction={row.original}
          maxWidth={columnSize}
        />
      );
    },
    size: 140,
    filterFn: (row, id, filterValue) => {
      if (!filterValue || !Array.isArray(filterValue) || filterValue.length === 0) return true;
      if (filterValue.includes("uncategorized") && !row.original.category) return true;
      return filterValue.includes(row.original.category?.id);
    },
  },
  {
    accessorKey: "transactionType",
    header: "Type",
    cell: ({ row }) => {
      const type = row.original.transactionType;
      const amount = row.original.amount;
      const isCredit = type === "credit" || amount > 0;
      return (
        <Badge variant={isCredit ? "default" : "secondary"}>
          {isCredit ? "Income" : "Expense"}
        </Badge>
      );
    },
    size: 100,
  },
  {
    accessorKey: "amount",
    header: ({ column }) => {
      const sorted = column.getIsSorted();
      return (
        <div
          className="flex items-center justify-end gap-1 cursor-pointer"
          onClick={() => column.toggleSorting(column.getIsSorted() === "asc")}
        >
          Amount
          {sorted === "asc" ? (
            <RiArrowUpLine className="h-4 w-4" />
          ) : sorted === "desc" ? (
            <RiArrowDownLine className="h-4 w-4" />
          ) : null}
        </div>
      );
    },
    cell: ({ row }) => {
      const amount = row.getValue("amount") as number;
      const type = row.original.transactionType;
      const isCredit = type === "credit" || amount > 0;
      return (
        <span className="whitespace-nowrap text-right font-mono block">
          {isCredit ? "+" : "-"}
          {Math.abs(amount).toFixed(2)}
        </span>
      );
    },
    size: 120,
    filterFn: (row, id, filterValue) => {
      if (!filterValue || (!filterValue.min && !filterValue.max)) return true;
      const amount = Math.abs(row.getValue("amount") as number);
      const min = filterValue.min ? parseFloat(filterValue.min) : -Infinity;
      const max = filterValue.max ? parseFloat(filterValue.max) : Infinity;
      return amount >= min && amount <= max;
    },
  },
  {
    accessorKey: "recurringTransaction",
    header: "Sub",
    cell: ({ row }) => {
      const recurring = row.original.recurringTransaction;
      if (!recurring) {
        return <span className="text-muted-foreground">-</span>;
      }
      return (
        <span title={`${recurring.name} (${recurring.frequency})`}>
          <RiCheckLine className="h-4 w-4 text-emerald-600" />
        </span>
      );
    },
    size: 60,
    filterFn: (row, id, filterValue) => {
      if (!filterValue || !Array.isArray(filterValue) || filterValue.length === 0) return true;
      if (filterValue.includes("no_subscription") && !row.original.recurringTransaction) return true;
      if (row.original.recurringTransaction) {
        return filterValue.includes(row.original.recurringTransaction.id);
      }
      return false;
    },
  },
  {
    accessorKey: "pending",
    header: "Status",
    cell: ({ row }) => {
      const pending = row.getValue("pending") as boolean;
      return pending ? (
        <Badge variant="outline">Pending</Badge>
      ) : null;
    },
    size: 80,
    filterFn: (row, id, filterValue) => {
      if (!filterValue || !Array.isArray(filterValue) || filterValue.length === 0) return true;
      if (filterValue.includes("pending") && row.original.pending) return true;
      if (filterValue.includes("completed") && !row.original.pending) return true;
      return false;
    },
  },
];
