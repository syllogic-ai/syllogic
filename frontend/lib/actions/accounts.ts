"use server";

import { revalidatePath } from "next/cache";
import { eq, and, lte, desc, sql } from "drizzle-orm";
import { db } from "@/lib/db";
import { accounts, accountBalances, transactions, type NewAccount } from "@/lib/db/schema";
import { requireAuth } from "@/lib/auth-helpers";

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
    await db
      .update(accounts)
      .set({
        isActive: false,
        updatedAt: new Date(),
      })
      .where(eq(accounts.id, accountId));

    revalidatePath("/settings");
    return { success: true };
  } catch (error) {
    console.error("Failed to delete account:", error);
    return { success: false, error: "Failed to delete account" };
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
      const backendUrl = process.env.BACKEND_URL || "http://localhost:8000";
      await fetch(`${backendUrl}/api/accounts/${accountId}/recalculate-timeseries`, {
        method: "POST",
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
