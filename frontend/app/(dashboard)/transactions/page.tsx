import { Suspense } from "react";
import { Header } from "@/components/layout/header";
import { TableSkeleton, FiltersSkeleton } from "@/components/skeletons/page-skeletons";
import { parseTransactionsSearchParams } from "@/lib/transactions/query-state";
import { TransactionsSection } from "./_sections";

interface TransactionsPageProps {
  searchParams: Promise<{
    [key: string]: string | string[] | undefined;
  }>;
}

export default async function TransactionsPage({ searchParams }: TransactionsPageProps) {
  const params = await searchParams;
  const queryState = parseTransactionsSearchParams(params);

  return (
    <>
      <Header title="Transactions" />
      <div className="flex h-[calc(100vh-4rem)] flex-col gap-4 p-4 pt-0">
        <Suspense
          key={JSON.stringify(queryState)}
          fallback={
            <>
              <FiltersSkeleton />
              <TableSkeleton rows={14} />
            </>
          }
        >
          <TransactionsSection queryState={queryState} />
        </Suspense>
      </div>
    </>
  );
}
