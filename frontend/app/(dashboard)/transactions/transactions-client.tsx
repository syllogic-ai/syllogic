"use client";

import { useState, useCallback } from "react";
import { TransactionTable } from "@/components/transactions/transaction-table";
import { AddTransactionButton } from "@/components/transactions/add-transaction-button";
import { AddTransactionDialog } from "@/components/transactions/add-transaction-dialog";
import { useRegisterCommandPaletteCallbacks } from "@/components/command-palette-context";
import { exportTransactionsToCSV } from "@/lib/utils/csv-export";
import type { TransactionWithRelations } from "@/lib/actions/transactions";
import type { CategoryDisplay, AccountForFilter } from "@/types";

interface TransactionsClientProps {
  initialTransactions: TransactionWithRelations[];
  categories: CategoryDisplay[];
  accounts: AccountForFilter[];
}

export function TransactionsClient({
  initialTransactions,
  categories,
  accounts,
}: TransactionsClientProps) {
  const [transactions, setTransactions] = useState(initialTransactions);
  const [isAddDialogOpen, setIsAddDialogOpen] = useState(false);

  const handleUpdateTransaction = (
    id: string,
    updates: Partial<TransactionWithRelations>
  ) => {
    setTransactions((prev) =>
      prev.map((tx) => (tx.id === id ? { ...tx, ...updates } : tx))
    );
  };

  const handleBulkUpdate = (transactionIds: string[], categoryId: string | null) => {
    const category = categoryId
      ? categories.find((c) => c.id === categoryId) ?? null
      : null;

    setTransactions((prev) =>
      prev.map((tx) =>
        transactionIds.includes(tx.id)
          ? { ...tx, categoryId, category }
          : tx
      )
    );
  };

  const handleAddManual = useCallback(() => {
    setIsAddDialogOpen(true);
  }, []);

  const handleExportCSV = useCallback(() => {
    exportTransactionsToCSV(transactions);
  }, [transactions]);

  // Register command palette callbacks
  useRegisterCommandPaletteCallbacks(
    {
      onAddTransaction: handleAddManual,
      onExportCSV: handleExportCSV,
    },
    [handleAddManual, handleExportCSV]
  );

  return (
    <>
      <div className="flex items-center shrink-0">
        <AddTransactionButton onAddManual={handleAddManual} />
      </div>
      <div className="min-h-0 flex-1 flex flex-col">
        <TransactionTable
          transactions={transactions}
          categories={categories}
          accounts={accounts}
          onUpdateTransaction={handleUpdateTransaction}
          onBulkUpdate={handleBulkUpdate}
        />
      </div>
      <AddTransactionDialog
        open={isAddDialogOpen}
        onOpenChange={setIsAddDialogOpen}
        categories={categories}
      />
    </>
  );
}
