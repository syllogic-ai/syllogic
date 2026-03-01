import { Header } from "@/components/layout/header";
import { CategorySpendingClient } from "@/components/category-spending/category-spending-client";
import {
  getCategorySpendingData,
  getCategorySpendingTransactionsPage,
} from "@/lib/actions/category-spending";
import { getUserAccounts } from "@/lib/actions/dashboard";
import { getUserCategories } from "@/lib/actions/categories";
import { parseCategorySpendingSearchParams } from "@/lib/category-spending/query-params";
import { parseTransactionsSearchParams } from "@/lib/transactions/query-state";

interface CategorySpendingPageProps {
  searchParams: Promise<{
    [key: string]: string | string[] | undefined;
  }>;
}

export default async function CategorySpendingPage({
  searchParams,
}: CategorySpendingPageProps) {
  const params = await searchParams;
  const parsed = parseCategorySpendingSearchParams(params);
  const tableQueryState = parseTransactionsSearchParams(params);

  const [data, transactionsPage, accounts, categories] = await Promise.all([
    getCategorySpendingData({
      accountIds: parsed.accountIds,
      dateFrom: parsed.dateFrom,
      dateTo: parsed.dateTo,
      horizon: parsed.effectiveHorizon,
    }),
    getCategorySpendingTransactionsPage({
      accountIds: parsed.accountIds,
      dateFrom: parsed.dateFrom,
      dateTo: parsed.dateTo,
      horizon: parsed.effectiveHorizon,
      categoryIds: parsed.categoryIds,
      page: parsed.page,
      pageSize: parsed.pageSize,
      sort: parsed.sort,
      order: parsed.order,
    }),
    getUserAccounts(),
    getUserCategories(),
  ]);

  return (
    <>
      <Header title="Category Spending" />
      <CategorySpendingClient
        data={data}
        query={parsed}
        initialSelectedCategoryIds={parsed.categoryIds}
        transactions={transactionsPage.rows}
        transactionsTotalCount={transactionsPage.totalCount}
        transactionsQueryState={tableQueryState}
        accounts={accounts}
        categories={categories}
      />
    </>
  );
}
