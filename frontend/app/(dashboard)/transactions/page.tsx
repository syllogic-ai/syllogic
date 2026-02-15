import { Suspense } from "react";
import { Header } from "@/components/layout/header";
import { TransactionsClient } from "./transactions-client";
import { getTransactionsPage, getUserAccounts } from "@/lib/actions/transactions";
import { getUserCategories } from "@/lib/actions/categories";
import { parseTransactionsSearchParams } from "@/lib/transactions/query-state";

interface TransactionsPageProps {
  searchParams: Promise<{
    [key: string]: string | string[] | undefined;
  }>;
}

export default async function TransactionsPage({ searchParams }: TransactionsPageProps) {
  const params = await searchParams;
  const queryState = parseTransactionsSearchParams(params);

  const [pageData, categories, accounts] = await Promise.all([
    getTransactionsPage(queryState),
    getUserCategories(),
    getUserAccounts(),
  ]);

  return (
    <>
      <Header title="Transactions" />
      <div className="flex h-[calc(100vh-4rem)] flex-col gap-4 p-4 pt-0">
        <Suspense fallback={<div className="flex-1" />}>
          <TransactionsClient
            initialTransactions={pageData.rows}
            totalCount={pageData.totalCount}
            initialQueryState={queryState}
            categories={categories}
            accounts={accounts}
          />
        </Suspense>
      </div>
    </>
  );
}
