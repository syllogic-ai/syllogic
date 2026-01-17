"use client";

import { type ColumnDef } from "@tanstack/react-table";
import { Checkbox } from "@/components/ui/checkbox";
import { Button } from "@/components/ui/button";
import type { TransactionWithRelations } from "@/lib/actions/transactions";
import { RiArrowUpDownLine, RiArrowUpLine, RiArrowDownLine } from "@remixicon/react";

function formatDate(date: Date): string {
  return new Intl.DateTimeFormat("en-GB", {
    month: "short",
    day: "numeric",
  }).format(date);
}

function formatAmount(amount: number, currency: string): string {
  const formatted = new Intl.NumberFormat("nl-NL", {
    style: "currency",
    currency: currency,
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(Math.abs(amount));

  return amount < 0 ? `-${formatted}` : formatted;
}

export const transactionColumns: ColumnDef<TransactionWithRelations>[] = [
  {
    id: "select",
    header: ({ table }) => (
      <Checkbox
        checked={table.getIsAllPageRowsSelected()}
        indeterminate={table.getIsSomePageRowsSelected() && !table.getIsAllPageRowsSelected()}
        onCheckedChange={(value) => table.toggleAllPageRowsSelected(!!value)}
        aria-label="Select all"
      />
    ),
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
    accessorKey: "description",
    header: ({ column }) => {
      const sorted = column.getIsSorted();
      return (
        <Button
          variant="ghost"
          onClick={() => column.toggleSorting(column.getIsSorted() === "asc")}
          className="-ml-3 h-8"
        >
          Description
          {sorted === "asc" ? (
            <RiArrowUpLine className="ml-1 h-3.5 w-3.5" />
          ) : sorted === "desc" ? (
            <RiArrowDownLine className="ml-1 h-3.5 w-3.5" />
          ) : (
            <RiArrowUpDownLine className="ml-1 h-3.5 w-3.5" />
          )}
        </Button>
      );
    },
    cell: ({ row }) => {
      return (
        <span>
          {row.getValue("description")}
        </span>
      );
    },
    size: 350,
    filterFn: "includesString",
  },
  {
    accessorKey: "amount",
    header: ({ column }) => {
      const sorted = column.getIsSorted();
      return (
        <Button
          variant="ghost"
          onClick={() => column.toggleSorting(column.getIsSorted() === "asc")}
          className="-ml-3 h-8"
        >
          Amount
          {sorted === "asc" ? (
            <RiArrowUpLine className="ml-1 h-3.5 w-3.5" />
          ) : sorted === "desc" ? (
            <RiArrowDownLine className="ml-1 h-3.5 w-3.5" />
          ) : (
            <RiArrowUpDownLine className="ml-1 h-3.5 w-3.5" />
          )}
        </Button>
      );
    },
    cell: ({ row }) => {
      const amount = row.getValue("amount") as number;
      const currency = row.original.currency || "EUR";
      return (
        <span className="font-medium">
          {formatAmount(amount, currency)}
        </span>
      );
    },
    size: 120,
    filterFn: (row, id, filterValue) => {
      // Handle amount range filter { min?: string, max?: string }
      if (!filterValue || (!filterValue.min && !filterValue.max)) return true;
      const amount = Math.abs(row.getValue("amount") as number);
      const min = filterValue.min ? parseFloat(filterValue.min) : -Infinity;
      const max = filterValue.max ? parseFloat(filterValue.max) : Infinity;
      return amount >= min && amount <= max;
    },
  },
  {
    accessorKey: "bookedAt",
    header: ({ column }) => {
      const sorted = column.getIsSorted();
      return (
        <Button
          variant="ghost"
          onClick={() => column.toggleSorting(column.getIsSorted() === "asc")}
          className="-ml-3 h-8"
        >
          Date
          {sorted === "asc" ? (
            <RiArrowUpLine className="ml-1 h-3.5 w-3.5" />
          ) : sorted === "desc" ? (
            <RiArrowDownLine className="ml-1 h-3.5 w-3.5" />
          ) : (
            <RiArrowUpDownLine className="ml-1 h-3.5 w-3.5" />
          )}
        </Button>
      );
    },
    cell: ({ row }) => (
      <span className="text-muted-foreground">
        {formatDate(row.getValue("bookedAt"))}
      </span>
    ),
    size: 100,
    sortingFn: "datetime",
    filterFn: (row, id, filterValue) => {
      // Handle date range filter { from: Date, to?: Date }
      if (!filterValue || !filterValue.from) return true;
      const rowDate = row.getValue("bookedAt") as Date;
      const from = new Date(filterValue.from);
      const to = filterValue.to ? new Date(filterValue.to) : from;
      // Set time to start/end of day for comparison
      from.setHours(0, 0, 0, 0);
      to.setHours(23, 59, 59, 999);
      return rowDate >= from && rowDate <= to;
    },
  },
  {
    accessorKey: "category",
    header: "Category",
    cell: ({ row }) => {
      const category = row.original.category;
      return category ? (
        <span
          className="inline-flex items-center px-2 py-0.5 text-xs text-white truncate"
          style={{ backgroundColor: category.color ?? "#6B7280" }}
        >
          {category.name}
        </span>
      ) : (
        <span className="text-muted-foreground">Uncategorized</span>
      );
    },
    size: 150,
    filterFn: (row, id, filterValue) => {
      // Handle array of selected category IDs
      if (!filterValue || !Array.isArray(filterValue) || filterValue.length === 0) return true;
      // Check for uncategorized
      if (filterValue.includes("uncategorized") && !row.original.category) return true;
      // Check if category matches any selected
      return filterValue.includes(row.original.category?.id);
    },
  },
  {
    accessorKey: "account",
    header: "Account",
    cell: ({ row }) => (
      <span className="text-muted-foreground">
        {row.original.account.name}
      </span>
    ),
    size: 150,
    filterFn: (row, id, filterValue) => {
      // Handle array of selected account IDs
      if (!filterValue || !Array.isArray(filterValue) || filterValue.length === 0) return true;
      return filterValue.includes(row.original.account.id);
    },
  },
  {
    accessorKey: "pending",
    header: "Status",
    cell: ({ row }) => {
      const pending = row.getValue("pending") as boolean;
      return pending ? (
        <span className="text-muted-foreground text-xs border px-1.5 py-0.5">
          Pending
        </span>
      ) : null;
    },
    size: 100,
    filterFn: (row, id, filterValue) => {
      // Handle array of selected statuses
      if (!filterValue || !Array.isArray(filterValue) || filterValue.length === 0) return true;
      if (filterValue.includes("pending") && row.original.pending) return true;
      if (filterValue.includes("completed") && !row.original.pending) return true;
      return false;
    },
  },
];
