"use server";

import { revalidatePath, revalidateTag } from "next/cache";
import { eq, and, lte, gte, lt, desc, sql } from "drizzle-orm";
import { db } from "@/lib/db";
import { accounts, accountBalances, transactions, recurringTransactions, subscriptionSuggestions, type NewAccount } from "@/lib/db/schema";
import { requireAuth, getAuthenticatedSession } from "@/lib/auth-helpers";
import { isDemoRestrictedUserEmail, DEMO_RESTRICTED_ACTION_ERROR } from "@/lib/demo-access";
import { getBackendBaseUrl } from "@/lib/backend-url";
import { createInternalAuthHeaders } from "@/lib/internal-auth";
import { resolveMissingAccountLogo } from "@/lib/actions/account-logos";
import { getCachedFullUserAccounts, CACHE_TAGS } from "@/lib/data/cached";

export interface CreateAccountInput {
  name: string;
  accountType: string;
  institution?: string;
  currency: string;
  startingBalance?: number;
}

export interface UpdateAccountInput extends Partial<CreateAccountInput> {
  logoId?: string | null;
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
    revalidateTag(CACHE_TAGS.accounts(userId), "default");
    return { success: true, accountId: result.id };
  } catch (error) {
    console.error("Failed to create account:", error);
    return { success: false, error: "Failed to create account" };
  }
}

export async function updateAccount(
  accountId: string,
  input: UpdateAccountInput
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

    const updateData: Partial<NewAccount> = {
      updatedAt: new Date(),
    };

    if ("name" in input && input.name !== undefined) {
      updateData.name = input.name;
    }
    if ("accountType" in input && input.accountType !== undefined) {
      updateData.accountType = input.accountType;
    }
    if ("institution" in input) {
      updateData.institution = input.institution ?? null;
    }
    if ("currency" in input && input.currency !== undefined) {
      updateData.currency = input.currency;
    }
    if ("startingBalance" in input && input.startingBalance !== undefined) {
      updateData.startingBalance = input.startingBalance.toString();
    }
    if ("logoId" in input) {
      updateData.logoId = input.logoId ?? null;
    }

    await db.update(accounts).set(updateData).where(eq(accounts.id, accountId));

    revalidatePath("/assets");
    revalidatePath("/accounts");
    revalidatePath(`/accounts/${accountId}`);
    revalidatePath("/transactions");
    revalidatePath("/settings");
    revalidatePath("/");
    revalidateTag(CACHE_TAGS.accounts(userId), "default");
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
    revalidateTag(CACHE_TAGS.accounts(userId), "default");
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

    // Delete subscriptions and suggestions linked to this account.
    // recurringTransactions has ON DELETE SET NULL on account_id, so we must
    // delete them explicitly; deleting them first nulls out
    // transactions.recurring_transaction_id via the DB cascade.
    await db
      .delete(recurringTransactions)
      .where(
        and(
          eq(recurringTransactions.accountId, accountId),
          eq(recurringTransactions.userId, userId)
        )
      );

    await db
      .delete(subscriptionSuggestions)
      .where(
        and(
          eq(subscriptionSuggestions.accountId, accountId),
          eq(subscriptionSuggestions.userId, userId)
        )
      );

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
    revalidateTag(CACHE_TAGS.accounts(userId), "default");

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
  return getCachedFullUserAccounts();
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
    revalidateTag(CACHE_TAGS.accounts(userId), "default");

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
    with: {
      logo: {
        columns: {
          id: true,
          logoUrl: true,
          updatedAt: true,
        },
      },
    },
  });

  if (!account) {
    return null;
  }

  return resolveMissingAccountLogo(account);
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

export type CreatePocketAccountInput = {
  name: string;
  accountType?: string;
  currency?: string;
  startingBalance?: number;
  iban: string;
};

export async function createPocketAccount(
  input: CreatePocketAccountInput,
): Promise<{ success: boolean; error?: string; accountId?: string; backfilledCount?: number }> {
  const session = await getAuthenticatedSession();
  const userId = session?.user?.id;
  if (!userId) return { success: false, error: "Not authenticated" };
  if (isDemoRestrictedUserEmail(session.user.email)) {
    return { success: false, error: DEMO_RESTRICTED_ACTION_ERROR };
  }

  try {
    const path = "/api/accounts/pocket";
    const url = `${getBackendBaseUrl().replace(/\/+$/, "")}${path}`;
    const headers = createInternalAuthHeaders({ method: "POST", pathWithQuery: path, userId });
    const resp = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json", ...headers },
      body: JSON.stringify({
        name: input.name,
        account_type: input.accountType ?? "savings",
        currency: input.currency ?? "EUR",
        starting_balance: String(input.startingBalance ?? 0),
        iban: input.iban,
      }),
    });
    if (!resp.ok) {
      const data = await resp.json().catch(() => ({ detail: "Failed to create pocket account" }));
      const detail =
        typeof data.detail === "string"
          ? data.detail
          : Array.isArray(data.detail) && data.detail[0]?.msg
            ? data.detail[0].msg
            : "Failed to create pocket account";
      return { success: false, error: detail };
    }
    const data = await resp.json();
    revalidatePath("/settings");
    revalidatePath("/assets");
    revalidatePath("/transactions/import");
    return { success: true, accountId: data.account_id, backfilledCount: data.backfilled_count };
  } catch {
    return { success: false, error: "Failed to create pocket account" };
  }
}

export async function unlinkInternalTransfer(
  transferId: string,
): Promise<{ success: boolean; error?: string }> {
  const session = await getAuthenticatedSession();
  const userId = session?.user?.id;
  if (!userId) return { success: false, error: "Not authenticated" };
  if (isDemoRestrictedUserEmail(session.user.email)) {
    return { success: false, error: DEMO_RESTRICTED_ACTION_ERROR };
  }

  try {
    // URL-encode transferId so a malformed id (e.g. one with a slash) can't
    // produce a mismatch between the signed pathWithQuery and the actual
    // request path. UUIDs don't need it in practice, but be defensive.
    const path = `/api/accounts/internal-transfers/${encodeURIComponent(transferId)}`;
    const url = `${getBackendBaseUrl().replace(/\/+$/, "")}${path}`;
    const headers = createInternalAuthHeaders({ method: "DELETE", pathWithQuery: path, userId });
    const resp = await fetch(url, { method: "DELETE", headers });
    if (!resp.ok) {
      const data = await resp
        .json()
        .catch(() => ({ detail: "Failed to unlink internal transfer" }));
      return {
        success: false,
        error:
          typeof data.detail === "string"
            ? data.detail
            : "Failed to unlink internal transfer",
      };
    }
    revalidatePath("/transactions");
    revalidatePath("/assets");
    return { success: true };
  } catch {
    return { success: false, error: "Failed to unlink internal transfer" };
  }
}
