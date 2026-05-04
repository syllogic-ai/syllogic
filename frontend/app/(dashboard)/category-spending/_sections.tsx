import { CategorySpendingClient } from "@/components/category-spending/category-spending-client";
import {
  getCategorySpendingData,
  getCategorySpendingTransactionsPage,
} from "@/lib/actions/category-spending";
import { getUserAccounts } from "@/lib/actions/dashboard";
import { getUserCategories } from "@/lib/actions/categories";
import type { ParsedCategorySpendingQueryParams } from "@/lib/category-spending/query-params";
import type { TransactionsQueryState } from "@/lib/transactions/query-state";

export async function CategorySpendingSection({
  parsed,
  tableQueryState,
}: {
  parsed: ParsedCategorySpendingQueryParams;
  tableQueryState: TransactionsQueryState;
}) {
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
  );
}
