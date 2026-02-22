"use server";

import { revalidatePath } from "next/cache";
import { eq, and, desc, inArray, sql, gte, lte, gt, asc, ne, or, ilike, isNull } from "drizzle-orm";
import { db } from "@/lib/db";
import { transactions, accounts, categories, accountBalances } from "@/lib/db/schema";
import { requireAuth } from "@/lib/auth-helpers";
import { getBackendBaseUrl } from "@/lib/backend-url";
import { createInternalAuthHeaders } from "@/lib/internal-auth";
import { resolveMissingAccountLogos } from "@/lib/actions/account-logos";
import type {
  TransactionSortField,
  TransactionSortOrder,
  TransactionsQueryState,
} from "@/lib/transactions/query-state";
import { hasActiveTransactionFilters } from "@/lib/transactions/query-state";

export interface CreateTransactionInput {
  accountId: string;
  amount: number;
  description: string;
  categoryId?: string;
  bookedAt: Date;
  transactionType: "debit" | "credit";
  merchant?: string;
}

/**
 * Recalculates account_balances records from a given date.
 * Stops at the earlier of:
 * - The next balancing transfer date (exclusive - day before)
 * - The most recent date in account_balances table (if no balancing transfers ahead)
 *
 * @param accountId - The account to recalculate balances for
 * @param fromDate - The starting date for recalculation
 * @param startingBalance - The account's starting balance
 * @param excludeTransactionId - Optional transaction ID to exclude (when deleting)
 */
async function recalculateAccountBalancesFromDate(
  accountId: string,
  fromDate: Date,
  startingBalance: number,
  excludeTransactionId?: string
): Promise<void> {
  // Normalize fromDate to start of day
  const startDate = new Date(fromDate);
  startDate.setHours(0, 0, 0, 0);

  // Get the "Balancing Transfer" category ID for this account's user
  const account = await db.query.accounts.findFirst({
    where: eq(accounts.id, accountId),
  });

  if (!account) {
    console.error("Account not found for balance recalculation");
    return;
  }

  const balancingCategory = await db.query.categories.findFirst({
    where: and(
      eq(categories.userId, account.userId),
      eq(categories.name, "Balancing Transfer")
    ),
  });

  // Find the next balancing transfer AFTER fromDate
  // Use the original fromDate (exact timestamp), not startDate (beginning of day)
  // This ensures we don't find the transaction we just created as the "next" one
  let nextBalancingTransferDate: Date | null = null;
  if (balancingCategory) {
    const conditions = [
      eq(transactions.accountId, accountId),
      eq(transactions.categoryId, balancingCategory.id),
      gt(transactions.bookedAt, fromDate)
    ];

    // Exclude the transaction being deleted if provided
    if (excludeTransactionId) {
      conditions.push(ne(transactions.id, excludeTransactionId));
    }

    const nextBalancingTransfer = await db.query.transactions.findFirst({
      where: and(...conditions),
      orderBy: [asc(transactions.bookedAt)],
    });

    if (nextBalancingTransfer) {
      nextBalancingTransferDate = new Date(nextBalancingTransfer.bookedAt);
    }
  }

  // Find the most recent balance date in account_balances
  const mostRecentBalance = await db.query.accountBalances.findFirst({
    where: eq(accountBalances.accountId, accountId),
    orderBy: [desc(accountBalances.date)],
  });

  // Determine end date for recalculation
  let endDate: Date;
  const today = new Date();
  today.setHours(23, 59, 59, 999);

  if (nextBalancingTransferDate) {
    // Stop the day BEFORE the next balancing transfer
    endDate = new Date(nextBalancingTransferDate);
    endDate.setDate(endDate.getDate() - 1);
    endDate.setHours(23, 59, 59, 999);
  } else if (mostRecentBalance) {
    // No balancing transfer ahead
    const mostRecentDate = new Date(mostRecentBalance.date);
    mostRecentDate.setHours(23, 59, 59, 999);

    // Use the later of: most recent balance date OR today
    // This handles the case where we're adding a balancing transfer after existing records
    if (mostRecentDate >= startDate) {
      endDate = mostRecentDate;
    } else {
      // Most recent balance is before our start date, recalculate to today
      endDate = today;
    }
  } else {
    // Fallback to today (initial setup case)
    endDate = today;
  }

  // Ensure we don't go past today
  if (endDate > today) {
    endDate = today;
  }

  // Iterate through each day from fromDate to endDate
  const currentDate = new Date(startDate);

  while (currentDate <= endDate) {
    // Calculate balance up to end of this day
    const endOfDay = new Date(currentDate);
    endOfDay.setHours(23, 59, 59, 999);

    // Build conditions for balance calculation, excluding the deleted transaction
    const balanceConditions = [
      eq(transactions.accountId, accountId),
      lte(transactions.bookedAt, endOfDay)
    ];

    if (excludeTransactionId) {
      balanceConditions.push(ne(transactions.id, excludeTransactionId));
    }

    const balanceResult = await db
      .select({
        total: sql<string>`COALESCE(SUM(${transactions.amount}), 0)`,
      })
      .from(transactions)
      .where(and(...balanceConditions));

    const transactionSum = parseFloat(balanceResult[0]?.total || "0");
    const balanceOnDate = startingBalance + transactionSum;

    // Normalize date to midnight for storage (matching backend behavior)
    const dateForStorage = new Date(currentDate);
    dateForStorage.setHours(0, 0, 0, 0);

    // Check if a record exists for this date
    const existingRecord = await db.query.accountBalances.findFirst({
      where: and(
        eq(accountBalances.accountId, accountId),
        eq(accountBalances.date, dateForStorage)
      ),
    });

    if (existingRecord) {
      // Update existing record
      await db
        .update(accountBalances)
        .set({
          balanceInAccountCurrency: balanceOnDate.toFixed(2),
          balanceInFunctionalCurrency: balanceOnDate.toFixed(2),
          updatedAt: new Date(),
        })
        .where(eq(accountBalances.id, existingRecord.id));
    } else {
      // Insert new record
      await db.insert(accountBalances).values({
        accountId,
        date: dateForStorage,
        balanceInAccountCurrency: balanceOnDate.toFixed(2),
        balanceInFunctionalCurrency: balanceOnDate.toFixed(2),
      });
    }

    // Move to next day
    currentDate.setDate(currentDate.getDate() + 1);
  }
}

export async function createTransaction(
  input: CreateTransactionInput
): Promise<{ success: boolean; error?: string; transactionId?: string }> {
  const userId = await requireAuth();

  if (!userId) {
    return { success: false, error: "Not authenticated" };
  }

  try {
    // Call backend API to import the transaction
    const backendUrl = getBackendBaseUrl();
    const pathWithQuery = "/api/transactions/import";

    const response = await fetch(`${backendUrl}${pathWithQuery}`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...createInternalAuthHeaders({
          method: "POST",
          pathWithQuery,
          userId,
        }),
      },
      body: JSON.stringify({
        transactions: [
          {
            account_id: input.accountId,
            amount: input.amount,
            description: input.description,
            merchant: input.merchant || null,
            booked_at: input.bookedAt.toISOString(),
            transaction_type: input.transactionType,
            category_id: input.categoryId || null, // Pre-selected category (skips AI categorization)
          },
        ],
        sync_exchange_rates: true,
        update_functional_amounts: true,
        calculate_balances: true,
      }),
    });

    if (!response.ok) {
      const errorText = await response.text();
      console.error("Backend import failed:", response.status, errorText);
      return { success: false, error: `Failed to create transaction: ${response.status}` };
    }

    const backendResponse = await response.json();

    if (!backendResponse.success) {
      return { success: false, error: backendResponse.message };
    }

    revalidatePath("/transactions");
    revalidatePath("/");
    revalidatePath("/settings");
    revalidatePath("/assets");

    return {
      success: true,
      transactionId: backendResponse.transaction_ids?.[0] || undefined
    };
  } catch (error) {
    console.error("Failed to create transaction:", error);
    return { success: false, error: "Failed to create transaction" };
  }
}

export async function updateTransactionCategory(
  transactionId: string,
  categoryId: string | null
): Promise<{ success: boolean; error?: string }> {
  const userId = await requireAuth();

  if (!userId) {
    return { success: false, error: "Not authenticated" };
  }

  try {
    // Verify the transaction belongs to the user
    const transaction = await db.query.transactions.findFirst({
      where: and(
        eq(transactions.id, transactionId),
        eq(transactions.userId, userId)
      ),
    });

    if (!transaction) {
      return { success: false, error: "Transaction not found" };
    }

    // Verify the category belongs to the user (if provided)
    if (categoryId) {
      const category = await db.query.categories.findFirst({
        where: and(
          eq(categories.id, categoryId),
          eq(categories.userId, userId)
        ),
      });

      if (!category) {
        return { success: false, error: "Category not found" };
      }
    }

    await db
      .update(transactions)
      .set({
        categoryId,
        updatedAt: new Date(),
      })
      .where(eq(transactions.id, transactionId));

    revalidatePath("/transactions");
    return { success: true };
  } catch (error) {
    console.error("Failed to update transaction category:", error);
    return { success: false, error: "Failed to update transaction category" };
  }
}

export async function getUserAccounts() {
  const userId = await requireAuth();

  if (!userId) {
    return [];
  }

  return db.query.accounts.findMany({
    where: and(
      eq(accounts.userId, userId),
      eq(accounts.isActive, true)
    ),
    orderBy: [desc(accounts.createdAt)],
  });
}

// Note: getUserCategories has been consolidated in lib/actions/categories.ts
// Use: import { getUserCategories } from "@/lib/actions/categories"

export interface TransactionWithRelations {
  id: string;
  accountId: string;
  account: {
    id: string;
    name: string;
    institution: string | null;
    accountType: string;
    logo: {
      id: string;
      logoUrl: string | null;
      updatedAt?: Date | null;
    } | null;
  } | null;
  description: string | null;
  merchant: string | null;
  amount: number;
  currency: string | null;
  categoryId: string | null;
  category: {
    id: string;
    name: string;
    color: string | null;
    icon: string | null;
  } | null;
  categorySystemId: string | null;
  categorySystem: {
    id: string;
    name: string;
    color: string | null;
    icon: string | null;
  } | null;
  recurringTransactionId: string | null;
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
  bookedAt: Date;
  pending: boolean | null;
  transactionType: string | null;
  includeInAnalytics: boolean;
}

export interface TransactionsPageResult {
  rows: TransactionWithRelations[];
  totalCount: number;
  filteredTotals: FilteredTransactionTotals | null;
  page: number;
  pageSize: number;
  resolvedFrom?: string;
  resolvedTo?: string;
  effectiveHorizon?: number;
}

export interface FilteredTransactionTotals {
  totalIn: number;
  totalOut: number;
}

function normalizeAccountIds(accountIds: string[]): string[] {
  return Array.from(new Set(accountIds.map((id) => id.trim()).filter(Boolean)));
}

function toNumberOrUndefined(value?: string): number | undefined {
  if (!value) return undefined;
  const parsed = Number.parseFloat(value);
  return Number.isFinite(parsed) ? parsed : undefined;
}

function resolveSortOrder(
  sort: TransactionSortField,
  order: TransactionSortOrder
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

interface TransactionRowWithRelations {
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

function mapTransactionRowsForUi(
  rows: TransactionRowWithRelations[],
  contextLabel: string
): TransactionWithRelations[] {
  return rows.flatMap((tx) => {
    if (!tx.account) {
      console.warn(`[${contextLabel}] Transaction missing account relation`, {
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

async function hydrateTransactionRowsWithResolvedAccountLogos(
  rows: TransactionRowWithRelations[]
): Promise<TransactionRowWithRelations[]> {
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

async function getLatestTransactionDateForScope(
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

interface ResolvedTransactionsWhereClause {
  whereClause: NonNullable<ReturnType<typeof and>>;
  resolvedFrom?: Date;
  resolvedTo?: Date;
  effectiveHorizon?: number;
}

async function buildTransactionsWhereClause(
  userId: string,
  input: TransactionsQueryState
): Promise<ResolvedTransactionsWhereClause> {
  const normalizedAccountIds = normalizeAccountIds(input.accountIds);
  const conditions = [eq(transactions.userId, userId)];

  if (normalizedAccountIds.length > 0) {
    conditions.push(inArray(transactions.accountId, normalizedAccountIds));
  }

  let resolvedFrom: Date | undefined;
  let resolvedTo: Date | undefined;
  let effectiveHorizon: number | undefined;

  if (input.from) {
    resolvedFrom = new Date(`${input.from}T00:00:00.000Z`);
    resolvedTo = input.to
      ? new Date(`${input.to}T23:59:59.999Z`)
      : await getLatestTransactionDateForScope(userId, normalizedAccountIds);
    resolvedTo.setHours(23, 59, 59, 999);
    if (resolvedTo < resolvedFrom) {
      resolvedTo = new Date(resolvedFrom);
      resolvedTo.setHours(23, 59, 59, 999);
    }
  } else if (input.horizon) {
    const latestDate = await getLatestTransactionDateForScope(userId, normalizedAccountIds);
    resolvedTo = new Date(latestDate);
    resolvedTo.setHours(23, 59, 59, 999);
    effectiveHorizon = input.horizon;
    resolvedFrom = new Date(resolvedTo);
    resolvedFrom.setDate(resolvedFrom.getDate() - (effectiveHorizon - 1));
    resolvedFrom.setHours(0, 0, 0, 0);
  }

  if (resolvedFrom) {
    conditions.push(gte(transactions.bookedAt, resolvedFrom));
  }
  if (resolvedTo) {
    conditions.push(lte(transactions.bookedAt, resolvedTo));
  }

  if (input.search) {
    conditions.push(
      or(
        ilike(transactions.description, `%${input.search}%`),
        ilike(transactions.merchant, `%${input.search}%`)
      )!
    );
  }

  const categoryIds = input.category.filter((value) => value !== "uncategorized");
  const includeUncategorized = input.category.includes("uncategorized");
  if (categoryIds.length > 0 || includeUncategorized) {
    const categoryConditions = [];
    if (categoryIds.length > 0) {
      categoryConditions.push(inArray(transactions.categoryId, categoryIds));
      categoryConditions.push(
        and(
          isNull(transactions.categoryId),
          inArray(transactions.categorySystemId, categoryIds)
        )
      );
    }
    if (includeUncategorized) {
      categoryConditions.push(
        and(isNull(transactions.categoryId), isNull(transactions.categorySystemId))
      );
    }
    conditions.push(or(...categoryConditions)!);
  }

  const includesPending = input.status.includes("pending");
  const includesCompleted = input.status.includes("completed");
  if (includesPending !== includesCompleted) {
    if (includesPending) {
      conditions.push(eq(transactions.pending, true));
    } else {
      conditions.push(or(eq(transactions.pending, false), isNull(transactions.pending))!);
    }
  }

  const subscriptionIds = input.subscription.filter((value) => value !== "no_subscription");
  const includesNoSubscription = input.subscription.includes("no_subscription");
  if (subscriptionIds.length > 0 || includesNoSubscription) {
    const subscriptionConditions = [];
    if (subscriptionIds.length > 0) {
      subscriptionConditions.push(inArray(transactions.recurringTransactionId, subscriptionIds));
    }
    if (includesNoSubscription) {
      subscriptionConditions.push(isNull(transactions.recurringTransactionId));
    }
    conditions.push(or(...subscriptionConditions)!);
  }

  const includesAnalytics = input.analytics.includes("included");
  const includesNonAnalytics = input.analytics.includes("excluded");
  if (includesAnalytics !== includesNonAnalytics) {
    conditions.push(eq(transactions.includeInAnalytics, includesAnalytics));
  }

  const minAmount = toNumberOrUndefined(input.minAmount);
  const maxAmount = toNumberOrUndefined(input.maxAmount);
  if (minAmount !== undefined) {
    conditions.push(sql`ABS(${transactions.amount}) >= ${minAmount}`);
  }
  if (maxAmount !== undefined) {
    conditions.push(sql`ABS(${transactions.amount}) <= ${maxAmount}`);
  }

  return {
    whereClause: and(...conditions)!,
    resolvedFrom,
    resolvedTo,
    effectiveHorizon,
  };
}

export async function getTransactionsPage(
  input: TransactionsQueryState
): Promise<TransactionsPageResult> {
  const userId = await requireAuth();

  if (!userId) {
    return {
      rows: [],
      totalCount: 0,
      filteredTotals: null,
      page: input.page,
      pageSize: input.pageSize,
    };
  }

  const {
    whereClause,
    resolvedFrom,
    resolvedTo,
    effectiveHorizon,
  } = await buildTransactionsWhereClause(userId, input);
  const shouldComputeFilteredTotals = hasActiveTransactionFilters(input);

  const [countRows, rows, totalsRows] = await Promise.all([
    db
      .select({
        count: sql<number>`COUNT(*)::int`,
      })
      .from(transactions)
      .where(whereClause),
    db.query.transactions.findMany({
      where: whereClause,
      orderBy: resolveSortOrder(input.sort, input.order),
      limit: input.pageSize,
      offset: (input.page - 1) * input.pageSize,
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
    shouldComputeFilteredTotals
      ? db
          .select({
            totalIn: sql<string>`COALESCE(SUM(
              CASE
                WHEN ${transactions.transactionType} = 'credit' THEN ABS(${transactions.amount})
                WHEN ${transactions.transactionType} IS NULL AND ${transactions.amount} > 0 THEN ${transactions.amount}
                ELSE 0
              END
            ), 0)`,
            totalOut: sql<string>`COALESCE(SUM(
              CASE
                WHEN ${transactions.transactionType} = 'debit' THEN ABS(${transactions.amount})
                WHEN ${transactions.transactionType} IS NULL AND ${transactions.amount} < 0 THEN ABS(${transactions.amount})
                ELSE 0
              END
            ), 0)`,
          })
          .from(transactions)
          .where(whereClause)
      : Promise.resolve([]),
  ]);

  const filteredTotals = shouldComputeFilteredTotals
    ? {
        totalIn: Number.parseFloat(totalsRows[0]?.totalIn ?? "0"),
        totalOut: Number.parseFloat(totalsRows[0]?.totalOut ?? "0"),
      }
    : null;
  const hydratedRows = await hydrateTransactionRowsWithResolvedAccountLogos(rows);

  return {
    rows: mapTransactionRowsForUi(hydratedRows, "getTransactionsPage"),
    totalCount: countRows[0]?.count ?? 0,
    filteredTotals,
    page: input.page,
    pageSize: input.pageSize,
    resolvedFrom: resolvedFrom ? resolvedFrom.toISOString().slice(0, 10) : undefined,
    resolvedTo: resolvedTo ? resolvedTo.toISOString().slice(0, 10) : undefined,
    effectiveHorizon,
  };
}

export async function getTransactions(): Promise<TransactionWithRelations[]> {
  const userId = await requireAuth();

  if (!userId) {
    return [];
  }

  try {
    const result = await db.query.transactions.findMany({
      where: eq(transactions.userId, userId),
      orderBy: [desc(transactions.bookedAt)],
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
    });
    const hydratedRows = await hydrateTransactionRowsWithResolvedAccountLogos(result);
    return mapTransactionRowsForUi(hydratedRows, "getTransactions");
  } catch (error: unknown) {
    const normalizedError =
      error instanceof Error
        ? {
            message: error.message,
            cause: "cause" in error ? (error as Error & { cause?: unknown }).cause : undefined,
            stack: error.stack,
          }
        : { message: String(error), cause: undefined, stack: undefined };
    console.error("[getTransactions] Query failed:", {
      error: normalizedError.message,
      cause: normalizedError.cause,
      stack: normalizedError.stack,
      userId,
    });
    // Return empty array on error to prevent app crash
    return [];
  }
}

export async function getTransactionsForAccount(
  accountId: string
): Promise<TransactionWithRelations[]> {
  const userId = await requireAuth();

  if (!userId) {
    return [];
  }

  // Verify the account belongs to the user
  const account = await db.query.accounts.findFirst({
    where: and(
      eq(accounts.id, accountId),
      eq(accounts.userId, userId)
    ),
  });

  if (!account) {
    return [];
  }

  try {
    const result = await db.query.transactions.findMany({
      where: and(
        eq(transactions.userId, userId),
        eq(transactions.accountId, accountId)
      ),
      orderBy: [desc(transactions.bookedAt)],
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
    });
    const hydratedRows = await hydrateTransactionRowsWithResolvedAccountLogos(result);
    return mapTransactionRowsForUi(hydratedRows, "getTransactionsForAccount");
  } catch (error: unknown) {
    const normalizedError =
      error instanceof Error
        ? {
            message: error.message,
            cause: "cause" in error ? (error as Error & { cause?: unknown }).cause : undefined,
            stack: error.stack,
          }
        : { message: String(error), cause: undefined, stack: undefined };
    console.error("[getTransactionsForAccount] Query failed:", {
      error: normalizedError.message,
      cause: normalizedError.cause,
      stack: normalizedError.stack,
      userId,
      accountId,
    });
    // Return empty array on error to prevent app crash
    return [];
  }
}

export async function bulkUpdateTransactionCategory(
  transactionIds: string[],
  categoryId: string | null
): Promise<{ success: boolean; error?: string; updatedCount?: number }> {
  const userId = await requireAuth();

  if (!userId) {
    return { success: false, error: "Not authenticated" };
  }

  if (transactionIds.length === 0) {
    return { success: false, error: "No transactions selected" };
  }

  try {
    // Verify the category belongs to the user (if provided)
    if (categoryId) {
      const category = await db.query.categories.findFirst({
        where: and(
          eq(categories.id, categoryId),
          eq(categories.userId, userId)
        ),
      });

      if (!category) {
        return { success: false, error: "Category not found" };
      }
    }

    // Update all transactions that belong to the user
    await db
      .update(transactions)
      .set({
        categoryId,
        updatedAt: new Date(),
      })
      .where(
        and(
          inArray(transactions.id, transactionIds),
          eq(transactions.userId, userId)
        )
      );

    revalidatePath("/transactions");
    return { success: true, updatedCount: transactionIds.length };
  } catch (error) {
    console.error("Failed to bulk update transaction categories:", error);
    return { success: false, error: "Failed to update transactions" };
  }
}

export async function updateTransactionIncludeInAnalytics(
  transactionId: string,
  includeInAnalytics: boolean
): Promise<{ success: boolean; error?: string }> {
  const userId = await requireAuth();

  if (!userId) {
    return { success: false, error: "Not authenticated" };
  }

  try {
    // Verify the transaction belongs to the user
    const transaction = await db.query.transactions.findFirst({
      where: and(
        eq(transactions.id, transactionId),
        eq(transactions.userId, userId)
      ),
    });

    if (!transaction) {
      return { success: false, error: "Transaction not found" };
    }

    await db
      .update(transactions)
      .set({
        includeInAnalytics,
        updatedAt: new Date(),
      })
      .where(eq(transactions.id, transactionId));

    revalidatePath("/transactions");
    revalidatePath("/");
    return { success: true };
  } catch (error) {
    console.error("Failed to update transaction include_in_analytics:", error);
    return { success: false, error: "Failed to update transaction" };
  }
}

export async function bulkUpdateTransactionIncludeInAnalytics(
  transactionIds: string[],
  includeInAnalytics: boolean
): Promise<{ success: boolean; error?: string; updatedCount?: number }> {
  const userId = await requireAuth();

  if (!userId) {
    return { success: false, error: "Not authenticated" };
  }

  if (transactionIds.length === 0) {
    return { success: false, error: "No transactions selected" };
  }

  try {
    // Update all transactions that belong to the user
    await db
      .update(transactions)
      .set({
        includeInAnalytics,
        updatedAt: new Date(),
      })
      .where(
        and(
          inArray(transactions.id, transactionIds),
          eq(transactions.userId, userId)
        )
      );

    revalidatePath("/transactions");
    revalidatePath("/");
    return { success: true, updatedCount: transactionIds.length };
  } catch (error) {
    console.error("Failed to bulk update transaction include_in_analytics:", error);
    return { success: false, error: "Failed to update transactions" };
  }
}

/**
 * Deletes a balancing transfer transaction and recalculates balances.
 * This reverts the balance adjustment as if the transfer never existed.
 */
export async function deleteBalancingTransaction(
  transactionId: string
): Promise<{ success: boolean; error?: string }> {
  const userId = await requireAuth();

  if (!userId) {
    return { success: false, error: "Not authenticated" };
  }

  try {
    // Get the transaction with its account and category
    const transaction = await db.query.transactions.findFirst({
      where: and(
        eq(transactions.id, transactionId),
        eq(transactions.userId, userId)
      ),
      with: {
        account: true,
        category: true,
      },
    });

    if (!transaction) {
      return { success: false, error: "Transaction not found" };
    }

    // Verify this is a "Balancing Transfer" category
    if (!transaction.category || transaction.category.name !== "Balancing Transfer") {
      return { success: false, error: "Only balancing transfers can be reverted" };
    }

    const accountId = transaction.accountId;
    const transactionDate = transaction.bookedAt;

    // Get the account's starting balance for recalculation
    const account = transaction.account;
    if (!account) {
      return { success: false, error: "Transaction account not found" };
    }
    const startingBalance = parseFloat(account.startingBalance || "0");

    // Delete the transaction
    await db.delete(transactions).where(eq(transactions.id, transactionId));

    // Recalculate balances from the deleted transaction's date
    // Pass the transactionId to exclude it from balance calculations
    // (the transaction is deleted but we pass it for the recalculation logic to find the next balancing transfer correctly)
    await recalculateAccountBalancesFromDate(
      accountId,
      transactionDate,
      startingBalance,
      transactionId
    );

    // Update the account's functional_balance
    const balanceResult = await db
      .select({
        total: sql<string>`COALESCE(SUM(${transactions.amount}), 0)`,
      })
      .from(transactions)
      .where(eq(transactions.accountId, accountId));

    const transactionSum = parseFloat(balanceResult[0]?.total || "0");
    const newFunctionalBalance = startingBalance + transactionSum;

    await db
      .update(accounts)
      .set({
        functionalBalance: newFunctionalBalance.toFixed(2),
        updatedAt: new Date(),
      })
      .where(eq(accounts.id, accountId));

    revalidatePath("/transactions");
    revalidatePath("/");
    revalidatePath("/settings");
    revalidatePath("/assets");

    return { success: true };
  } catch (error) {
    console.error("Failed to delete balancing transaction:", error);
    return { success: false, error: "Failed to revert balancing transfer" };
  }
}

export interface CreateOrUpdateBalancingTransactionInput {
  accountId: string;
  targetBalance: number;
  adjustmentDate: Date;
  balancingCategoryId: string;
}

/**
 * Creates or updates a balancing transfer for a specific date.
 * If a balancing transfer already exists on that date for the account, it updates it.
 * Otherwise, it creates a new one.
 * In both cases, balances are recalculated.
 */
export async function createOrUpdateBalancingTransaction(
  input: CreateOrUpdateBalancingTransactionInput
): Promise<{ success: boolean; error?: string; transactionId?: string; isUpdate?: boolean }> {
  const userId = await requireAuth();

  if (!userId) {
    return { success: false, error: "Not authenticated" };
  }

  try {
    const { accountId, targetBalance, adjustmentDate, balancingCategoryId } = input;

    // Verify the account belongs to the user
    const account = await db.query.accounts.findFirst({
      where: and(
        eq(accounts.id, accountId),
        eq(accounts.userId, userId)
      ),
    });

    if (!account) {
      return { success: false, error: "Account not found" };
    }

    // Verify the category belongs to the user
    const category = await db.query.categories.findFirst({
      where: and(
        eq(categories.id, balancingCategoryId),
        eq(categories.userId, userId)
      ),
    });

    if (!category || category.name !== "Balancing Transfer") {
      return { success: false, error: "Invalid balancing transfer category" };
    }

    // Normalize date to start and end of day for searching
    const startOfDay = new Date(adjustmentDate);
    startOfDay.setHours(0, 0, 0, 0);
    const endOfDay = new Date(adjustmentDate);
    endOfDay.setHours(23, 59, 59, 999);

    // Check if there's already a balancing transfer on this date for this account
    const existingBalancingTransfer = await db.query.transactions.findFirst({
      where: and(
        eq(transactions.accountId, accountId),
        eq(transactions.categoryId, balancingCategoryId),
        gte(transactions.bookedAt, startOfDay),
        lte(transactions.bookedAt, endOfDay)
      ),
    });

    const startingBalance = parseFloat(account.startingBalance || "0");

    // Calculate what the balance would be on this date WITHOUT any balancing transfer
    // We need to exclude the existing balancing transfer (if any) from the calculation
    const balanceConditions = [
      eq(transactions.accountId, accountId),
      lte(transactions.bookedAt, endOfDay)
    ];

    if (existingBalancingTransfer) {
      balanceConditions.push(ne(transactions.id, existingBalancingTransfer.id));
    }

    const balanceWithoutAdjustment = await db
      .select({
        total: sql<string>`COALESCE(SUM(${transactions.amount}), 0)`,
      })
      .from(transactions)
      .where(and(...balanceConditions));

    const transactionSumWithoutAdjustment = parseFloat(balanceWithoutAdjustment[0]?.total || "0");
    const currentBalanceWithoutAdjustment = startingBalance + transactionSumWithoutAdjustment;

    // Calculate the required adjustment amount
    const difference = targetBalance - currentBalanceWithoutAdjustment;

    if (Math.abs(difference) < 0.01) {
      // No adjustment needed - if there's an existing balancing transfer, delete it
      if (existingBalancingTransfer) {
        await db.delete(transactions).where(eq(transactions.id, existingBalancingTransfer.id));

        // Recalculate balances
        await recalculateAccountBalancesFromDate(
          accountId,
          adjustmentDate,
          startingBalance,
          existingBalancingTransfer.id
        );

        // Update functional balance
        const newBalanceResult = await db
          .select({
            total: sql<string>`COALESCE(SUM(${transactions.amount}), 0)`,
          })
          .from(transactions)
          .where(eq(transactions.accountId, accountId));

        const newFunctionalBalance = startingBalance + parseFloat(newBalanceResult[0]?.total || "0");

        await db
          .update(accounts)
          .set({
            functionalBalance: newFunctionalBalance.toFixed(2),
            updatedAt: new Date(),
          })
          .where(eq(accounts.id, accountId));

        revalidatePath("/transactions");
        revalidatePath("/");
        revalidatePath("/settings");
        revalidatePath("/assets");

        return { success: true, isUpdate: true };
      }
      return { success: true };
    }

    const transactionType = difference > 0 ? "credit" : "debit";
    // Keep the sign! Debits should be negative, credits positive.
    // The balance formula is: balance = starting_balance + SUM(transactions.amount)
    const amount = difference;

    let transactionId: string;
    let isUpdate = false;

    if (existingBalancingTransfer) {
      // Update existing transaction
      await db
        .update(transactions)
        .set({
          amount: amount.toString(),
          transactionType,
          updatedAt: new Date(),
        })
        .where(eq(transactions.id, existingBalancingTransfer.id));

      transactionId = existingBalancingTransfer.id;
      isUpdate = true;
    } else {
      // Create new transaction
      const [result] = await db.insert(transactions).values({
        userId,
        accountId,
        amount: amount.toString(),
        description: "Balance adjustment",
        categoryId: balancingCategoryId,
        bookedAt: adjustmentDate,
        transactionType,
        currency: account.currency || "EUR",
      }).returning({ id: transactions.id });

      transactionId = result.id;
    }

    // Recalculate balances from the adjustment date
    await recalculateAccountBalancesFromDate(
      accountId,
      adjustmentDate,
      startingBalance
    );

    // Update the account's functional_balance
    const balanceResult = await db
      .select({
        total: sql<string>`COALESCE(SUM(${transactions.amount}), 0)`,
      })
      .from(transactions)
      .where(eq(transactions.accountId, accountId));

    const transactionSum = parseFloat(balanceResult[0]?.total || "0");
    const newFunctionalBalance = startingBalance + transactionSum;

    await db
      .update(accounts)
      .set({
        functionalBalance: newFunctionalBalance.toFixed(2),
        updatedAt: new Date(),
      })
      .where(eq(accounts.id, accountId));

    revalidatePath("/transactions");
    revalidatePath("/");
    revalidatePath("/settings");
    revalidatePath("/assets");

    return { success: true, transactionId, isUpdate };
  } catch (error) {
    console.error("Failed to create/update balancing transaction:", error);
    return { success: false, error: "Failed to update balance" };
  }
}
