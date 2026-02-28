"use client";

import * as React from "react";
import { useSearchParams, useRouter } from "next/navigation";
import { type OnChangeFn, type PaginationState, type SortingState } from "@tanstack/react-table";
import { DataTable } from "@/components/ui/data-table";
import type {
  FilteredTransactionTotals,
  TransactionWithRelations,
} from "@/lib/actions/transactions";
import type { CategoryDisplay, AccountForFilter } from "@/types";
import { TransactionSheet } from "./transaction-sheet";
import { transactionColumns } from "./columns";
import { TransactionFilters } from "./transaction-filters";
import { TransactionPagination } from "./transaction-pagination";
import { BulkActionsDock } from "./bulk-actions-dock";
import { useFilterPersistence } from "@/lib/hooks/use-filter-persistence";
import {
  parseTransactionsSearchParamsFromUrlSearchParams,
  toTransactionsSearchParams,
  hasActiveTransactionFilters,
  type TransactionSortField,
  type TransactionsQueryState,
} from "@/lib/transactions/query-state";

interface TransactionTableProps {
  transactions: TransactionWithRelations[];
  totalCount: number;
  filteredTotals: FilteredTransactionTotals | null;
  queryState: TransactionsQueryState;
  categories?: CategoryDisplay[];
  accounts?: AccountForFilter[];
  onUpdateTransaction?: (id: string, updates: Partial<TransactionWithRelations>) => void;
  onDeleteTransaction?: (id: string) => void;
  onBulkUpdate?: (transactionIds: string[], categoryId: string | null) => void;
  action?: React.ReactNode;
}

const MANAGED_QUERY_KEYS = [
  "page",
  "pageSize",
  "search",
  "category",
  "account",
  "status",
  "subscription",
  "analytics",
  "minAmount",
  "maxAmount",
  "from",
  "to",
  "horizon",
  "sort",
  "order",
];

function mergeManagedQueryParams(
  currentSearchParams: URLSearchParams,
  nextState: TransactionsQueryState
): URLSearchParams {
  const nextParams = new URLSearchParams(currentSearchParams.toString());
  MANAGED_QUERY_KEYS.forEach((key) => nextParams.delete(key));
  const managed = toTransactionsSearchParams(nextState);
  managed.forEach((value, key) => {
    nextParams.append(key, value);
  });
  return nextParams;
}

function mapSortColumnIdToSortField(id: string): TransactionSortField {
  if (id === "amount" || id === "description" || id === "merchant") {
    return id;
  }
  return "bookedAt";
}

function formatSummaryAmount(amount: number): string {
  return amount.toLocaleString(undefined, {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
}

export function TransactionTable({
  transactions,
  totalCount,
  filteredTotals,
  queryState,
  categories = [],
  accounts = [],
  onUpdateTransaction,
  onDeleteTransaction,
  onBulkUpdate,
  action,
}: TransactionTableProps) {
  const [selectedTransaction, setSelectedTransaction] = React.useState<TransactionWithRelations | null>(null);
  const searchParams = useSearchParams();
  const router = useRouter();

  useFilterPersistence();

  const updateQueryState = React.useCallback(
    (patch: Partial<TransactionsQueryState>, options?: { resetPage?: boolean }) => {
      const currentParams = new URLSearchParams(searchParams.toString());
      const currentState = parseTransactionsSearchParamsFromUrlSearchParams(currentParams);
      const nextState: TransactionsQueryState = {
        ...currentState,
        ...patch,
      };

      if (options?.resetPage ?? true) {
        nextState.page = 1;
      }

      const merged = mergeManagedQueryParams(currentParams, nextState);
      const queryString = merged.toString();
      router.replace(queryString ? `/transactions?${queryString}` : "/transactions", {
        scroll: false,
      });
    },
    [router, searchParams]
  );

  const sortingState = React.useMemo<SortingState>(
    () => [
      {
        id: queryState.sort,
        desc: queryState.order === "desc",
      },
    ],
    [queryState.order, queryState.sort]
  );

  const paginationState = React.useMemo<PaginationState>(
    () => ({
      pageIndex: Math.max(0, queryState.page - 1),
      pageSize: queryState.pageSize,
    }),
    [queryState.page, queryState.pageSize]
  );

  const pageCount = Math.max(1, Math.ceil(totalCount / queryState.pageSize));
  const resolvedFilteredTotals = hasActiveTransactionFilters(queryState)
    ? filteredTotals
    : null;

  const handleSortingStateChange = React.useCallback<OnChangeFn<SortingState>>(
    (updater) => {
      const current = sortingState;
      const next = typeof updater === "function" ? updater(current) : updater;
      const nextSort = next[0];
      if (!nextSort) {
        updateQueryState({ sort: "bookedAt", order: "desc" }, { resetPage: false });
        return;
      }

      updateQueryState(
        {
          sort: mapSortColumnIdToSortField(nextSort.id),
          order: nextSort.desc ? "desc" : "asc",
        },
        { resetPage: false }
      );
    },
    [sortingState, updateQueryState]
  );

  const handlePaginationStateChange = React.useCallback<OnChangeFn<PaginationState>>(
    (updater) => {
      const current = paginationState;
      const next = typeof updater === "function" ? updater(current) : updater;
      updateQueryState(
        {
          page: next.pageIndex + 1,
          pageSize: next.pageSize,
        },
        { resetPage: false }
      );
    },
    [paginationState, updateQueryState]
  );

  const recurringOptions = React.useMemo(() => {
    const byId = new Map<string, { id: string; name: string; merchant?: string; frequency: string }>();
    transactions.forEach((transaction) => {
      const recurring = transaction.recurringTransaction;
      if (!recurring || byId.has(recurring.id)) {
        return;
      }
      byId.set(recurring.id, {
        id: recurring.id,
        name: recurring.name,
        merchant: recurring.merchant ?? undefined,
        frequency: recurring.frequency,
      });
    });
    return Array.from(byId.values());
  }, [transactions]);

  React.useEffect(() => {
    const txId = searchParams.get("tx");
    if (!txId) return;
    const tx = transactions.find((transaction) => transaction.id === txId);
    if (!tx) return;

    setSelectedTransaction(tx);
    const params = new URLSearchParams(searchParams.toString());
    params.delete("tx");
    const queryString = params.toString();
    router.replace(queryString ? `/transactions?${queryString}` : "/transactions", {
      scroll: false,
    });
  }, [router, searchParams, transactions]);

  const handleRowClick = (transaction: TransactionWithRelations) => {
    setSelectedTransaction(transaction);
  };

  const handleUpdateTransaction = (id: string, updates: Partial<TransactionWithRelations>) => {
    onUpdateTransaction?.(id, updates);
    if (selectedTransaction?.id === id) {
      setSelectedTransaction((prev) => (prev ? { ...prev, ...updates } : null));
    }
  };

  return (
    <>
      <DataTable
        columns={transactionColumns}
        data={transactions}
        onRowClick={handleRowClick}
        enableColumnResizing={true}
        enableRowSelection={true}
        enablePagination={true}
        manualPagination={true}
        manualSorting={true}
        rowCount={totalCount}
        pageCount={pageCount}
        paginationState={paginationState}
        onPaginationStateChange={handlePaginationStateChange}
        sortingState={sortingState}
        onSortingStateChange={handleSortingStateChange}
        toolbar={() => (
          <TransactionFilters
            filters={queryState}
            categories={categories}
            accounts={accounts}
            recurringOptions={recurringOptions}
            action={action}
            onFiltersChange={updateQueryState}
            onClearFilters={() =>
              updateQueryState(
                {
                  page: 1,
                  search: undefined,
                  category: [],
                  accountIds: [],
                  status: [],
                  subscription: [],
                  analytics: [],
                  minAmount: undefined,
                  maxAmount: undefined,
                  from: undefined,
                  to: undefined,
                  horizon: 30,
                  sort: "bookedAt",
                  order: "desc",
                },
                { resetPage: false }
              )
            }
          />
        )}
        pagination={(table) => (
          <TransactionPagination
            table={table}
            totalCount={totalCount}
            page={queryState.page}
            pageSize={queryState.pageSize}
            onPageChange={(page) => updateQueryState({ page }, { resetPage: false })}
            onPageSizeChange={(pageSize) =>
              updateQueryState({ pageSize, page: 1 }, { resetPage: false })
            }
          />
        )}
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
        wrapperClassName="flex min-h-0 flex-1 flex-col"
        tableContainerClassName="min-h-0 flex-1 overflow-y-auto"
        tableContainerProps={
          { "data-walkthrough": "walkthrough-table" } as React.HTMLAttributes<HTMLDivElement>
        }
        footer={
          resolvedFilteredTotals ? (
            <div className="-mt-px flex items-center justify-end gap-8 border-x border-b bg-muted/25 px-4 py-2">
              <div className="flex items-center gap-2 text-xs">
                <span className="text-muted-foreground">Total In</span>
                <span className="font-mono font-medium text-emerald-700">
                  +{formatSummaryAmount(resolvedFilteredTotals.totalIn)}
                </span>
              </div>
              <div className="flex items-center gap-2 text-xs">
                <span className="text-muted-foreground">Total Out</span>
                <span className="font-mono font-medium text-rose-700">
                  -{formatSummaryAmount(resolvedFilteredTotals.totalOut)}
                </span>
              </div>
            </div>
          ) : null
        }
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
