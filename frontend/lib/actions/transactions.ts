"use server";

import { revalidatePath } from "next/cache";
import { eq, and, desc, inArray, sql, gte, lte, gt, asc, ne } from "drizzle-orm";
import { db } from "@/lib/db";
import { transactions, accounts, categories, accountBalances, type NewTransaction } from "@/lib/db/schema";
import { requireAuth } from "@/lib/auth-helpers";

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
    const backendUrl = process.env.BACKEND_URL || "http://localhost:8000";

    const response = await fetch(`${backendUrl}/api/transactions/import`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
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
        user_id: userId,
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
  };
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
        account: true,
        category: true,
        categorySystem: true,
        recurringTransaction: true,
        transactionLink: true,
      },
    });

    return result.map((tx) => ({
      id: tx.id,
      accountId: tx.accountId,
      account: tx.account
        ? {
            id: tx.account.id,
            name: tx.account.name,
            institution: tx.account.institution,
            accountType: tx.account.accountType,
          }
        : null,
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
  }));
  } catch (error: any) {
    console.error("[getTransactions] Query failed:", {
      error: error?.message || String(error),
      cause: error?.cause,
      stack: error?.stack,
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
        account: true,
        category: true,
        categorySystem: true,
        recurringTransaction: true,
        transactionLink: true,
      },
    });

    return result.map((tx) => ({
      id: tx.id,
      accountId: tx.accountId,
      account: tx.account
        ? {
            id: tx.account.id,
            name: tx.account.name,
            institution: tx.account.institution,
            accountType: tx.account.accountType,
          }
        : null,
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
  }));
  } catch (error: any) {
    console.error("[getTransactionsForAccount] Query failed:", {
      error: error?.message || String(error),
      cause: error?.cause,
      stack: error?.stack,
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
