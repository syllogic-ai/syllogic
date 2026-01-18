"use server";

import { revalidatePath } from "next/cache";
import { eq, and } from "drizzle-orm";
import { db } from "@/lib/db";
import { accounts, type NewAccount } from "@/lib/db/schema";
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
        functionalBalance: input.startingBalance?.toString(), // For manual accounts, update both
        updatedAt: new Date(),
      })
      .where(eq(accounts.id, accountId));

    revalidatePath("/settings");
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
