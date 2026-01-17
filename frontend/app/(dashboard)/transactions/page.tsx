import { Header } from "@/components/layout/header";
import { TransactionsClient } from "./transactions-client";
import { getTransactions, getUserCategories } from "@/lib/actions/transactions";

export default async function TransactionsPage() {
  const [transactions, categories] = await Promise.all([
    getTransactions(),
    getUserCategories(),
  ]);

  return (
    <>
      <Header title="Transactions" />
      <div className="flex h-[calc(100vh-4rem)] flex-col gap-4 p-4 pt-0">
        <TransactionsClient
          initialTransactions={transactions}
          categories={categories}
        />
      </div>
    </>
  );
}
