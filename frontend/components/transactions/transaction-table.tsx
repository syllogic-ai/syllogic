"use client";

import { useState, useMemo, useEffect } from "react";
import { useSearchParams, useRouter } from "next/navigation";
import { DataTable } from "@/components/ui/data-table";
import type { TransactionWithRelations } from "@/lib/actions/transactions";
import type { CategoryDisplay, AccountForFilter } from "@/types";
import { TransactionSheet } from "./transaction-sheet";
import { transactionColumns } from "./columns";
import { TransactionFilters } from "./transaction-filters";
import { TransactionPagination } from "./transaction-pagination";
import { BulkActionsDock } from "./bulk-actions-dock";

interface TransactionTableProps {
  transactions: TransactionWithRelations[];
  categories?: CategoryDisplay[];
  accounts?: AccountForFilter[];
  onUpdateTransaction?: (id: string, updates: Partial<TransactionWithRelations>) => void;
  onBulkUpdate?: (transactionIds: string[], categoryId: string | null) => void;
}

export function TransactionTable({
  transactions,
  categories = [],
  accounts = [],
  onUpdateTransaction,
  onBulkUpdate,
}: TransactionTableProps) {
  const [selectedTransaction, setSelectedTransaction] = useState<TransactionWithRelations | null>(null);
  const searchParams = useSearchParams();
  const router = useRouter();

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
        columns={transactionColumns}
        data={transactions}
        onRowClick={handleRowClick}
        enableColumnResizing={true}
        enableRowSelection={true}
        enablePagination={true}
        pageSize={20}
        toolbar={(table) => (
          <TransactionFilters table={table} categories={categories} accounts={accounts} />
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
        categories={categories}
      />
    </>
  );
}
