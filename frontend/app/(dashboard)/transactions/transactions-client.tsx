"use client";

import { useState } from "react";
import { TransactionTable } from "@/components/transactions/transaction-table";
import { AddTransactionButton } from "@/components/transactions/add-transaction-button";
import { AddTransactionDialog } from "@/components/transactions/add-transaction-dialog";
import type { TransactionWithRelations } from "@/lib/actions/transactions";

interface Category {
  id: string;
  name: string;
  color: string | null;
  icon: string | null;
}

interface TransactionsClientProps {
  initialTransactions: TransactionWithRelations[];
  categories: Category[];
}

export function TransactionsClient({
  initialTransactions,
  categories,
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

  const handleAddManual = () => {
    setIsAddDialogOpen(true);
  };

  return (
    <>
      <div className="flex items-center justify-between shrink-0">
        <AddTransactionButton onAddManual={handleAddManual} />
      </div>
      <div className="min-h-0 flex-1 flex flex-col">
        <TransactionTable
          transactions={transactions}
          categories={categories}
          onUpdateTransaction={handleUpdateTransaction}
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
