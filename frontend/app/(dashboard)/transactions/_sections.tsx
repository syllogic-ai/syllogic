import { TransactionsClient } from "./transactions-client";
import { getTransactionsPage, getUserAccounts } from "@/lib/actions/transactions";
import { getUserCategories } from "@/lib/actions/categories";
import { getAuthenticatedSession } from "@/lib/auth-helpers";
import { isDemoRestrictedUserEmail } from "@/lib/demo-access";
import type { TransactionsQueryState } from "@/lib/transactions/query-state";

export async function TransactionsSection({
  queryState,
}: {
  queryState: TransactionsQueryState;
}) {
  const session = await getAuthenticatedSession();
  const canImportCsv =
    !!process.env.OPENAI_API_KEY &&
    !isDemoRestrictedUserEmail(session?.user.email);
  const canDelete = !isDemoRestrictedUserEmail(session?.user.email);

  const [pageData, categories, accounts] = await Promise.all([
    getTransactionsPage(queryState),
    getUserCategories(),
    getUserAccounts(),
  ]);

  return (
    <TransactionsClient
      initialTransactions={pageData.rows}
      totalCount={pageData.totalCount}
      filteredTotals={pageData.filteredTotals}
      initialQueryState={queryState}
      categories={categories}
      accounts={accounts}
      canImportCsv={canImportCsv}
      canDelete={canDelete}
    />
  );
}
