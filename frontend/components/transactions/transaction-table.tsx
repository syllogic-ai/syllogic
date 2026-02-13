"use client";

import * as React from "react";
import { useState, useEffect, useCallback } from "react";
import { useSearchParams, useRouter, usePathname } from "next/navigation";
import { type DateRange } from "react-day-picker";
import { type ColumnFiltersState } from "@tanstack/react-table";
import { DataTable } from "@/components/ui/data-table";
import type { TransactionWithRelations } from "@/lib/actions/transactions";
import type { CategoryDisplay, AccountForFilter } from "@/types";
import { TransactionSheet } from "./transaction-sheet";
import { transactionColumns } from "./columns";
import { TransactionFilters } from "./transaction-filters";
import { TransactionPagination } from "./transaction-pagination";
import { BulkActionsDock } from "./bulk-actions-dock";

const FILTER_STORAGE_KEY = "filters:/transactions";

interface TransactionTableProps {
  transactions: TransactionWithRelations[];
  categories?: CategoryDisplay[];
  accounts?: AccountForFilter[];
  onUpdateTransaction?: (id: string, updates: Partial<TransactionWithRelations>) => void;
  onDeleteTransaction?: (id: string) => void;
  onBulkUpdate?: (transactionIds: string[], categoryId: string | null) => void;
  action?: React.ReactNode;
}

export function TransactionTable({
  transactions,
  categories = [],
  accounts = [],
  onUpdateTransaction,
  onDeleteTransaction,
  onBulkUpdate,
  action,
}: TransactionTableProps) {
  const [selectedTransaction, setSelectedTransaction] = useState<TransactionWithRelations | null>(null);
  const searchParams = useSearchParams();
  const router = useRouter();

  const searchKey = searchParams.toString();
  const resetToken = searchParams.get("reset");
  const [tableKey, setTableKey] = useState(() =>
    resetToken ? `reset-${resetToken}` : "default"
  );

  useEffect(() => {
    if (!resetToken) return;
    setTableKey(`reset-${resetToken}`);
    const params = new URLSearchParams(searchParams.toString());
    params.delete("reset");
    const queryString = params.toString();
    router.replace(queryString ? `/transactions?${queryString}` : "/transactions", {
      scroll: false,
    });
  }, [resetToken, router, searchParams]);

  // Check if URL has filter-related params
  const hasUrlFilters = React.useMemo(() => {
    const params = new URLSearchParams(searchKey);
    return params.has("category") || params.has("account") || params.has("from") || params.has("to") || params.has("horizon");
  }, [searchKey]);

  // Build filters from URL params
  const urlBasedFilters = React.useMemo(() => {
    const filters: ColumnFiltersState = [];
    const params = new URLSearchParams(searchKey);
    const categoryParam = params.get("category");
    const accountParam = params.get("account");
    const fromParam = params.get("from");
    const toParam = params.get("to");
    const horizonParam = params.get("horizon");

    if (categoryParam) {
      filters.push({ id: "category", value: [categoryParam] });
    }

    if (accountParam) {
      filters.push({ id: "account", value: [accountParam] });
    }

    let dateRange: DateRange | undefined;
    if (fromParam) {
      const fromDate = new Date(fromParam);
      const toDate = new Date(toParam ?? fromParam);
      if (!Number.isNaN(fromDate.getTime())) {
        dateRange = {
          from: fromDate,
          to: Number.isNaN(toDate.getTime()) ? fromDate : toDate,
        };
      }
    } else if (horizonParam) {
      const horizon = parseInt(horizonParam, 10);
      if (!Number.isNaN(horizon) && horizon > 0) {
        const referenceDate = transactions
          .filter((tx) => !accountParam || tx.accountId === accountParam)
          .reduce<Date | null>((latest, tx) => {
            const bookedAt = new Date(tx.bookedAt);
            if (Number.isNaN(bookedAt.getTime())) return latest;
            if (!latest || bookedAt > latest) return bookedAt;
            return latest;
          }, null);

        if (referenceDate) {
          const fromDate = new Date(referenceDate);
          fromDate.setDate(fromDate.getDate() - horizon);
          fromDate.setHours(0, 0, 0, 0);
          const toDate = new Date(referenceDate);
          toDate.setHours(23, 59, 59, 999);
          dateRange = { from: fromDate, to: toDate };
        }
      }
    }

    if (dateRange) {
      filters.push({ id: "bookedAt", value: dateRange });
    }

    return filters;
  }, [searchKey, transactions]);

  // Track mounted state to know when we can access sessionStorage
  const [isMounted, setIsMounted] = useState(false);
  useEffect(() => {
    setIsMounted(true);
  }, []);

  // Load saved filters from sessionStorage (only on client after mount)
  const savedFilters = React.useMemo((): ColumnFiltersState => {
    if (!isMounted) return [];
    try {
      const saved = sessionStorage.getItem(FILTER_STORAGE_KEY);
      if (saved) {
        const parsed = JSON.parse(saved) as ColumnFiltersState;
        return parsed.map((filter) => {
          if (filter.id === "bookedAt" && filter.value) {
            const val = filter.value as { from?: string; to?: string };
            return {
              ...filter,
              value: {
                from: val.from ? new Date(val.from) : undefined,
                to: val.to ? new Date(val.to) : undefined,
              },
            };
          }
          return filter;
        });
      }
    } catch {
      // Ignore parse errors
    }
    return [];
  }, [isMounted]);

  // Compute initial filters - URL takes precedence, then sessionStorage
  const initialColumnFilters = hasUrlFilters ? urlBasedFilters : savedFilters;

  // Force table remount when saved filters are loaded
  useEffect(() => {
    if (isMounted && !hasUrlFilters && savedFilters.length > 0) {
      setTableKey(`restored-${Date.now()}`);
    }
  }, [isMounted, hasUrlFilters, savedFilters.length]);

  // Save filters to sessionStorage when they change
  const handleColumnFiltersChange = useCallback((filters: ColumnFiltersState) => {
    try {
      // Convert dates to ISO strings for storage
      const serializable = filters.map((filter) => {
        if (filter.id === "bookedAt" && filter.value) {
          const val = filter.value as DateRange;
          return {
            ...filter,
            value: {
              from: val.from?.toISOString(),
              to: val.to?.toISOString(),
            },
          };
        }
        return filter;
      });
      sessionStorage.setItem(FILTER_STORAGE_KEY, JSON.stringify(serializable));
    } catch {
      // Ignore storage errors
    }
  }, []);

  // Handle URL query param for auto-selecting a transaction
  useEffect(() => {
    const txId = searchParams.get("tx");
    if (txId) {
      const tx = transactions.find((t) => t.id === txId);
      if (tx) {
        setSelectedTransaction(tx);
        // Clear the URL param to avoid re-selecting on navigation
        router.replace("/transactions", { scroll: false });
      }
    }
  }, [searchParams, transactions, router]);

  const handleRowClick = (transaction: TransactionWithRelations) => {
    setSelectedTransaction(transaction);
  };

  const handleUpdateTransaction = (id: string, updates: Partial<TransactionWithRelations>) => {
    onUpdateTransaction?.(id, updates);
    if (selectedTransaction?.id === id) {
      setSelectedTransaction((prev) => prev ? { ...prev, ...updates } : null);
    }
  };

  return (
    <>
      <DataTable
        key={tableKey}
        columns={transactionColumns}
        data={transactions}
        onRowClick={handleRowClick}
        enableColumnResizing={true}
        enableRowSelection={true}
        enablePagination={true}
        pageSize={20}
        initialColumnFilters={initialColumnFilters}
        onColumnFiltersChange={handleColumnFiltersChange}
        toolbar={(table) => (
          <TransactionFilters table={table} categories={categories} accounts={accounts} action={action} />
        )}
        pagination={(table) => <TransactionPagination table={table} />}
        bulkActions={(table) => {
          const selectedRows = table.getSelectedRowModel().rows;
          const selectedIds = selectedRows.map((row) => row.original.id);
          const selectedTransactions = selectedRows.map((row) => row.original);
          const selectedCount = selectedRows.length;

          return (
            <BulkActionsDock
              selectedCount={selectedCount}
              selectedIds={selectedIds}
              selectedTransactions={selectedTransactions}
              categories={categories}
              onClearSelection={() => table.resetRowSelection()}
              onBulkUpdate={(categoryId) => {
                onBulkUpdate?.(selectedIds, categoryId);
              }}
              onLinkSuccess={() => {
                router.refresh();
              }}
            />
          );
        }}
        wrapperClassName="flex flex-col min-h-0 flex-1"
        tableContainerClassName="flex-1 min-h-0 overflow-y-auto"
      />

      <TransactionSheet
        transaction={selectedTransaction}
        open={selectedTransaction !== null}
        onOpenChange={(open) => {
          if (!open) setSelectedTransaction(null);
        }}
        onUpdateTransaction={handleUpdateTransaction}
        onDeleteTransaction={onDeleteTransaction}
        categories={categories}
      />
    </>
  );
}
