"use server";

import { db } from "@/lib/db";
import { accounts, transactions, categories, users, properties, vehicles, accountBalances, transactionLinks } from "@/lib/db/schema";
import { getAuthenticatedSession } from "@/lib/auth-helpers";
import { eq, sql, gte, lte, and, desc, inArray, isNull } from "drizzle-orm";
import { buildConservativeSankey } from "@/lib/dashboard/sankey";

async function getUserCurrency(userId: string): Promise<string> {
  const result = await db
    .select({ functionalCurrency: users.functionalCurrency })
    .from(users)
    .where(eq(users.id, userId))
    .limit(1);

  return result[0]?.functionalCurrency || "EUR";
}

function normalizeAccountIds(accountIds?: string[]): string[] | undefined {
  if (!accountIds?.length) return undefined;
  const uniqueIds = Array.from(new Set(accountIds.map((id) => id.trim()).filter(Boolean)));
  return uniqueIds.length > 0 ? uniqueIds : undefined;
}

function errorToLogContext(error: unknown): {
  message: string;
  cause?: unknown;
  stack?: string;
} {
  if (error instanceof Error) {
    return {
      message: error.message,
      cause: "cause" in error ? (error as Error & { cause?: unknown }).cause : undefined,
      stack: error.stack,
    };
  }

  return {
    message: String(error),
  };
}

async function getLatestTransactionDate(userId: string, accountIds?: string[]): Promise<Date> {
  const normalizedAccountIds = normalizeAccountIds(accountIds);
  const conditions = [eq(transactions.userId, userId)];
  if (normalizedAccountIds?.length) {
    conditions.push(inArray(transactions.accountId, normalizedAccountIds));
  }

  const result = await db
    .select({
      latestDate: sql<string>`MAX(${transactions.bookedAt})`,
    })
    .from(transactions)
    .where(and(...conditions));

  const latestDate = result[0]?.latestDate;
  return latestDate ? new Date(latestDate) : new Date();
}

// Get user accounts for filter dropdown
export async function getUserAccounts() {
  const session = await getAuthenticatedSession();

  if (!session?.user?.id) {
    return [];
  }

  const result = await db
    .select({
      id: accounts.id,
      name: accounts.name,
      institution: accounts.institution,
      accountType: accounts.accountType,
    })
    .from(accounts)
    .where(and(eq(accounts.userId, session.user.id), eq(accounts.isActive, true)))
    .orderBy(accounts.name);

  return result;
}

// Get available months/years for the date selector
export async function getAvailableMonths() {
  const session = await getAuthenticatedSession();

  if (!session?.user?.id) {
    return [];
  }

  const result = await db
    .select({
      year: sql<number>`EXTRACT(YEAR FROM ${transactions.bookedAt})::int`,
      month: sql<number>`EXTRACT(MONTH FROM ${transactions.bookedAt})::int`,
    })
    .from(transactions)
    .where(eq(transactions.userId, session.user.id))
    .groupBy(
      sql`EXTRACT(YEAR FROM ${transactions.bookedAt})`,
      sql`EXTRACT(MONTH FROM ${transactions.bookedAt})`
    )
    .orderBy(
      desc(sql`EXTRACT(YEAR FROM ${transactions.bookedAt})`),
      desc(sql`EXTRACT(MONTH FROM ${transactions.bookedAt})`)
    );

  return result.map((row) => ({
    year: row.year,
    month: row.month,
  }));
}

export async function getTotalBalance(accountIds?: string[]) {
  const session = await getAuthenticatedSession();

  if (!session?.user?.id) {
    return { total: 0, currency: "EUR" };
  }

  // Get user's active account IDs
  const accountConditions = [
    eq(accounts.userId, session.user.id),
    eq(accounts.isActive, true),
  ];
  const normalizedAccountIds = normalizeAccountIds(accountIds);
  if (normalizedAccountIds?.length) {
    accountConditions.push(inArray(accounts.id, normalizedAccountIds));
  }

  const userAccounts = await db
    .select({ id: accounts.id })
    .from(accounts)
    .where(and(...accountConditions));

  if (userAccounts.length === 0) {
    const currency = await getUserCurrency(session.user.id);
    return { total: 0, currency };
  }

  const selectedAccountIds = userAccounts.map((a) => a.id);

  // Get the latest balance for EACH account, then sum them
  // This ensures accounts with different latest dates are all included
  const [result, currency] = await Promise.all([
    db
      .select({
        total: sql<string>`COALESCE(SUM(ab.balance_in_functional_currency), 0)`,
      })
      .from(sql`(
        SELECT DISTINCT ON (account_id) account_id, balance_in_functional_currency
        FROM account_balances
        WHERE account_id IN (${sql.join(selectedAccountIds.map((id) => sql`${id}`), sql`, `)})
        ORDER BY account_id, date DESC
      ) AS ab`),
    getUserCurrency(session.user.id),
  ]);

  return {
    total: parseFloat(result[0]?.total || "0"),
    currency,
  };
}

export async function getBalanceHistory(startDate: Date, endDate: Date, accountIds?: string[]) {
  const session = await getAuthenticatedSession();

  if (!session?.user?.id) {
    return [];
  }

  const normalizedAccountIds = normalizeAccountIds(accountIds);

  // Get user's active account IDs
  const accountConditions = [
    eq(accounts.userId, session.user.id),
    eq(accounts.isActive, true),
  ];
  if (normalizedAccountIds?.length) {
    accountConditions.push(inArray(accounts.id, normalizedAccountIds));
  }

  const userAccounts = await db
    .select({ id: accounts.id })
    .from(accounts)
    .where(and(...accountConditions));

  if (userAccounts.length === 0) {
    return [];
  }

  const selectedAccountIds = userAccounts.map((a) => a.id);

  // Query account_balances table - sum across accounts per day
  const result = await db
    .select({
      date: sql<string>`DATE(${accountBalances.date})`,
      value: sql<string>`SUM(${accountBalances.balanceInFunctionalCurrency})`,
    })
    .from(accountBalances)
    .where(and(
      inArray(accountBalances.accountId, selectedAccountIds),
      gte(accountBalances.date, startDate),
      lte(accountBalances.date, endDate)
    ))
    .groupBy(sql`DATE(${accountBalances.date})`)
    .orderBy(sql`DATE(${accountBalances.date})`);

  return result.map(row => ({
    date: row.date,
    value: parseFloat(row.value || "0"),
  }));
}

export async function getPeriodSpending(startDate: Date, endDate: Date, accountIds?: string[]) {
  const session = await getAuthenticatedSession();

  if (!session?.user?.id) {
    return { total: 0, currency: "EUR" };
  }

  const normalizedAccountIds = normalizeAccountIds(accountIds);

  const conditions = [
    eq(transactions.userId, session.user.id),
    eq(transactions.transactionType, "debit"),
    eq(transactions.includeInAnalytics, true),
    gte(transactions.bookedAt, startDate),
    lte(transactions.bookedAt, endDate),
  ];
  if (normalizedAccountIds?.length) {
    conditions.push(inArray(transactions.accountId, normalizedAccountIds));
  }

  // For linked transactions, use net amount (sum of all in group) for primary
  // Subquery calculates net for each link group
  try {
    const [result, currency] = await Promise.all([
      db
        .select({
          total: sql<string>`COALESCE(SUM(
            CASE
              WHEN ${transactionLinks.linkRole} = 'primary' AND ${transactionLinks.groupId} IS NOT NULL THEN
                COALESCE((
                  SELECT CASE 
                    WHEN COALESCE(SUM(t2.amount), 0) < 0 THEN ABS(COALESCE(SUM(t2.amount), 0))
                    ELSE 0
                  END
                  FROM ${transactions} t2
                  JOIN ${transactionLinks} tl2 ON t2.id = tl2.transaction_id
                  WHERE tl2.group_id = ${transactionLinks.groupId}
                    AND tl2.group_id IS NOT NULL
                ), 0)
              WHEN ${transactionLinks.linkRole} IS NOT NULL THEN 0
              ELSE ABS(${transactions.amount})
            END
          ), 0)`,
        })
        .from(transactions)
        .innerJoin(
          categories,
          sql`${categories.id} = COALESCE(${transactions.categoryId}, ${transactions.categorySystemId})`
        )
        .leftJoin(
          transactionLinks,
          eq(transactions.id, transactionLinks.transactionId)
        )
        .where(and(...conditions, eq(categories.categoryType, "expense"))),
      getUserCurrency(session.user.id),
    ]);

    return {
      total: parseFloat(result[0]?.total || "0"),
      currency,
    };
  } catch (error: unknown) {
    const normalizedError = errorToLogContext(error);
    console.error("[getPeriodSpending] Query failed:", {
      error: normalizedError.message,
      cause: normalizedError.cause,
      stack: normalizedError.stack,
      userId: session.user.id,
    });
    // Return default on error to prevent app crash
    return {
      total: 0,
      currency: await getUserCurrency(session.user.id),
    };
  }
}

export async function getPeriodIncome(startDate: Date, endDate: Date, accountIds?: string[]) {
  const session = await getAuthenticatedSession();

  if (!session?.user?.id) {
    return { total: 0, currency: "EUR" };
  }

  const normalizedAccountIds = normalizeAccountIds(accountIds);

  const conditions = [
    eq(transactions.userId, session.user.id),
    eq(transactions.transactionType, "credit"),
    eq(transactions.includeInAnalytics, true),
    gte(transactions.bookedAt, startDate),
    lte(transactions.bookedAt, endDate),
  ];
  if (normalizedAccountIds?.length) {
    conditions.push(inArray(transactions.accountId, normalizedAccountIds));
  }

  // For linked transactions, use net amount (sum of all in group) for primary
  // Subquery calculates net for each link group
  try {
    const [result, currency] = await Promise.all([
      db
        .select({
          total: sql<string>`COALESCE(SUM(
            CASE
              WHEN ${transactionLinks.linkRole} = 'primary' AND ${transactionLinks.groupId} IS NOT NULL THEN
                COALESCE((
                  SELECT CASE 
                    WHEN COALESCE(SUM(t2.amount), 0) > 0 THEN COALESCE(SUM(t2.amount), 0)
                    ELSE 0
                  END
                  FROM ${transactions} t2
                  JOIN ${transactionLinks} tl2 ON t2.id = tl2.transaction_id
                  WHERE tl2.group_id = ${transactionLinks.groupId}
                    AND tl2.group_id IS NOT NULL
                ), 0)
              WHEN ${transactionLinks.linkRole} IS NOT NULL THEN 0
              ELSE ${transactions.amount}
            END
          ), 0)`,
        })
        .from(transactions)
        .innerJoin(
          categories,
          sql`${categories.id} = COALESCE(${transactions.categoryId}, ${transactions.categorySystemId})`
        )
        .leftJoin(
          transactionLinks,
          eq(transactions.id, transactionLinks.transactionId)
        )
        .where(and(...conditions, eq(categories.categoryType, "income"))),
      getUserCurrency(session.user.id),
    ]);

    return {
      total: parseFloat(result[0]?.total || "0"),
      currency,
    };
  } catch (error: unknown) {
    const normalizedError = errorToLogContext(error);
    console.error("[getPeriodIncome] Query failed:", {
      error: normalizedError.message,
      cause: normalizedError.cause,
      stack: normalizedError.stack,
      userId: session.user.id,
    });
    // Return default on error to prevent app crash
    return {
      total: 0,
      currency: await getUserCurrency(session.user.id),
    };
  }
}

export async function getSpendingHistory(startDate: Date, endDate: Date, accountIds?: string[]) {
  const session = await getAuthenticatedSession();

  if (!session?.user?.id) {
    return [];
  }

  const normalizedAccountIds = normalizeAccountIds(accountIds);

  const conditions = [
    eq(transactions.userId, session.user.id),
    eq(transactions.transactionType, "debit"),
    eq(transactions.includeInAnalytics, true),
    gte(transactions.bookedAt, startDate),
    lte(transactions.bookedAt, endDate),
  ];
  if (normalizedAccountIds?.length) {
    conditions.push(inArray(transactions.accountId, normalizedAccountIds));
  }

  // Only count transactions categorized as 'expense' (excludes transfers)
  const result = await db
    .select({
      date: sql<string>`DATE(${transactions.bookedAt})`,
      value: sql<string>`COALESCE(SUM(ABS(${transactions.amount})), 0)`,
    })
    .from(transactions)
    .innerJoin(
      categories,
      sql`${categories.id} = COALESCE(${transactions.categoryId}, ${transactions.categorySystemId})`
    )
    .where(and(...conditions, eq(categories.categoryType, "expense")))
    .groupBy(sql`DATE(${transactions.bookedAt})`)
    .orderBy(sql`DATE(${transactions.bookedAt})`);

  return result.map((row) => ({
    date: row.date,
    value: parseFloat(row.value),
  }));
}

export async function getIncomeHistory(startDate: Date, endDate: Date, accountIds?: string[]) {
  const session = await getAuthenticatedSession();

  if (!session?.user?.id) {
    return [];
  }

  const normalizedAccountIds = normalizeAccountIds(accountIds);

  const conditions = [
    eq(transactions.userId, session.user.id),
    eq(transactions.transactionType, "credit"),
    eq(transactions.includeInAnalytics, true),
    gte(transactions.bookedAt, startDate),
    lte(transactions.bookedAt, endDate),
  ];
  if (normalizedAccountIds?.length) {
    conditions.push(inArray(transactions.accountId, normalizedAccountIds));
  }

  // Only count transactions categorized as 'income' (excludes transfers)
  const result = await db
    .select({
      date: sql<string>`DATE(${transactions.bookedAt})`,
      value: sql<string>`COALESCE(SUM(${transactions.amount}), 0)`,
    })
    .from(transactions)
    .innerJoin(
      categories,
      sql`${categories.id} = COALESCE(${transactions.categoryId}, ${transactions.categorySystemId})`
    )
    .where(and(...conditions, eq(categories.categoryType, "income")))
    .groupBy(sql`DATE(${transactions.bookedAt})`)
    .orderBy(sql`DATE(${transactions.bookedAt})`);

  return result.map((row) => ({
    date: row.date,
    value: parseFloat(row.value),
  }));
}

export async function getIncomeExpenseData(startDate: Date, endDate: Date, accountIds?: string[]) {
  const session = await getAuthenticatedSession();

  if (!session?.user?.id) {
    return [];
  }

  const normalizedAccountIds = normalizeAccountIds(accountIds);

  const conditions = [
    eq(transactions.userId, session.user.id),
    eq(transactions.includeInAnalytics, true),
    gte(transactions.bookedAt, startDate),
    lte(transactions.bookedAt, endDate),
  ];
  if (normalizedAccountIds?.length) {
    conditions.push(inArray(transactions.accountId, normalizedAccountIds));
  }

  // Get monthly income and expenses in the selected range
  // Filter by category type to exclude transfers
  // For linked transactions: use net amount via subquery
  try {
    const result = await db
    .select({
      year: sql<number>`EXTRACT(YEAR FROM ${transactions.bookedAt})::int`,
      month: sql<number>`EXTRACT(MONTH FROM ${transactions.bookedAt})::int`,
      income: sql<string>`COALESCE(SUM(
        CASE
          WHEN ${categories.categoryType} = 'income' THEN
            CASE
              WHEN ${transactionLinks.linkRole} = 'primary' AND ${transactionLinks.groupId} IS NOT NULL THEN
                COALESCE((
                  SELECT CASE 
                    WHEN COALESCE(SUM(t2.amount), 0) > 0 THEN COALESCE(SUM(t2.amount), 0)
                    ELSE 0
                  END
                  FROM ${transactions} t2
                  JOIN ${transactionLinks} tl2 ON t2.id = tl2.transaction_id
                  WHERE tl2.group_id = ${transactionLinks.groupId}
                    AND tl2.group_id IS NOT NULL
                ), 0)
              WHEN ${transactionLinks.linkRole} IS NOT NULL THEN 0
              ELSE ABS(${transactions.amount})
            END
          ELSE 0
        END
      ), 0)`,
      expenses: sql<string>`COALESCE(SUM(
        CASE
          WHEN ${categories.categoryType} = 'expense' THEN
            CASE
              WHEN ${transactionLinks.linkRole} = 'primary' AND ${transactionLinks.groupId} IS NOT NULL THEN
                COALESCE((
                  SELECT CASE 
                    WHEN COALESCE(SUM(t2.amount), 0) < 0 THEN ABS(COALESCE(SUM(t2.amount), 0))
                    ELSE 0
                  END
                  FROM ${transactions} t2
                  JOIN ${transactionLinks} tl2 ON t2.id = tl2.transaction_id
                  WHERE tl2.group_id = ${transactionLinks.groupId}
                    AND tl2.group_id IS NOT NULL
                ), 0)
              WHEN ${transactionLinks.linkRole} IS NOT NULL THEN 0
              ELSE ABS(${transactions.amount})
            END
          ELSE 0
        END
      ), 0)`,
    })
    .from(transactions)
    .innerJoin(
      categories,
      sql`${categories.id} = COALESCE(${transactions.categoryId}, ${transactions.categorySystemId})`
    )
    .leftJoin(
      transactionLinks,
      eq(transactions.id, transactionLinks.transactionId)
    )
    .where(and(...conditions))
    .groupBy(
      sql`EXTRACT(YEAR FROM ${transactions.bookedAt})`,
      sql`EXTRACT(MONTH FROM ${transactions.bookedAt})`
    )
    .orderBy(
      sql`EXTRACT(YEAR FROM ${transactions.bookedAt})`,
      sql`EXTRACT(MONTH FROM ${transactions.bookedAt})`
    );

    const monthNames = [
      "Jan",
      "Feb",
      "Mar",
      "Apr",
      "May",
      "Jun",
      "Jul",
      "Aug",
      "Sep",
      "Oct",
      "Nov",
      "Dec",
    ];

    const startMonth = new Date(startDate.getFullYear(), startDate.getMonth(), 1);
    const endMonth = new Date(endDate.getFullYear(), endDate.getMonth(), 1);

    // Create array of months in selected range
    const months: { month: string; monthDate: string; income: number; expenses: number }[] = [];
    for (
      let date = new Date(startMonth);
      date <= endMonth;
      date = new Date(date.getFullYear(), date.getMonth() + 1, 1)
    ) {
      const monthLabel = monthNames[date.getMonth()];
      const monthDate = `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-01`;
      months.push({
        month: monthLabel,
        monthDate,
        income: 0,
        expenses: 0,
      });
    }

    // Fill in the data
    for (const row of result) {
      // Find the corresponding month in our array
      const rowDate = new Date(row.year, row.month - 1, 1);
      const monthIndex = months.findIndex((_, i) => {
        const targetDate = new Date(
          startMonth.getFullYear(),
          startMonth.getMonth() + i,
          1
        );
        return (
          targetDate.getFullYear() === rowDate.getFullYear() &&
          targetDate.getMonth() === rowDate.getMonth()
        );
      });

      if (monthIndex !== -1) {
        months[monthIndex].income = parseFloat(row.income);
        months[monthIndex].expenses = parseFloat(row.expenses);
      }
    }

    return months;
  } catch (error: unknown) {
    const normalizedError = errorToLogContext(error);
    console.error("[getIncomeExpenseData] Query failed:", {
      error: normalizedError.message,
      cause: normalizedError.cause,
      stack: normalizedError.stack,
      userId: session.user.id,
    });
    // Return empty array on error to prevent app crash
    return [];
  }
}

export async function getSpendingByCategory(
  startDate: Date,
  endDate: Date,
  accountIds?: string[],
  limit: number = 5
) {
  const session = await getAuthenticatedSession();

  if (!session?.user?.id) {
    return { categories: [], total: 0 };
  }

  const normalizedAccountIds = normalizeAccountIds(accountIds);

  // Build base conditions
  const baseConditions = [
    eq(transactions.userId, session.user.id),
    eq(transactions.transactionType, "debit"),
    eq(transactions.includeInAnalytics, true),
    gte(transactions.bookedAt, startDate),
    lte(transactions.bookedAt, endDate),
  ];
  if (normalizedAccountIds?.length) {
    baseConditions.push(inArray(transactions.accountId, normalizedAccountIds));
  }

  // Get spending by category using net amounts for linked transactions via subquery
  try {
    const categorizedResult = await db
      .select({
        id: categories.id,
        name: categories.name,
        icon: categories.icon,
        color: categories.color,
        amount: sql<string>`COALESCE(SUM(
          CASE
            WHEN ${transactionLinks.linkRole} = 'primary' AND ${transactionLinks.groupId} IS NOT NULL THEN
              COALESCE((
                SELECT CASE 
                  WHEN COALESCE(SUM(t2.amount), 0) < 0 THEN ABS(COALESCE(SUM(t2.amount), 0))
                  ELSE 0
                END
                FROM ${transactions} t2
                JOIN ${transactionLinks} tl2 ON t2.id = tl2.transaction_id
                WHERE tl2.group_id = ${transactionLinks.groupId}
                  AND tl2.group_id IS NOT NULL
              ), 0)
            WHEN ${transactionLinks.linkRole} IS NOT NULL THEN 0
            ELSE ABS(${transactions.amount})
          END
        ), 0)`,
      })
      .from(transactions)
      .innerJoin(
        categories,
        sql`${categories.id} = COALESCE(${transactions.categoryId}, ${transactions.categorySystemId})`
      )
      .leftJoin(
        transactionLinks,
        eq(transactions.id, transactionLinks.transactionId)
      )
      .where(and(...baseConditions, eq(categories.categoryType, "expense")))
      .groupBy(categories.id, categories.name, categories.icon, categories.color)
      .orderBy(desc(sql`COALESCE(SUM(
        CASE
          WHEN ${transactionLinks.linkRole} = 'primary' AND ${transactionLinks.groupId} IS NOT NULL THEN
            COALESCE((
              SELECT CASE 
                WHEN COALESCE(SUM(t2.amount), 0) < 0 THEN ABS(COALESCE(SUM(t2.amount), 0))
                ELSE 0
              END
              FROM ${transactions} t2
              JOIN ${transactionLinks} tl2 ON t2.id = tl2.transaction_id
              WHERE tl2.group_id = ${transactionLinks.groupId}
                AND tl2.group_id IS NOT NULL
            ), 0)
          WHEN ${transactionLinks.linkRole} IS NOT NULL THEN 0
          ELSE ABS(${transactions.amount})
        END
      ), 0)`))
      .limit(limit);

  // Get uncategorized spending (non-linked only)
  const uncategorizedResult = await db
    .select({
      amount: sql<string>`COALESCE(SUM(ABS(${transactions.amount})), 0)`,
    })
    .from(transactions)
    .leftJoin(
      transactionLinks,
      eq(transactions.id, transactionLinks.transactionId)
    )
    .where(
      and(
        ...baseConditions,
        isNull(transactions.categoryId),
        isNull(transactions.categorySystemId),
        isNull(transactionLinks.linkRole)
      )
    );

  // Get total spending using net amounts
  const totalResult = await db
    .select({
      total: sql<string>`COALESCE(SUM(
        CASE
        WHEN ${transactionLinks.linkRole} = 'primary' AND ${transactionLinks.groupId} IS NOT NULL THEN
          COALESCE((
            SELECT CASE 
              WHEN COALESCE(SUM(t2.amount), 0) < 0 THEN ABS(COALESCE(SUM(t2.amount), 0))
              ELSE 0
            END
            FROM ${transactions} t2
            JOIN ${transactionLinks} tl2 ON t2.id = tl2.transaction_id
            WHERE tl2.group_id = ${transactionLinks.groupId}
              AND tl2.group_id IS NOT NULL
          ), 0)
        WHEN ${transactionLinks.linkRole} IS NOT NULL THEN 0
        ELSE ABS(${transactions.amount})
      END
    ), 0)`,
    })
    .from(transactions)
    .innerJoin(
      categories,
      sql`${categories.id} = COALESCE(${transactions.categoryId}, ${transactions.categorySystemId})`
    )
    .leftJoin(
      transactionLinks,
      eq(transactions.id, transactionLinks.transactionId)
    )
    .where(and(...baseConditions, eq(categories.categoryType, "expense")));

    const categorizedCategories = categorizedResult.map((row) => ({
      id: row.id,
      name: row.name,
      icon: row.icon,
      color: row.color,
      amount: parseFloat(row.amount),
    }));

    // Add uncategorized if there's any amount
    const uncategorizedAmount = parseFloat(uncategorizedResult[0]?.amount || "0");
    if (uncategorizedAmount > 0) {
      categorizedCategories.push({
        id: "uncategorized",
        name: "Uncategorized",
        icon: null,
        color: null,
        amount: uncategorizedAmount,
      });
    }

    // Sort by amount and limit
    const sortedCategories = categorizedCategories
      .sort((a, b) => b.amount - a.amount)
      .slice(0, limit);

    return {
      categories: sortedCategories,
      total: parseFloat(totalResult[0]?.total || "0"),
    };
  } catch (error: unknown) {
    const normalizedError = errorToLogContext(error);
    console.error("[getSpendingByCategory] Query failed:", {
      error: normalizedError.message,
      cause: normalizedError.cause,
      stack: normalizedError.stack,
      userId: session.user.id,
    });
    // Return empty result on error to prevent app crash
    return {
      categories: [],
      total: 0,
    };
  }
}

// Asset category types and mapping
type AssetCategoryKey = "cash" | "investment" | "crypto" | "property" | "vehicle" | "other";

const ASSET_CATEGORY_COLORS: Record<AssetCategoryKey, string> = {
  cash: "#3B82F6",
  investment: "#10B981",
  crypto: "#F59E0B",
  property: "#8B5CF6",
  vehicle: "#EC4899",
  other: "#6B7280",
};

const ASSET_CATEGORY_LABELS: Record<AssetCategoryKey, string> = {
  cash: "Cash",
  investment: "Investment",
  crypto: "Crypto",
  property: "Property",
  vehicle: "Vehicle",
  other: "Other",
};

// Map account types to asset categories
function getAssetCategory(accountType: string): AssetCategoryKey {
  const typeMap: Record<string, AssetCategoryKey> = {
    checking: "cash",
    savings: "cash",
    credit: "other",
    investment: "investment",
    brokerage: "investment",
    crypto: "crypto",
    property: "property",
    vehicle: "vehicle",
  };
  return typeMap[accountType.toLowerCase()] || "other";
}

interface AssetAccount {
  id: string;
  name: string;
  institution: string | null;
  value: number;
  percentage: number;
  currency: string;
  initial: string;
}

interface AssetCategory {
  key: AssetCategoryKey;
  label: string;
  color: string;
  value: number;
  percentage: number;
  isActive: boolean;
  accounts: AssetAccount[];
}

interface AssetsOverviewData {
  total: number;
  currency: string;
  categories: AssetCategory[];
}

export async function getAssetsOverview(): Promise<AssetsOverviewData> {
  const session = await getAuthenticatedSession();

  if (!session?.user?.id) {
    return {
      total: 0,
      currency: "EUR",
      categories: Object.keys(ASSET_CATEGORY_LABELS).map((key) => ({
        key: key as AssetCategoryKey,
        label: ASSET_CATEGORY_LABELS[key as AssetCategoryKey],
        color: ASSET_CATEGORY_COLORS[key as AssetCategoryKey],
        value: 0,
        percentage: 0,
        isActive: false,
        accounts: [],
      })),
    };
  }

  const [userAccounts, userProperties, userVehicles, currency] = await Promise.all([
    db
      .select({
        id: accounts.id,
        name: accounts.name,
        accountType: accounts.accountType,
        institution: accounts.institution,
        functionalBalance: accounts.functionalBalance,
        currency: accounts.currency,
      })
      .from(accounts)
      .where(and(eq(accounts.userId, session.user.id), eq(accounts.isActive, true))),
    db
      .select({
        id: properties.id,
        name: properties.name,
        propertyType: properties.propertyType,
        address: properties.address,
        currentValue: properties.currentValue,
        currency: properties.currency,
      })
      .from(properties)
      .where(and(eq(properties.userId, session.user.id), eq(properties.isActive, true))),
    db
      .select({
        id: vehicles.id,
        name: vehicles.name,
        vehicleType: vehicles.vehicleType,
        make: vehicles.make,
        model: vehicles.model,
        year: vehicles.year,
        currentValue: vehicles.currentValue,
        currency: vehicles.currency,
      })
      .from(vehicles)
      .where(and(eq(vehicles.userId, session.user.id), eq(vehicles.isActive, true))),
    getUserCurrency(session.user.id),
  ]);

  // Group accounts by asset category
  const categoryMap = new Map<AssetCategoryKey, AssetAccount[]>();
  let total = 0;

  // Process bank accounts
  for (const account of userAccounts) {
    const category = getAssetCategory(account.accountType);
    const value = parseFloat(account.functionalBalance || "0");

    // Only include positive balances in assets
    if (value > 0) {
      total += value;

      if (!categoryMap.has(category)) {
        categoryMap.set(category, []);
      }

      categoryMap.get(category)!.push({
        id: account.id,
        name: account.name,
        institution: account.institution,
        value,
        percentage: 0, // Will calculate after totals
        currency: account.currency || currency,
        initial: account.name.charAt(0).toUpperCase(),
      });
    }
  }

  // Process properties
  for (const property of userProperties) {
    const value = parseFloat(property.currentValue || "0");

    if (value > 0) {
      total += value;

      if (!categoryMap.has("property")) {
        categoryMap.set("property", []);
      }

      // Extract city/state from address for display
      const addressParts = property.address?.split(",").map(p => p.trim()) || [];
      const location = addressParts.length > 1 ? addressParts.slice(-2).join(", ") : property.address;

      categoryMap.get("property")!.push({
        id: property.id,
        name: property.name,
        institution: location || null, // Use location as "institution" for display
        value,
        percentage: 0,
        currency: property.currency || currency,
        initial: property.name.charAt(0).toUpperCase(),
      });
    }
  }

  // Process vehicles
  for (const vehicle of userVehicles) {
    const value = parseFloat(vehicle.currentValue || "0");

    if (value > 0) {
      total += value;

      if (!categoryMap.has("vehicle")) {
        categoryMap.set("vehicle", []);
      }

      // Build make/model string for display
      const makeModel = [vehicle.make, vehicle.model].filter(Boolean).join(" ") || null;

      categoryMap.get("vehicle")!.push({
        id: vehicle.id,
        name: vehicle.name,
        institution: makeModel, // Use make/model as "institution" for display
        value,
        percentage: 0,
        currency: vehicle.currency || currency,
        initial: vehicle.name.charAt(0).toUpperCase(),
      });
    }
  }

  // Build categories with percentages
  const categoryOrder: AssetCategoryKey[] = ["cash", "investment", "crypto", "property", "vehicle", "other"];

  const categories: AssetCategory[] = categoryOrder.map((key) => {
    const accountsInCategory = categoryMap.get(key) || [];
    const categoryValue = accountsInCategory.reduce((sum, acc) => sum + acc.value, 0);
    const categoryPercentage = total > 0 ? (categoryValue / total) * 100 : 0;

    // Calculate account percentages relative to category total
    const accountsWithPercentages = accountsInCategory.map((acc) => ({
      ...acc,
      percentage: categoryValue > 0 ? (acc.value / categoryValue) * 100 : 0,
    }));

    // Sort accounts by value descending
    accountsWithPercentages.sort((a, b) => b.value - a.value);

    return {
      key,
      label: ASSET_CATEGORY_LABELS[key],
      color: ASSET_CATEGORY_COLORS[key],
      value: categoryValue,
      percentage: categoryPercentage,
      isActive: categoryValue > 0,
      accounts: accountsWithPercentages,
    };
  });

  return {
    total,
    currency,
    categories,
  };
}

export interface SankeyData {
  nodes: {
    name: string;
    categoryId?: string | null;
    categoryType?: "income" | "expense";
    total?: number;
  }[];
  links: { source: number; target: number; value: number }[];
}

export async function getSankeyData(
  startDate?: Date,
  endDate?: Date,
  accountIds?: string[]
): Promise<SankeyData> {
  const session = await getAuthenticatedSession();

  if (!session?.user?.id) {
    return { nodes: [], links: [] };
  }

  const normalizedAccountIds = normalizeAccountIds(accountIds);

  let resolvedStartDate = startDate;
  let resolvedEndDate = endDate;
  if (!resolvedStartDate || !resolvedEndDate) {
    const fallbackRefDate = await getLatestTransactionDate(session.user.id, normalizedAccountIds);
    resolvedEndDate = new Date(fallbackRefDate);
    resolvedEndDate.setHours(23, 59, 59, 999);
    resolvedStartDate = new Date(resolvedEndDate);
    resolvedStartDate.setDate(resolvedStartDate.getDate() - 29);
    resolvedStartDate.setHours(0, 0, 0, 0);
  }
  const rangeStart = resolvedStartDate ?? new Date(0);
  const rangeEnd = resolvedEndDate ?? new Date();

  const conditions = [
    eq(transactions.userId, session.user.id),
    eq(transactions.includeInAnalytics, true),
    gte(transactions.bookedAt, rangeStart),
    lte(transactions.bookedAt, rangeEnd),
  ];
  if (normalizedAccountIds?.length) {
    conditions.push(inArray(transactions.accountId, normalizedAccountIds));
  }

  // Get income by category (categories with type 'income' only, excludes transfers)
  const incomeByCategory = await db
    .select({
      categoryId: sql<string>`COALESCE(${transactions.categoryId}, ${transactions.categorySystemId})`,
      categoryName: categories.name,
      total: sql<string>`COALESCE(SUM(ABS(${transactions.amount})), 0)`,
    })
    .from(transactions)
    .innerJoin(
      categories,
      sql`${categories.id} = COALESCE(${transactions.categoryId}, ${transactions.categorySystemId})`
    )
    .where(
      and(
        ...conditions,
        eq(categories.categoryType, "income")
      )
    )
    .groupBy(
      sql`COALESCE(${transactions.categoryId}, ${transactions.categorySystemId})`,
      categories.name
    )
    .orderBy(desc(sql`SUM(ABS(${transactions.amount}))`));

  // Get expenses by category (categories with type 'expense' only, excludes transfers)
  const expensesByCategory = await db
    .select({
      categoryId: sql<string>`COALESCE(${transactions.categoryId}, ${transactions.categorySystemId})`,
      categoryName: categories.name,
      total: sql<string>`COALESCE(SUM(ABS(${transactions.amount})), 0)`,
    })
    .from(transactions)
    .innerJoin(
      categories,
      sql`${categories.id} = COALESCE(${transactions.categoryId}, ${transactions.categorySystemId})`
    )
    .where(
      and(
        ...conditions,
        eq(categories.categoryType, "expense")
      )
    )
    .groupBy(
      sql`COALESCE(${transactions.categoryId}, ${transactions.categorySystemId})`,
      categories.name
    )
    .orderBy(desc(sql`SUM(ABS(${transactions.amount}))`));

  // Filter and limit categories
  const incomeCategories = incomeByCategory
    .filter(c => parseFloat(c.total) > 0)
    .slice(0, 6);

  const expenseCategories = expensesByCategory
    .filter(c => parseFloat(c.total) > 0)
    .slice(0, 8);

  if (incomeCategories.length === 0 || expenseCategories.length === 0) {
    return { nodes: [], links: [] };
  }

  return buildConservativeSankey(
    incomeCategories.map((category) => ({
      categoryId: category.categoryId,
      categoryName: category.categoryName || "Other Income",
      total: parseFloat(category.total),
      categoryType: "income" as const,
    })),
    expenseCategories.map((category) => ({
      categoryId: category.categoryId,
      categoryName: category.categoryName || "Other Expenses",
      total: parseFloat(category.total),
      categoryType: "expense" as const,
    }))
  );
}

export interface DashboardFilters {
  accountIds?: string[];
  dateFrom?: Date;
  dateTo?: Date;
  horizon?: number;
}

export async function getDashboardData(filters: DashboardFilters = {}) {
  const session = await getAuthenticatedSession();

  const monthNames = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
  ];

  if (!session?.user?.id) {
    return {
      balance: { total: 0, currency: "EUR" },
      balanceHistory: [],
      periodSpending: { total: 0, currency: "EUR" },
      periodIncome: { total: 0, currency: "EUR" },
      savingsRate: { amount: 0, percentage: 0, currency: "EUR" },
      spendingHistory: [],
      incomeHistory: [],
      incomeExpense: [],
      spendingByCategory: { categories: [], total: 0 },
      assetsOverview: {
        total: 0,
        currency: "EUR",
        categories: Object.keys(ASSET_CATEGORY_LABELS).map((key) => ({
          key: key as AssetCategoryKey,
          label: ASSET_CATEGORY_LABELS[key as AssetCategoryKey],
          color: ASSET_CATEGORY_COLORS[key as AssetCategoryKey],
          value: 0,
          percentage: 0,
          isActive: false,
          accounts: [],
        })),
      },
      sankeyData: { nodes: [], links: [] },
      periodLabel: { title: "30-Day", subtitle: "Last 30 days" },
      horizon: 30,
      referencePeriod: {
        month: monthNames[new Date().getMonth()],
        year: new Date().getFullYear(),
        label: `${monthNames[new Date().getMonth()]} ${new Date().getFullYear()}`,
      },
    };
  }

  const normalizedAccountIds = normalizeAccountIds(filters.accountIds);
  const horizonCandidate = filters.horizon ?? 30;
  const horizonDays = Number.isFinite(horizonCandidate) && horizonCandidate > 0
    ? horizonCandidate
    : 30;
  const isDateRangeMode = Boolean(filters.dateFrom);
  const latestTransactionDate = await getLatestTransactionDate(session.user.id, normalizedAccountIds);

  // Canonical window for all dashboard datasets/charts
  let startDate: Date;
  let endDate: Date;
  if (isDateRangeMode && filters.dateFrom) {
    startDate = new Date(filters.dateFrom);
    startDate.setHours(0, 0, 0, 0);
    endDate = filters.dateTo ? new Date(filters.dateTo) : new Date(latestTransactionDate);
    endDate.setHours(23, 59, 59, 999);
    if (endDate < startDate) {
      endDate = new Date(startDate);
      endDate.setHours(23, 59, 59, 999);
    }
  } else {
    endDate = new Date(latestTransactionDate);
    endDate.setHours(23, 59, 59, 999);
    startDate = new Date(endDate);
    startDate.setDate(startDate.getDate() - (horizonDays - 1));
    startDate.setHours(0, 0, 0, 0);
  }

  const currency = await getUserCurrency(session.user.id);

  const [
    balance,
    balanceHistory,
    periodSpending,
    periodIncome,
    spendingHistory,
    incomeHistory,
    incomeExpense,
    spendingByCategory,
    assetsOverview,
    sankeyData,
  ] = await Promise.all([
    getTotalBalance(normalizedAccountIds),
    getBalanceHistory(startDate, endDate, normalizedAccountIds),
    getPeriodSpending(startDate, endDate, normalizedAccountIds),
    getPeriodIncome(startDate, endDate, normalizedAccountIds),
    getSpendingHistory(startDate, endDate, normalizedAccountIds),
    getIncomeHistory(startDate, endDate, normalizedAccountIds),
    getIncomeExpenseData(startDate, endDate, normalizedAccountIds),
    getSpendingByCategory(startDate, endDate, normalizedAccountIds, 5),
    getAssetsOverview(),
    getSankeyData(startDate, endDate, normalizedAccountIds),
  ]);

  // Calculate savings rate (income - expenses = potential savings)
  const savingsAmount = periodIncome.total - periodSpending.total;
  const savingsPercentage = periodIncome.total > 0
    ? (savingsAmount / periodIncome.total) * 100
    : 0;

  const isSameCalendarDay = (a: Date, b: Date) =>
    a.getFullYear() === b.getFullYear() &&
    a.getMonth() === b.getMonth() &&
    a.getDate() === b.getDate();

  const lastDayOfMonth = (date: Date) =>
    new Date(date.getFullYear(), date.getMonth() + 1, 0).getDate();

  const isFullMonthRange = (rangeStart: Date, rangeEnd: Date) =>
    rangeStart.getFullYear() === rangeEnd.getFullYear() &&
    rangeStart.getMonth() === rangeEnd.getMonth() &&
    rangeStart.getDate() === 1 &&
    rangeEnd.getDate() === lastDayOfMonth(rangeEnd);

  const isFullQuarterRange = (rangeStart: Date, rangeEnd: Date) => {
    const quarterStartMonth = Math.floor(rangeStart.getMonth() / 3) * 3;
    const quarterEndMonth = quarterStartMonth + 2;
    return (
      rangeStart.getFullYear() === rangeEnd.getFullYear() &&
      rangeStart.getMonth() === quarterStartMonth &&
      rangeStart.getDate() === 1 &&
      rangeEnd.getMonth() === quarterEndMonth &&
      rangeEnd.getDate() === lastDayOfMonth(rangeEnd)
    );
  };

  const isFullYearRange = (rangeStart: Date, rangeEnd: Date) =>
    rangeStart.getFullYear() === rangeEnd.getFullYear() &&
    rangeStart.getMonth() === 0 &&
    rangeStart.getDate() === 1 &&
    rangeEnd.getMonth() === 11 &&
    rangeEnd.getDate() === 31;

  const getQuarter = (date: Date) => Math.floor(date.getMonth() / 3) + 1;

  const formatShortDate = (date: Date) =>
    date.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
  const formatShortDateNoYear = (date: Date) =>
    date.toLocaleDateString("en-US", { month: "short", day: "numeric" });
  const formatLongMonthYear = (date: Date) =>
    date.toLocaleDateString("en-US", { month: "long", year: "numeric" });

  const getDateModePeriodLabel = (rangeStart: Date, rangeEnd: Date) => {
    if (isFullYearRange(rangeStart, rangeEnd)) {
      return { title: "Year", subtitle: String(rangeStart.getFullYear()) };
    }
    if (isFullQuarterRange(rangeStart, rangeEnd)) {
      return {
        title: "Quarter",
        subtitle: `Q${getQuarter(rangeStart)} ${rangeStart.getFullYear()}`,
      };
    }
    if (isFullMonthRange(rangeStart, rangeEnd)) {
      return { title: "Month", subtitle: formatLongMonthYear(rangeStart) };
    }
    if (isSameCalendarDay(rangeStart, rangeEnd)) {
      return { title: "Day", subtitle: formatShortDate(rangeStart) };
    }
    if (rangeStart.getFullYear() === rangeEnd.getFullYear()) {
      if (rangeStart.getMonth() === rangeEnd.getMonth()) {
        return {
          title: "Custom",
          subtitle: `${rangeStart.toLocaleDateString("en-US", {
            month: "short",
          })} ${rangeStart.getDate()} - ${rangeEnd.getDate()}, ${rangeStart.getFullYear()}`,
        };
      }
      return {
        title: "Custom",
        subtitle: `${formatShortDateNoYear(rangeStart)} - ${formatShortDateNoYear(rangeEnd)}, ${rangeStart.getFullYear()}`,
      };
    }
    return {
      title: "Custom",
      subtitle: `${formatShortDate(rangeStart)} - ${formatShortDate(rangeEnd)}`,
    };
  };

  // Generate period label based on horizon
  const getHorizonPeriodLabel = (h: number) => {
    if (h <= 7) return { title: "7-Day", subtitle: "Last 7 days" };
    if (h <= 30) return { title: "30-Day", subtitle: "Last 30 days" };
    return { title: "12-Month", subtitle: "Last 12 months" };
  };

  const periodLabel = isDateRangeMode
    ? getDateModePeriodLabel(startDate, endDate)
    : getHorizonPeriodLabel(horizonDays);

  return {
    balance,
    balanceHistory,
    periodSpending,
    periodIncome,
    savingsRate: {
      amount: savingsAmount,
      percentage: savingsPercentage,
      currency,
    },
    spendingHistory,
    incomeHistory,
    incomeExpense,
    spendingByCategory,
    assetsOverview,
    sankeyData,
    periodLabel,
    horizon: horizonDays,
    referencePeriod: {
      month: monthNames[endDate.getMonth()],
      year: endDate.getFullYear(),
      label: `${monthNames[endDate.getMonth()]} ${endDate.getFullYear()}`,
    },
  };
}
