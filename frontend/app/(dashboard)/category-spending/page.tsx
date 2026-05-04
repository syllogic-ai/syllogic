import { Suspense } from "react";
import { Header } from "@/components/layout/header";
import { ChartSkeleton, FiltersSkeleton, TableSkeleton } from "@/components/skeletons/page-skeletons";
import { parseCategorySpendingSearchParams } from "@/lib/category-spending/query-params";
import { parseTransactionsSearchParams } from "@/lib/transactions/query-state";
import { CategorySpendingSection } from "./_sections";

interface CategorySpendingPageProps {
  searchParams: Promise<{
    [key: string]: string | string[] | undefined;
  }>;
}

export default async function CategorySpendingPage({ searchParams }: CategorySpendingPageProps) {
  const params = await searchParams;
  const parsed = parseCategorySpendingSearchParams(params);
  const tableQueryState = parseTransactionsSearchParams(params);

  return (
    <>
      <Header title="Category Spending" />
      <Suspense
        key={JSON.stringify({ parsed, tableQueryState })}
        fallback={
          <div className="flex flex-1 flex-col gap-4 p-4 pt-0">
            <FiltersSkeleton />
            <ChartSkeleton height={360} />
            <TableSkeleton rows={10} />
          </div>
        }
      >
        <CategorySpendingSection parsed={parsed} tableQueryState={tableQueryState} />
      </Suspense>
    </>
  );
}
