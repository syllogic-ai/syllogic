"use server";

import {
  endOfDay,
  endOfMonth,
  startOfDay,
  startOfMonth,
  subDays,
} from "date-fns";
import {
  and,
  asc,
  desc,
  eq,
  gte,
  inArray,
  isNull,
  lte,
  or,
  sql,
  type SQLWrapper,
} from "drizzle-orm";
import type { SupportedHorizon } from "@/lib/dashboard/query-params";
import { getAuthenticatedSession } from "@/lib/auth-helpers";
import { db } from "@/lib/db";
import { categories, transactions, transactionLinks, users } from "@/lib/db/schema";
import { resolveMissingAccountLogos } from "@/lib/actions/account-logos";
import type { TransactionWithRelations } from "@/lib/actions/transactions";
import type {
  CategorySpendingSortField,
  CategorySpendingSortOrder,
} from "@/lib/category-spending/query-params";
import {
  computePreviousWindow,
  formatIsoDate,
  getTouchedMonthKeys,
  parseIsoDateAtEndOfDay,
  parseIsoDateAtStartOfDay,
  resolveCategoryColor,
} from "@/lib/category-spending/helpers";

export interface CategorySpendingFilters {
  accountIds?: string[];
  dateFrom?: string;
  dateTo?: string;
  horizon?: SupportedHorizon;
}

export interface CategorySpendingTransactionsFilters extends CategorySpendingFilters {
  categoryIds?: string[];
  page?: number;
  pageSize?: number;
  sort?: CategorySpendingSortField;
  order?: CategorySpendingSortOrder;
}

interface RawCategoryAmount {
  id: string;
  name: string;
  color: string | null;
  icon: string | null;
  amount: number;
}

export interface CategorySpendingCategory {
  id: string;
  name: string;
  color: string | null;
  icon: string | null;
  fill: string;
  amount: number;
  sharePct: number;
  deltaAmount: number;
  deltaPct: number;
  averageMonthlyAmount: number;
}

export interface CategorySpendingSummary {
  totalSpend: number;
  averageMonthlySpend: number;
  topCategory: {
    id: string;
    name: string;
    amount: number;
  } | null;
}

export interface CategorySpendingData {
  currency: string;
  categories: CategorySpendingCategory[];
  summary: CategorySpendingSummary;
  range: {
    startDate: string;
    endDate: string;
    comparisonStartDate: string;
    comparisonEndDate: string;
    monthCount: number;
    referenceDate: string;
  };
}

export interface CategorySpendingTransactionsPageResult {
  rows: TransactionWithRelations[];
  totalCount: number;
  page: number;
  pageSize: number;
}

const DEFAULT_PAGE = 1;
const DEFAULT_PAGE_SIZE = 20;
const MIN_PAGE_SIZE = 10;
const MAX_PAGE_SIZE = 100;

interface CategorySpendingTransactionRowWithRelations {
  id: string;
  accountId: string;
  description: string | null;
  merchant: string | null;
  amount: string;
  currency: string | null;
  categoryId: string | null;
  categorySystemId: string | null;
  recurringTransactionId: string | null;
  bookedAt: Date;
  pending: boolean | null;
  transactionType: string | null;
  includeInAnalytics: boolean;
  account: {
    id: string;
    name: string;
    institution: string | null;
    accountType: string;
    logoId: string | null;
    logo: {
      id: string;
      logoUrl: string | null;
      updatedAt: Date | null;
    } | null;
  } | null;
  category: {
    id: string;
    name: string;
    color: string | null;
    icon: string | null;
  } | null;
  categorySystem: {
    id: string;
    name: string;
    color: string | null;
    icon: string | null;
  } | null;
  recurringTransaction: {
    id: string;
    name: string;
    merchant: string | null;
    frequency: string;
  } | null;
  transactionLink: {
    groupId: string;
    linkRole: string;
  } | null;
}

function normalizeAccountIds(accountIds?: string[]): string[] {
  if (!accountIds?.length) {
    return [];
  }

  return Array.from(new Set(accountIds.map((id) => id.trim()).filter(Boolean)));
}

function normalizeCategoryIds(categoryIds?: string[]): string[] {
  if (!categoryIds?.length) {
    return [];
  }

  return Array.from(new Set(categoryIds.map((id) => id.trim()).filter(Boolean)));
}

function normalizePage(value?: number): number {
  if (!value || !Number.isFinite(value)) {
    return DEFAULT_PAGE;
  }
  return Math.max(DEFAULT_PAGE, Math.floor(value));
}

function normalizePageSize(value?: number): number {
  if (!value || !Number.isFinite(value)) {
    return DEFAULT_PAGE_SIZE;
  }
  return Math.max(MIN_PAGE_SIZE, Math.min(MAX_PAGE_SIZE, Math.floor(value)));
}

function resolveTransactionSortOrder(
  sort: CategorySpendingSortField,
  order: CategorySpendingSortOrder
) {
  if (sort === "amount") {
    return order === "asc"
      ? [asc(transactions.amount), desc(transactions.bookedAt)]
      : [desc(transactions.amount), desc(transactions.bookedAt)];
  }
  if (sort === "description") {
    return order === "asc"
      ? [asc(transactions.description), desc(transactions.bookedAt)]
      : [desc(transactions.description), desc(transactions.bookedAt)];
  }
  if (sort === "merchant") {
    return order === "asc"
      ? [asc(transactions.merchant), desc(transactions.bookedAt)]
      : [desc(transactions.merchant), desc(transactions.bookedAt)];
  }

  return order === "asc"
    ? [asc(transactions.bookedAt), desc(transactions.id)]
    : [desc(transactions.bookedAt), desc(transactions.id)];
}

async function getUserCurrency(userId: string): Promise<string> {
  const result = await db
    .select({ functionalCurrency: users.functionalCurrency })
    .from(users)
    .where(eq(users.id, userId))
    .limit(1);

  return result[0]?.functionalCurrency || "EUR";
}

async function getLatestTransactionDate(
  userId: string,
  accountIds: string[]
): Promise<Date> {
  const conditions = [eq(transactions.userId, userId)];
  if (accountIds.length > 0) {
    conditions.push(inArray(transactions.accountId, accountIds));
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

function resolvePrimaryRange(
  filters: CategorySpendingFilters,
  referenceDate: Date
): {
  startDate: Date;
  endDate: Date;
} {
  if (filters.dateFrom) {
    const startDate = parseIsoDateAtStartOfDay(filters.dateFrom);
    const endDate = filters.dateTo
      ? parseIsoDateAtEndOfDay(filters.dateTo)
      : endOfDay(referenceDate);

    if (endDate < startDate) {
      return {
        startDate,
        endDate: endOfDay(startDate),
      };
    }

    return {
      startDate,
      endDate,
    };
  }

  if (filters.horizon) {
    const endDate = endOfDay(referenceDate);
    return {
      startDate: startOfDay(subDays(endDate, filters.horizon - 1)),
      endDate,
    };
  }

  return {
    startDate: startOfMonth(referenceDate),
    endDate: endOfMonth(referenceDate),
  };
}

async function fetchCategoryAmounts(
  userId: string,
  startDate: Date,
  endDate: Date,
  accountIds: string[]
): Promise<RawCategoryAmount[]> {
  const baseConditions = [
    eq(transactions.userId, userId),
    eq(transactions.transactionType, "debit"),
    eq(transactions.includeInAnalytics, true),
    gte(transactions.bookedAt, startDate),
    lte(transactions.bookedAt, endDate),
  ];

  if (accountIds.length > 0) {
    baseConditions.push(inArray(transactions.accountId, accountIds));
  }

  const categorizedResult = await db
    .select({
      id: categories.id,
      name: categories.name,
      color: categories.color,
      icon: categories.icon,
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
    .leftJoin(transactionLinks, eq(transactions.id, transactionLinks.transactionId))
    .where(and(...baseConditions, eq(categories.categoryType, "expense")))
    .groupBy(categories.id, categories.name, categories.color, categories.icon)
    .orderBy(
      desc(
        sql`COALESCE(SUM(
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
        ), 0)`
      )
    );

  const uncategorizedResult = await db
    .select({
      amount: sql<string>`COALESCE(SUM(ABS(${transactions.amount})), 0)`,
    })
    .from(transactions)
    .leftJoin(transactionLinks, eq(transactions.id, transactionLinks.transactionId))
    .where(
      and(
        ...baseConditions,
        isNull(transactions.categoryId),
        isNull(transactions.categorySystemId),
        isNull(transactionLinks.linkRole)
      )
    );

  const items: RawCategoryAmount[] = categorizedResult.map((row) => ({
    id: row.id,
    name: row.name,
    color: row.color,
    icon: row.icon,
    amount: parseFloat(row.amount || "0"),
  }));

  const uncategorizedAmount = parseFloat(uncategorizedResult[0]?.amount || "0");
  if (uncategorizedAmount > 0) {
    items.push({
      id: "uncategorized",
      name: "Uncategorized",
      color: null,
      icon: null,
      amount: uncategorizedAmount,
    });
  }

  return items.sort((a, b) => b.amount - a.amount);
}

function mapCategorySpendingTransactionRowsForUi(
  rows: CategorySpendingTransactionRowWithRelations[]
): TransactionWithRelations[] {
  return rows.flatMap((tx) => {
    if (!tx.account) {
      console.warn("[getCategorySpendingTransactionsPage] Transaction missing account relation", {
        transactionId: tx.id,
        accountId: tx.accountId,
      });
      return [];
    }

    return [
      {
        id: tx.id,
        accountId: tx.accountId,
        account: {
          id: tx.account.id,
          name: tx.account.name,
          institution: tx.account.institution,
          accountType: tx.account.accountType,
          logo: tx.account.logo
            ? {
                id: tx.account.logo.id,
                logoUrl: tx.account.logo.logoUrl,
                updatedAt: tx.account.logo.updatedAt,
              }
            : null,
        },
        description: tx.description,
        merchant: tx.merchant,
        amount: parseFloat(tx.amount),
        currency: tx.currency,
        categoryId: tx.categoryId,
        category: tx.category
          ? {
              id: tx.category.id,
              name: tx.category.name,
              color: tx.category.color,
              icon: tx.category.icon,
            }
          : null,
        categorySystemId: tx.categorySystemId,
        categorySystem: tx.categorySystem
          ? {
              id: tx.categorySystem.id,
              name: tx.categorySystem.name,
              color: tx.categorySystem.color,
              icon: tx.categorySystem.icon,
            }
          : null,
        recurringTransactionId: tx.recurringTransactionId,
        recurringTransaction: tx.recurringTransaction
          ? {
              id: tx.recurringTransaction.id,
              name: tx.recurringTransaction.name,
              merchant: tx.recurringTransaction.merchant,
              frequency: tx.recurringTransaction.frequency,
            }
          : null,
        transactionLink: tx.transactionLink
          ? {
              groupId: tx.transactionLink.groupId,
              linkRole: tx.transactionLink.linkRole,
            }
          : null,
        bookedAt: tx.bookedAt,
        pending: tx.pending,
        transactionType: tx.transactionType,
        includeInAnalytics: tx.includeInAnalytics,
      },
    ];
  });
}

async function hydrateCategorySpendingTransactionRowsWithResolvedAccountLogos(
  rows: CategorySpendingTransactionRowWithRelations[]
): Promise<CategorySpendingTransactionRowWithRelations[]> {
  const uniqueAccounts = Array.from(
    new Map(
      rows
        .filter((row) => row.account)
        .map((row) => [
          row.account!.id,
          {
            id: row.account!.id,
            institution: row.account!.institution,
            logoId: row.account!.logoId,
            logo: row.account!.logo,
          },
        ])
    ).values()
  );

  const resolvedAccounts = await resolveMissingAccountLogos(uniqueAccounts);
  const resolvedById = new Map(resolvedAccounts.map((account) => [account.id, account]));

  return rows.map((row) => {
    if (!row.account) {
      return row;
    }

    const resolved = resolvedById.get(row.account.id);
    if (!resolved) {
      return row;
    }

    return {
      ...row,
      account: {
        ...row.account,
        logoId: resolved.logoId,
        logo: resolved.logo
          ? {
              id: resolved.logo.id,
              logoUrl: resolved.logo.logoUrl,
              updatedAt: resolved.logo.updatedAt ?? null,
            }
          : null,
      },
    };
  });
}

export async function getCategorySpendingData(
  filters: CategorySpendingFilters = {}
): Promise<CategorySpendingData> {
  const session = await getAuthenticatedSession();

  if (!session?.user?.id) {
    return {
      currency: "EUR",
      categories: [],
      summary: {
        totalSpend: 0,
        averageMonthlySpend: 0,
        topCategory: null,
      },
      range: {
        startDate: formatIsoDate(new Date()),
        endDate: formatIsoDate(new Date()),
        comparisonStartDate: formatIsoDate(new Date()),
        comparisonEndDate: formatIsoDate(new Date()),
        monthCount: 1,
        referenceDate: formatIsoDate(new Date()),
      },
    };
  }

  const normalizedAccountIds = normalizeAccountIds(filters.accountIds);
  const [currency, referenceDate] = await Promise.all([
    getUserCurrency(session.user.id),
    getLatestTransactionDate(session.user.id, normalizedAccountIds),
  ]);

  const { startDate, endDate } = resolvePrimaryRange(filters, referenceDate);
  const { comparisonStart, comparisonEnd } = computePreviousWindow(startDate, endDate);

  const [currentCategories, previousCategories] = await Promise.all([
    fetchCategoryAmounts(session.user.id, startDate, endDate, normalizedAccountIds),
    fetchCategoryAmounts(
      session.user.id,
      comparisonStart,
      comparisonEnd,
      normalizedAccountIds
    ),
  ]);

  const previousById = new Map(previousCategories.map((item) => [item.id, item.amount]));
  const totalSpend = currentCategories.reduce((sum, item) => sum + item.amount, 0);
  const monthCount = Math.max(1, getTouchedMonthKeys(startDate, endDate).length);

  const categoriesWithMetrics: CategorySpendingCategory[] = currentCategories.map((item, index) => {
    const previousAmount = previousById.get(item.id) ?? 0;
    const deltaAmount = item.amount - previousAmount;
    const deltaPct =
      previousAmount > 0
        ? (deltaAmount / previousAmount) * 100
        : item.amount > 0
          ? 100
          : 0;

    return {
      id: item.id,
      name: item.name,
      color: item.color,
      icon: item.icon,
      fill: resolveCategoryColor(item.color, index),
      amount: item.amount,
      sharePct: totalSpend > 0 ? (item.amount / totalSpend) * 100 : 0,
      deltaAmount,
      deltaPct,
      averageMonthlyAmount: item.amount / monthCount,
    };
  });

  const topCategory = categoriesWithMetrics[0]
    ? {
        id: categoriesWithMetrics[0].id,
        name: categoriesWithMetrics[0].name,
        amount: categoriesWithMetrics[0].amount,
      }
    : null;

  return {
    currency,
    categories: categoriesWithMetrics,
    summary: {
      totalSpend,
      averageMonthlySpend: totalSpend / monthCount,
      topCategory,
    },
    range: {
      startDate: formatIsoDate(startDate),
      endDate: formatIsoDate(endDate),
      comparisonStartDate: formatIsoDate(comparisonStart),
      comparisonEndDate: formatIsoDate(comparisonEnd),
      monthCount,
      referenceDate: formatIsoDate(referenceDate),
    },
  };
}

export async function getCategorySpendingTransactionsPage(
  filters: CategorySpendingTransactionsFilters = {}
): Promise<CategorySpendingTransactionsPageResult> {
  const session = await getAuthenticatedSession();

  const page = normalizePage(filters.page);
  const pageSize = normalizePageSize(filters.pageSize);
  const sort = filters.sort ?? "bookedAt";
  const order = filters.order ?? "desc";

  if (!session?.user?.id) {
    return {
      rows: [],
      totalCount: 0,
      page,
      pageSize,
    };
  }

  const normalizedAccountIds = normalizeAccountIds(filters.accountIds);
  const normalizedCategoryIds = normalizeCategoryIds(filters.categoryIds);
  const userId = session.user.id;

  const referenceDate = await getLatestTransactionDate(userId, normalizedAccountIds);
  const { startDate, endDate } = resolvePrimaryRange(filters, referenceDate);

  const expenseCategories = await db
    .select({ id: categories.id })
    .from(categories)
    .where(and(eq(categories.userId, userId), eq(categories.categoryType, "expense")));

  const expenseCategoryIds = expenseCategories.map((category) => category.id);
  const uncategorizedCondition = and(
    isNull(transactions.categoryId),
    isNull(transactions.categorySystemId)
  )!;

  const conditions: SQLWrapper[] = [
    eq(transactions.userId, userId),
    eq(transactions.transactionType, "debit"),
    eq(transactions.includeInAnalytics, true),
    gte(transactions.bookedAt, startDate),
    lte(transactions.bookedAt, endDate),
  ];

  if (normalizedAccountIds.length > 0) {
    conditions.push(inArray(transactions.accountId, normalizedAccountIds));
  }

  if (expenseCategoryIds.length > 0) {
    conditions.push(
      or(
        uncategorizedCondition,
        sql`COALESCE(${transactions.categoryId}, ${transactions.categorySystemId}) IN (${sql.join(
          expenseCategoryIds.map((id) => sql`${id}`),
          sql`, `
        )})`
      )!
    );
  } else {
    conditions.push(uncategorizedCondition);
  }

  if (normalizedCategoryIds.length > 0) {
    const includesUncategorized = normalizedCategoryIds.includes("uncategorized");
    const concreteIds = normalizedCategoryIds.filter((id) => id !== "uncategorized");
    const selectedConditions: SQLWrapper[] = [];

    if (concreteIds.length > 0) {
      selectedConditions.push(
        sql`COALESCE(${transactions.categoryId}, ${transactions.categorySystemId}) IN (${sql.join(
          concreteIds.map((id) => sql`${id}`),
          sql`, `
        )})`
      );
    }

    if (includesUncategorized) {
      selectedConditions.push(uncategorizedCondition);
    }

    if (selectedConditions.length === 0) {
      conditions.push(sql`1 = 0`);
    } else {
      conditions.push(or(...selectedConditions)!);
    }
  }

  const whereClause = and(...conditions)!;

  const [countRows, rows] = await Promise.all([
    db
      .select({
        count: sql<number>`COUNT(*)::int`,
      })
      .from(transactions)
      .where(whereClause),
    db.query.transactions.findMany({
      where: whereClause,
      orderBy: resolveTransactionSortOrder(sort, order),
      limit: pageSize,
      offset: (page - 1) * pageSize,
      with: {
        account: {
          with: {
            logo: {
              columns: {
                id: true,
                logoUrl: true,
                updatedAt: true,
              },
            },
          },
        },
        category: true,
        categorySystem: true,
        recurringTransaction: true,
        transactionLink: true,
      },
    }),
  ]);

  const hydratedRows = await hydrateCategorySpendingTransactionRowsWithResolvedAccountLogos(
    rows
  );

  return {
    rows: mapCategorySpendingTransactionRowsForUi(hydratedRows),
    totalCount: countRows[0]?.count ?? 0,
    page,
    pageSize,
  };
}
