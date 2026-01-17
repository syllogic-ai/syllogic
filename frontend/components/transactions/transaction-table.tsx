"use client";

import { useState } from "react";
import { DataTable } from "@/components/ui/data-table";
import type { TransactionWithRelations } from "@/lib/actions/transactions";
import { TransactionSheet } from "./transaction-sheet";
import { transactionColumns } from "./columns";
import { TransactionFilters } from "./transaction-filters";
import { TransactionPagination } from "./transaction-pagination";

interface Category {
  id: string;
  name: string;
  color: string | null;
  icon: string | null;
}

interface TransactionTableProps {
  transactions: TransactionWithRelations[];
  categories?: Category[];
  onUpdateTransaction?: (id: string, updates: Partial<TransactionWithRelations>) => void;
}

export function TransactionTable({ transactions, categories = [], onUpdateTransaction }: TransactionTableProps) {
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
        columns={transactionColumns}
        data={transactions}
        onRowClick={handleRowClick}
        enableColumnResizing={true}
        enableRowSelection={true}
        enablePagination={true}
        pageSize={20}
        toolbar={(table) => <TransactionFilters table={table} />}
        pagination={(table) => <TransactionPagination table={table} />}
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
