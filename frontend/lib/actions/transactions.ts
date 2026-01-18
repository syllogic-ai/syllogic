"use server";

import { revalidatePath } from "next/cache";
import { eq, and, desc, inArray } from "drizzle-orm";
import { db } from "@/lib/db";
import { transactions, accounts, categories, type NewTransaction } from "@/lib/db/schema";
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

export async function createTransaction(
  input: CreateTransactionInput
): Promise<{ success: boolean; error?: string; transactionId?: string }> {
  const userId = await requireAuth();

  if (!userId) {
    return { success: false, error: "Not authenticated" };
  }

  try {
    // Verify the account belongs to the user
    const account = await db.query.accounts.findFirst({
      where: and(
        eq(accounts.id, input.accountId),
        eq(accounts.userId, userId)
      ),
    });

    if (!account) {
      return { success: false, error: "Account not found" };
    }

    // Verify the category belongs to the user (if provided)
    if (input.categoryId) {
      const category = await db.query.categories.findFirst({
        where: and(
          eq(categories.id, input.categoryId),
          eq(categories.userId, userId)
        ),
      });

      if (!category) {
        return { success: false, error: "Category not found" };
      }
    }

    // Create the transaction
    const newTransaction: NewTransaction = {
      userId,
      accountId: input.accountId,
      amount: input.amount.toString(),
      description: input.description,
      categoryId: input.categoryId || null,
      bookedAt: input.bookedAt,
      transactionType: input.transactionType,
      merchant: input.merchant,
      currency: account.currency || "EUR",
    };

    const [result] = await db.insert(transactions).values(newTransaction).returning({ id: transactions.id });

    revalidatePath("/transactions");
    revalidatePath("/");
    return { success: true, transactionId: result.id };
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
  bookedAt: Date;
  pending: boolean | null;
  transactionType: string | null;
}

export async function getTransactions(): Promise<TransactionWithRelations[]> {
  const userId = await requireAuth();

  if (!userId) {
    return [];
  }

  const result = await db.query.transactions.findMany({
    where: eq(transactions.userId, userId),
    orderBy: [desc(transactions.bookedAt)],
    with: {
      account: true,
      category: true,
      categorySystem: true,
    },
  });

  return result.map((tx) => ({
    id: tx.id,
    accountId: tx.accountId,
    account: {
      id: tx.account.id,
      name: tx.account.name,
      institution: tx.account.institution,
      accountType: tx.account.accountType,
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
    bookedAt: tx.bookedAt,
    pending: tx.pending,
    transactionType: tx.transactionType,
  }));
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
