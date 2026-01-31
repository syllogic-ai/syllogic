"use client";

import { useState } from "react";
import { AccountHeader } from "@/components/accounts/account-header";
import { AccountBalanceChart } from "@/components/accounts/account-balance-chart";
import { AccountTransactions } from "@/components/accounts/account-transactions";
import type { Account, Category } from "@/lib/db/schema";
import type { BalanceHistoryPoint } from "@/lib/actions/accounts";
import type { TransactionWithRelations } from "@/lib/actions/transactions";
import type { CategoryDisplay } from "@/types";

interface AccountDetailProps {
  account: Account;
  balanceHistory: BalanceHistoryPoint[];
  initialTransactions: TransactionWithRelations[];
  categories: Category[];
}

export function AccountDetail({
  account,
  balanceHistory,
  initialTransactions,
  categories,
}: AccountDetailProps) {
  const [transactions, setTransactions] = useState(initialTransactions);
  const currency = account.currency || "EUR";

  // Convert Category[] to CategoryDisplay[]
  const categoryDisplays: CategoryDisplay[] = categories.map((cat) => ({
    id: cat.id,
    name: cat.name,
    color: cat.color,
    icon: cat.icon,
  }));

  const handleUpdateTransaction = (
    id: string,
    updates: Partial<TransactionWithRelations>
  ) => {
    setTransactions((prev) =>
      prev.map((tx) => (tx.id === id ? { ...tx, ...updates } : tx))
    );
  };

  const handleDeleteTransaction = (id: string) => {
    setTransactions((prev) => prev.filter((tx) => tx.id !== id));
  };

  const handleBulkUpdate = (transactionIds: string[], categoryId: string | null) => {
    const category = categoryId
      ? categoryDisplays.find((c) => c.id === categoryId) ?? null
      : null;

    setTransactions((prev) =>
      prev.map((tx) =>
        transactionIds.includes(tx.id)
          ? { ...tx, categoryId, category }
          : tx
      )
    );
  };

  return (
    <div className="flex flex-col gap-4">
      <AccountHeader account={account} currency={currency} />
      <AccountBalanceChart data={balanceHistory} currency={currency} />
      <div className="min-h-[400px]">
        {transactions.length === 0 ? (
          <div className="flex h-48 items-center justify-center rounded border border-dashed">
            <p className="text-sm text-muted-foreground">No transactions yet</p>
          </div>
        ) : (
          <AccountTransactions
            transactions={transactions}
            categories={categoryDisplays}
            onUpdateTransaction={handleUpdateTransaction}
            onDeleteTransaction={handleDeleteTransaction}
            onBulkUpdate={handleBulkUpdate}
          />
        )}
      </div>
    </div>
  );
}
