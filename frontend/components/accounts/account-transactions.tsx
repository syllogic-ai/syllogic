"use client";

import * as React from "react";
import { useState, useEffect, useMemo, useCallback, useRef } from "react";
import { useRouter } from "next/navigation";
import { type DateRange } from "react-day-picker";
import { type ColumnFiltersState } from "@tanstack/react-table";
import { DataTable } from "@/components/ui/data-table";
import type { TransactionWithRelations } from "@/lib/actions/transactions";
import type { CategoryDisplay } from "@/types";
import { TransactionSheet } from "@/components/transactions/transaction-sheet";
import { TransactionPagination } from "@/components/transactions/transaction-pagination";
import { BulkActionsDock } from "@/components/transactions/bulk-actions-dock";
import { AccountTransactionFilters } from "./account-transaction-filters";
import { accountTransactionColumns } from "./account-transaction-columns";

const FILTER_STORAGE_PREFIX = "filters:/accounts";

interface AccountTransactionsProps {
  accountId: string;
  transactions: TransactionWithRelations[];
  categories: CategoryDisplay[];
  onUpdateTransaction?: (id: string, updates: Partial<TransactionWithRelations>) => void;
  onDeleteTransaction?: (id: string) => void;
  onBulkUpdate?: (transactionIds: string[], categoryId: string | null) => void;
}

export function AccountTransactions({
  accountId,
  transactions,
  categories,
  onUpdateTransaction,
  onDeleteTransaction,
  onBulkUpdate,
}: AccountTransactionsProps) {
  const router = useRouter();
  const [selectedTransaction, setSelectedTransaction] = useState<TransactionWithRelations | null>(null);
  const [tableKey, setTableKey] = useState("default");
  const hasInitializedRef = useRef(false);

  const storageKey = `${FILTER_STORAGE_PREFIX}/${accountId}`;

  // Track mounted state to know when we can access localStorage
  const [isMounted, setIsMounted] = useState(false);
  useEffect(() => {
    setIsMounted(true);
  }, []);

  // Load saved filters from localStorage (only on client after mount)
  const savedFilters = useMemo((): ColumnFiltersState => {
    if (!isMounted) return [];
    try {
      const saved = localStorage.getItem(storageKey);
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
  }, [isMounted, storageKey]);

  // Force table remount when saved filters are loaded
  useEffect(() => {
    if (isMounted && savedFilters.length > 0) {
      setTableKey(`restored-${Date.now()}`);
    }
  }, [isMounted, savedFilters.length]);

  // Save filters to localStorage when they change
  const handleColumnFiltersChange = useCallback((filters: ColumnFiltersState) => {
    try {
      if (!hasInitializedRef.current) {
        hasInitializedRef.current = true;
        if (filters.length === 0) {
          return;
        }
      }

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
      localStorage.setItem(storageKey, JSON.stringify(serializable));
    } catch {
      // Ignore storage errors
    }
  }, [storageKey]);

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
        columns={accountTransactionColumns}
        data={transactions}
        onRowClick={handleRowClick}
        enableColumnResizing={true}
        enableRowSelection={true}
        enablePagination={true}
        pageSize={20}
        initialColumnFilters={savedFilters}
        onColumnFiltersChange={handleColumnFiltersChange}
        toolbar={(table) => (
          <AccountTransactionFilters table={table} categories={categories} />
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
