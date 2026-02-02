import { Suspense } from "react";
import { Header } from "@/components/layout/header";
import { TransactionsClient } from "./transactions-client";
import { getTransactions, getUserAccounts } from "@/lib/actions/transactions";
import { getUserCategories } from "@/lib/actions/categories";

export default async function TransactionsPage() {
  const [transactions, categories, accounts] = await Promise.all([
    getTransactions(),
    getUserCategories(),
    getUserAccounts(),
  ]);

  return (
    <>
      <Header title="Transactions" />
      <div className="flex h-[calc(100vh-4rem)] flex-col gap-4 p-4 pt-0">
        <Suspense fallback={<div className="flex-1" />}>
          <TransactionsClient
            initialTransactions={transactions}
            categories={categories}
            accounts={accounts}
          />
        </Suspense>
      </div>
    </>
  );
}
