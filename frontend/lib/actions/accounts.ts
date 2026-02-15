"use server";

import { revalidatePath } from "next/cache";
import { eq, and, lte, gte, lt, desc, sql } from "drizzle-orm";
import { db } from "@/lib/db";
import { accounts, accountBalances, transactions, type NewAccount } from "@/lib/db/schema";
import { requireAuth } from "@/lib/auth-helpers";
import { getBackendBaseUrl } from "@/lib/backend-url";
import { createInternalAuthHeaders } from "@/lib/internal-auth";

export interface CreateAccountInput {
  name: string;
  accountType: string;
  institution?: string;
  currency: string;
  startingBalance?: number;
}

export async function createAccount(
  input: CreateAccountInput
): Promise<{ success: boolean; error?: string; accountId?: string }> {
  const userId = await requireAuth();

  if (!userId) {
    return { success: false, error: "Not authenticated" };
  }

  try {
    const balanceValue = input.startingBalance?.toString() || "0";
    const newAccount: NewAccount = {
      userId,
      name: input.name,
      accountType: input.accountType,
      institution: input.institution || null,
      currency: input.currency,
      startingBalance: balanceValue,
      functionalBalance: balanceValue, // For manual accounts, functional = starting
      provider: "manual",
      isActive: true,
    };

    const [result] = await db.insert(accounts).values(newAccount).returning({ id: accounts.id });

    revalidatePath("/settings");
    revalidatePath("/transactions/import");
    return { success: true, accountId: result.id };
  } catch (error) {
    console.error("Failed to create account:", error);
    return { success: false, error: "Failed to create account" };
  }
}

export async function updateAccount(
  accountId: string,
  input: Partial<CreateAccountInput>
): Promise<{ success: boolean; error?: string }> {
  const userId = await requireAuth();

  if (!userId) {
    return { success: false, error: "Not authenticated" };
  }

  try {
    const account = await db.query.accounts.findFirst({
      where: and(eq(accounts.id, accountId), eq(accounts.userId, userId)),
    });

    if (!account) {
      return { success: false, error: "Account not found" };
    }

    await db
      .update(accounts)
      .set({
        name: input.name,
        accountType: input.accountType,
        institution: input.institution,
        currency: input.currency,
        startingBalance: input.startingBalance?.toString(),
        updatedAt: new Date(),
      })
      .where(eq(accounts.id, accountId));

    revalidatePath("/settings");
    revalidatePath("/");
    return { success: true };
  } catch (error) {
    console.error("Failed to update account:", error);
    return { success: false, error: "Failed to update account" };
  }
}

export async function deleteAccount(
  accountId: string
): Promise<{ success: boolean; error?: string }> {
  const userId = await requireAuth();

  if (!userId) {
    return { success: false, error: "Not authenticated" };
  }

  try {
    const account = await db.query.accounts.findFirst({
      where: and(eq(accounts.id, accountId), eq(accounts.userId, userId)),
    });

    if (!account) {
      return { success: false, error: "Account not found" };
    }

    // Soft delete by setting isActive to false
    // Note: Transactions and balances remain associated with the deactivated account
    // Use hardDeleteAccount for complete cleanup
    await db
      .update(accounts)
      .set({
        isActive: false,
        updatedAt: new Date(),
      })
      .where(eq(accounts.id, accountId));

    revalidatePath("/settings");
    revalidatePath("/");
    return { success: true };
  } catch (error) {
    console.error("Failed to delete account:", error);
    return { success: false, error: "Failed to delete account" };
  }
}

/**
 * Permanently delete an account and all associated data.
 * This includes all transactions and balance history records.
 * Use with caution - this action cannot be undone.
 */
export async function hardDeleteAccount(
  accountId: string
): Promise<{ success: boolean; error?: string; deletedTransactions?: number; deletedBalances?: number }> {
  const userId = await requireAuth();

  if (!userId) {
    return { success: false, error: "Not authenticated" };
  }

  try {
    const account = await db.query.accounts.findFirst({
      where: and(eq(accounts.id, accountId), eq(accounts.userId, userId)),
    });

    if (!account) {
      return { success: false, error: "Account not found" };
    }

    // Delete associated balance records first
    const deletedBalances = await db
      .delete(accountBalances)
      .where(eq(accountBalances.accountId, accountId))
      .returning({ id: accountBalances.id });

    // Delete associated transactions
    const deletedTransactions = await db
      .delete(transactions)
      .where(
        and(
          eq(transactions.accountId, accountId),
          eq(transactions.userId, userId)
        )
      )
      .returning({ id: transactions.id });

    // Delete the account
    await db.delete(accounts).where(eq(accounts.id, accountId));

    revalidatePath("/settings");
    revalidatePath("/");
    revalidatePath("/transactions");
    revalidatePath("/assets");

    return {
      success: true,
      deletedTransactions: deletedTransactions.length,
      deletedBalances: deletedBalances.length,
    };
  } catch (error) {
    console.error("Failed to hard delete account:", error);
    return { success: false, error: "Failed to delete account and associated data" };
  }
}

export async function getAccounts() {
  const userId = await requireAuth();

  if (!userId) {
    return [];
  }

  return db.query.accounts.findMany({
    where: and(eq(accounts.userId, userId), eq(accounts.isActive, true)),
    orderBy: (accounts, { asc }) => [asc(accounts.name)],
  });
}

export async function recalculateStartingBalance(
  accountId: string,
  knownCurrentBalance: number
): Promise<{ success: boolean; error?: string; newStartingBalance?: number }> {
  const userId = await requireAuth();

  if (!userId) {
    return { success: false, error: "Not authenticated" };
  }

  try {
    // Verify account belongs to user
    const account = await db.query.accounts.findFirst({
      where: and(eq(accounts.id, accountId), eq(accounts.userId, userId)),
    });

    if (!account) {
      return { success: false, error: "Account not found" };
    }

    // Get sum of all transactions for this account
    const result = await db
      .select({
        total: sql<string>`COALESCE(SUM(${transactions.amount}), 0)`,
      })
      .from(transactions)
      .where(eq(transactions.accountId, accountId));

    const transactionSum = parseFloat(result[0]?.total || "0");

    // Calculate new starting balance:
    // known_current_balance = starting_balance + transaction_sum
    // Therefore: starting_balance = known_current_balance - transaction_sum
    const newStartingBalance = knownCurrentBalance - transactionSum;

    // Update account's starting_balance and functional_balance
    await db
      .update(accounts)
      .set({
        startingBalance: newStartingBalance.toFixed(2),
        functionalBalance: knownCurrentBalance.toFixed(2),
        updatedAt: new Date(),
      })
      .where(eq(accounts.id, accountId));

    // Trigger backend timeseries recalculation
    try {
      const backendUrl = getBackendBaseUrl();
      const pathWithQuery = `/api/accounts/${accountId}/recalculate-timeseries`;
      await fetch(`${backendUrl}${pathWithQuery}`, {
        method: "POST",
        headers: createInternalAuthHeaders({
          method: "POST",
          pathWithQuery,
          userId,
        }),
      });
    } catch (backendError) {
      console.warn("Failed to trigger backend timeseries recalculation:", backendError);
      // Don't fail the operation if backend call fails
    }

    revalidatePath("/settings");
    revalidatePath("/transactions");
    revalidatePath("/");
    revalidatePath("/assets");

    return { success: true, newStartingBalance };
  } catch (error) {
    console.error("Failed to recalculate starting balance:", error);
    return { success: false, error: "Failed to recalculate starting balance" };
  }
}

export async function getAccountById(accountId: string) {
  const userId = await requireAuth();

  if (!userId) {
    return null;
  }

  const account = await db.query.accounts.findFirst({
    where: and(
      eq(accounts.id, accountId),
      eq(accounts.userId, userId),
      eq(accounts.isActive, true)
    ),
  });

  return account ?? null;
}

export interface BalanceHistoryPoint {
  date: string;
  balance: number;
}

export async function getAccountBalanceHistory(
  accountId: string,
  days: number | null = 90
): Promise<BalanceHistoryPoint[]> {
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

  let startDate: Date | null = null;
  if (typeof days === "number") {
    startDate = new Date();
    startDate.setDate(startDate.getDate() - days);
    startDate.setHours(0, 0, 0, 0);
  } else {
    const earliestTx = await db
      .select({
        minBookedAt: sql<Date | null>`MIN(${transactions.bookedAt})`,
      })
      .from(transactions)
      .where(eq(transactions.accountId, accountId));

    if (earliestTx[0]?.minBookedAt) {
      startDate = new Date(earliestTx[0].minBookedAt);
      startDate.setHours(0, 0, 0, 0);
    }
  }

  // Try to get balance history from accountBalances table
  const balanceHistory = await db.query.accountBalances.findMany({
    where: startDate
      ? and(
          eq(accountBalances.accountId, accountId),
          gte(accountBalances.date, startDate)
        )
      : eq(accountBalances.accountId, accountId),
    orderBy: [desc(accountBalances.date)],
  });

  if (balanceHistory.length > 0) {
    // Reverse to get chronological order (oldest first)
    return balanceHistory.reverse().map((b) => ({
      date: b.date.toISOString().split("T")[0],
      balance: parseFloat(b.balanceInAccountCurrency),
    }));
  }

  // Fallback: Calculate running balance from transactions
  const startingBalance = parseFloat(account.startingBalance || "0");
  const effectiveStartDate = startDate || new Date();
  effectiveStartDate.setHours(0, 0, 0, 0);
  const txResults = await db
    .select({
      date: sql<string>`DATE(${transactions.bookedAt})`,
      dailySum: sql<string>`SUM(${transactions.amount})`,
    })
    .from(transactions)
    .where(
      and(
        eq(transactions.accountId, accountId),
        gte(transactions.bookedAt, effectiveStartDate)
      )
    )
    .groupBy(sql`DATE(${transactions.bookedAt})`)
    .orderBy(sql`DATE(${transactions.bookedAt})`);

  // Build running balance for each day
  const result: BalanceHistoryPoint[] = [];
  let runningBalance = startingBalance;

  // Get sum of all transactions before start date
  const priorSum = await db
    .select({
      total: sql<string>`COALESCE(SUM(${transactions.amount}), 0)`,
    })
    .from(transactions)
    .where(
      and(
        eq(transactions.accountId, accountId),
        lt(transactions.bookedAt, effectiveStartDate)
      )
    );

  runningBalance += parseFloat(priorSum[0]?.total || "0");

  // Create a map of date -> daily sum
  const dailySums = new Map<string, number>();
  for (const tx of txResults) {
    dailySums.set(tx.date, parseFloat(tx.dailySum));
  }

  // Fill in all dates from startDate to today
  const currentDate = new Date(effectiveStartDate);
  const today = new Date();
  today.setHours(23, 59, 59, 999);

  while (currentDate <= today) {
    const dateStr = currentDate.toISOString().split("T")[0];
    const dailyChange = dailySums.get(dateStr) || 0;
    runningBalance += dailyChange;
    result.push({
      date: dateStr,
      balance: runningBalance,
    });
    currentDate.setDate(currentDate.getDate() + 1);
  }

  return result;
}

export async function getAccountBalanceOnDate(
  accountId: string,
  date: Date
): Promise<{ balance: number; found: boolean }> {
  const userId = await requireAuth();

  if (!userId) {
    return { balance: 0, found: false };
  }

  // Verify the account belongs to the user
  const account = await db.query.accounts.findFirst({
    where: and(eq(accounts.id, accountId), eq(accounts.userId, userId)),
  });

  if (!account) {
    return { balance: 0, found: false };
  }

  // First try to get balance from account_balances table
  const balanceRecord = await db.query.accountBalances.findFirst({
    where: and(
      eq(accountBalances.accountId, accountId),
      lte(accountBalances.date, date)
    ),
    orderBy: [desc(accountBalances.date)],
  });

  if (balanceRecord) {
    return {
      balance: parseFloat(balanceRecord.balanceInAccountCurrency),
      found: true,
    };
  }

  // No pre-computed balance found, calculate from transactions
  // Sum all transactions up to and including the selected date
  const startingBalance = parseFloat(account.startingBalance || "0");

  // Set end of day for the date comparison to include all transactions on that day
  const endOfDay = new Date(date);
  endOfDay.setHours(23, 59, 59, 999);

  const result = await db
    .select({
      total: sql<string>`COALESCE(SUM(${transactions.amount}), 0)`,
    })
    .from(transactions)
    .where(
      and(
        eq(transactions.accountId, accountId),
        lte(transactions.bookedAt, endOfDay)
      )
    );

  const transactionSum = parseFloat(result[0]?.total || "0");

  return {
    balance: startingBalance + transactionSum,
    found: true,
  };
}

export async function recalculateAccountTimeseries(
  accountId: string
): Promise<{ success: boolean; error?: string; message?: string; daysProcessed?: number; recordsStored?: number }> {
  const userId = await requireAuth();

  if (!userId) {
    return { success: false, error: "Not authenticated" };
  }

  try {
    // Verify account belongs to user
    const account = await db.query.accounts.findFirst({
      where: and(eq(accounts.id, accountId), eq(accounts.userId, userId)),
    });

    if (!account) {
      return { success: false, error: "Account not found" };
    }

    // Call backend to recalculate timeseries
    const backendUrl = getBackendBaseUrl();
    const pathWithQuery = `/api/accounts/${accountId}/recalculate-timeseries`;
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
    });

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({ detail: "Unknown error" }));
      return { success: false, error: errorData.detail || "Failed to recalculate timeseries" };
    }

    const data = await response.json();

    // Recalculate functional_balance on the account as well
    const txResult = await db
      .select({
        total: sql<string>`COALESCE(SUM(${transactions.amount}), 0)`,
      })
      .from(transactions)
      .where(eq(transactions.accountId, accountId));

    const transactionSum = parseFloat(txResult[0]?.total || "0");
    const startingBalance = parseFloat(account.startingBalance || "0");
    const newFunctionalBalance = startingBalance + transactionSum;

    await db
      .update(accounts)
      .set({
        functionalBalance: newFunctionalBalance.toFixed(2),
        updatedAt: new Date(),
      })
      .where(eq(accounts.id, accountId));

    revalidatePath("/settings");
    revalidatePath("/");
    revalidatePath("/transactions");
    revalidatePath("/assets");

    return {
      success: true,
      message: data.message || "Balance recalculated successfully",
      daysProcessed: data.days_processed,
      recordsStored: data.records_stored,
    };
  } catch (error) {
    console.error("Failed to recalculate timeseries:", error);
    return { success: false, error: "Failed to recalculate timeseries" };
  }
}
