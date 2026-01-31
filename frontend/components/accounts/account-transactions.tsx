"use client";

import * as React from "react";
import { useState } from "react";
import { DataTable } from "@/components/ui/data-table";
import type { TransactionWithRelations } from "@/lib/actions/transactions";
import type { CategoryDisplay } from "@/types";
import { TransactionSheet } from "@/components/transactions/transaction-sheet";
import { TransactionPagination } from "@/components/transactions/transaction-pagination";
import { BulkActionsDock } from "@/components/transactions/bulk-actions-dock";
import { AccountTransactionFilters } from "./account-transaction-filters";
import { accountTransactionColumns } from "./account-transaction-columns";

interface AccountTransactionsProps {
  transactions: TransactionWithRelations[];
  categories: CategoryDisplay[];
  onUpdateTransaction?: (id: string, updates: Partial<TransactionWithRelations>) => void;
  onDeleteTransaction?: (id: string) => void;
  onBulkUpdate?: (transactionIds: string[], categoryId: string | null) => void;
}

export function AccountTransactions({
  transactions,
  categories,
  onUpdateTransaction,
  onDeleteTransaction,
  onBulkUpdate,
}: AccountTransactionsProps) {
  const [selectedTransaction, setSelectedTransaction] = useState<TransactionWithRelations | null>(null);

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
        columns={accountTransactionColumns}
        data={transactions}
        onRowClick={handleRowClick}
        enableColumnResizing={true}
        enableRowSelection={true}
        enablePagination={true}
        pageSize={20}
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
