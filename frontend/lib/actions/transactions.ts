"use server";

import { headers } from "next/headers";
import { revalidatePath } from "next/cache";
import { eq, and, desc } from "drizzle-orm";
import { db } from "@/lib/db";
import { transactions, accounts, categories, type NewTransaction } from "@/lib/db/schema";
import { auth } from "@/lib/auth";

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
  const session = await auth.api.getSession({
    headers: await headers(),
  });

  if (!session?.user?.id) {
    return { success: false, error: "Not authenticated" };
  }

  try {
    // Verify the account belongs to the user
    const account = await db.query.accounts.findFirst({
      where: and(
        eq(accounts.id, input.accountId),
        eq(accounts.userId, session.user.id)
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
          eq(categories.userId, session.user.id)
        ),
      });

      if (!category) {
        return { success: false, error: "Category not found" };
      }
    }

    // Create the transaction
    const newTransaction: NewTransaction = {
      userId: session.user.id,
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

    // Update account balance
    const balanceChange = input.transactionType === "credit" ? input.amount : -input.amount;
    const newBalance = parseFloat(account.balanceCurrent || "0") + balanceChange;

    await db
      .update(accounts)
      .set({
        balanceCurrent: newBalance.toString(),
        updatedAt: new Date(),
      })
      .where(eq(accounts.id, input.accountId));

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
  const session = await auth.api.getSession({
    headers: await headers(),
  });

  if (!session?.user?.id) {
    return { success: false, error: "Not authenticated" };
  }

  try {
    // Verify the transaction belongs to the user
    const transaction = await db.query.transactions.findFirst({
      where: and(
        eq(transactions.id, transactionId),
        eq(transactions.userId, session.user.id)
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
          eq(categories.userId, session.user.id)
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
  const session = await auth.api.getSession({
    headers: await headers(),
  });

  if (!session?.user?.id) {
    return [];
  }

  return db.query.accounts.findMany({
    where: and(
      eq(accounts.userId, session.user.id),
      eq(accounts.isActive, true)
    ),
    orderBy: [desc(accounts.createdAt)],
  });
}

export async function getUserCategories() {
  const session = await auth.api.getSession({
    headers: await headers(),
  });

  if (!session?.user?.id) {
    return [];
  }

  return db.query.categories.findMany({
    where: eq(categories.userId, session.user.id),
    orderBy: (categories, { asc }) => [asc(categories.name)],
  });
}

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
  const session = await auth.api.getSession({
    headers: await headers(),
  });

  if (!session?.user?.id) {
    return [];
  }

  const result = await db.query.transactions.findMany({
    where: eq(transactions.userId, session.user.id),
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
