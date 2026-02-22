"use server";

import { revalidatePath } from "next/cache";
import { eq, and, desc, inArray } from "drizzle-orm";
import { db } from "@/lib/db";
import {
  subscriptionSuggestions,
  recurringTransactions,
  transactions,
  type SubscriptionSuggestion,
} from "@/lib/db/schema";
import { requireAuth } from "@/lib/auth-helpers";

// ============================================================================
// Types
// ============================================================================

export interface SubscriptionSuggestionWithMeta extends SubscriptionSuggestion {
  matchCount: number;
  accountName?: string | null;
  suggestedCategoryName?: string | null;
}

// ============================================================================
// Read Operations
// ============================================================================

/**
 * Get all pending suggestions for the current user
 */
export async function getPendingSuggestions(): Promise<SubscriptionSuggestionWithMeta[]> {
  const userId = await requireAuth();

  if (!userId) {
    return [];
  }

  try {
    const suggestions = await db.query.subscriptionSuggestions.findMany({
      where: and(
        eq(subscriptionSuggestions.userId, userId),
        eq(subscriptionSuggestions.status, "pending")
      ),
      with: {
        account: {
          columns: {
            name: true,
          },
        },
        suggestedCategory: {
          columns: {
            name: true,
          },
        },
      },
      orderBy: [desc(subscriptionSuggestions.confidence)],
    });

    // Add match count from parsed transaction IDs
    return suggestions.map((suggestion) => {
      let matchCount = 0;
      try {
        const ids = JSON.parse(suggestion.matchedTransactionIds);
        matchCount = Array.isArray(ids) ? ids.length : 0;
      } catch {
        matchCount = 0;
      }
      return {
        ...suggestion,
        matchCount,
        accountName: suggestion.account?.name ?? null,
        suggestedCategoryName: suggestion.suggestedCategory?.name ?? null,
      };
    });
  } catch (error) {
    console.error("Failed to get pending suggestions:", error);
    return [];
  }
}

/**
 * Get count of pending suggestions for badge display
 */
export async function getPendingSuggestionCount(): Promise<number> {
  const userId = await requireAuth();

  if (!userId) {
    return 0;
  }

  try {
    const suggestions = await db.query.subscriptionSuggestions.findMany({
      where: and(
        eq(subscriptionSuggestions.userId, userId),
        eq(subscriptionSuggestions.status, "pending")
      ),
      columns: { id: true },
    });

    return suggestions.length;
  } catch (error) {
    console.error("Failed to get suggestion count:", error);
    return 0;
  }
}

// ============================================================================
// Write Operations
// ============================================================================

/**
 * Verify (approve) a suggestion - creates subscription and links transactions
 * Accepts optional overrides for fields the user might customize in the form
 */
export async function verifySuggestion(
  suggestionId: string,
  overrides?: {
    accountId?: string;
    name?: string;
    merchant?: string;
    amount?: number;
    categoryId?: string;
    logoId?: string;
    importance?: number;
    frequency?: "weekly" | "biweekly" | "monthly" | "quarterly" | "yearly";
    description?: string;
  }
): Promise<{
  success: boolean;
  subscription?: (typeof recurringTransactions.$inferSelect) & {
    account?: unknown;
    category?: unknown;
    logo?: unknown;
  };
  linkedCount?: number;
  skippedCountDifferentAccount?: number;
  error?: string;
}> {
  const userId = await requireAuth();

  if (!userId) {
    return { success: false, error: "Not authenticated" };
  }

  try {
    const resolveInheritedFields = async (
      candidateTransactionIds: string[]
    ): Promise<{ categoryId: string | null; accountId: string | null }> => {
      if (candidateTransactionIds.length === 0) {
        return { categoryId: null, accountId: null };
      }

      const matchedTransactions = await db.query.transactions.findMany({
        where: and(
          inArray(transactions.id, candidateTransactionIds),
          eq(transactions.userId, userId)
        ),
        columns: {
          accountId: true,
          categoryId: true,
          categorySystemId: true,
        },
      });

      const counts = new Map<string, number>();
      const accountCounts = new Map<string, number>();
      for (const tx of matchedTransactions) {
        if (tx.accountId) {
          accountCounts.set(tx.accountId, (accountCounts.get(tx.accountId) ?? 0) + 1);
        }

        const categoryId = tx.categoryId ?? tx.categorySystemId;
        if (!categoryId) {
          continue;
        }
        counts.set(categoryId, (counts.get(categoryId) ?? 0) + 1);
      }

      let selectedCategoryId: string | null = null;
      let selectedCount = 0;
      for (const [categoryId, count] of counts.entries()) {
        if (count > selectedCount) {
          selectedCategoryId = categoryId;
          selectedCount = count;
        }
      }

      let selectedAccountId: string | null = null;
      let selectedAccountCount = 0;
      for (const [accountId, count] of accountCounts.entries()) {
        if (count > selectedAccountCount) {
          selectedAccountId = accountId;
          selectedAccountCount = count;
        }
      }

      return {
        categoryId: selectedCategoryId,
        accountId: selectedAccountId,
      };
    };

    // Get the suggestion
    const suggestion = await db.query.subscriptionSuggestions.findFirst({
      where: and(
        eq(subscriptionSuggestions.id, suggestionId),
        eq(subscriptionSuggestions.userId, userId),
        eq(subscriptionSuggestions.status, "pending")
      ),
    });

    if (!suggestion) {
      return { success: false, error: "Suggestion not found" };
    }

    // Parse transaction IDs
    let transactionIds: string[] = [];
    try {
      transactionIds = JSON.parse(suggestion.matchedTransactionIds);
      if (!Array.isArray(transactionIds)) {
        transactionIds = [];
      }
    } catch {
      transactionIds = [];
    }

    // Use overrides or fall back to suggestion values
    const finalName = overrides?.name?.trim() || suggestion.suggestedName;
    const finalMerchant = overrides?.merchant?.trim() || suggestion.suggestedMerchant;
    const finalAmount = overrides?.amount?.toFixed(2) || suggestion.suggestedAmount;
    const finalFrequency = overrides?.frequency || (suggestion.detectedFrequency as "weekly" | "biweekly" | "monthly" | "quarterly" | "yearly");
    const finalImportance = overrides?.importance ?? 2;
    const inherited = await resolveInheritedFields(transactionIds);
    const inheritedCategoryId = inherited.categoryId;
    const inheritedAccountId = inherited.accountId;

    const finalCategoryId =
      overrides?.categoryId ??
      suggestion.suggestedCategoryId ??
      inheritedCategoryId ??
      null;
    const finalAccountId =
      overrides?.accountId ??
      suggestion.accountId ??
      inheritedAccountId ??
      null;

    if (!finalAccountId) {
      return { success: false, error: "Could not determine account for this suggestion" };
    }

    // Check for duplicate subscription name
    const existingSubscription = await db.query.recurringTransactions.findFirst({
      where: and(
        eq(recurringTransactions.userId, userId),
        eq(recurringTransactions.accountId, finalAccountId),
        eq(recurringTransactions.name, finalName)
      ),
    });

    if (existingSubscription) {
      return {
        success: false,
        error: "A subscription with this name already exists",
      };
    }

    // Create the subscription
    const [created] = await db
      .insert(recurringTransactions)
      .values({
        userId,
        accountId: finalAccountId,
        name: finalName,
        merchant: finalMerchant,
        amount: finalAmount,
        currency: suggestion.currency,
        frequency: finalFrequency,
        importance: finalImportance,
        categoryId: finalCategoryId,
        logoId: overrides?.logoId || null,
        description: overrides?.description?.trim() || null,
        isActive: true,
      })
      .returning();

    // Link matched transactions to the new subscription
    let linkedCount = 0;
    let skippedCountDifferentAccount = 0;
    if (transactionIds.length > 0) {
      // Verify transactions belong to user
      const userTransactions = await db.query.transactions.findMany({
        where: and(
          inArray(transactions.id, transactionIds),
          eq(transactions.userId, userId)
        ),
        columns: {
          id: true,
          accountId: true,
        },
      });

      const validIds: string[] = [];
      for (const tx of userTransactions) {
        if (tx.accountId === finalAccountId) {
          validIds.push(tx.id);
        } else {
          skippedCountDifferentAccount += 1;
        }
      }

      if (validIds.length > 0) {
        await db
          .update(transactions)
          .set({
            recurringTransactionId: created.id,
            updatedAt: new Date(),
          })
          .where(inArray(transactions.id, validIds));

        linkedCount = validIds.length;
      }
    }

    // Update suggestion status to approved
    await db
      .update(subscriptionSuggestions)
      .set({
        status: "approved",
        updatedAt: new Date(),
      })
      .where(eq(subscriptionSuggestions.id, suggestionId));

    // Fetch the created subscription with category relation
    const subscriptionWithCategory = await db.query.recurringTransactions.findFirst({
      where: eq(recurringTransactions.id, created.id),
      with: {
        account: true,
        category: true,
        logo: true,
      },
    });

    revalidatePath("/subscriptions");
    revalidatePath("/transactions");

    return {
      success: true,
      subscription: subscriptionWithCategory || created,
      linkedCount,
      skippedCountDifferentAccount,
    };
  } catch (error) {
    console.error("Failed to verify suggestion:", error);
    return { success: false, error: "Failed to create subscription" };
  }
}

/**
 * Dismiss a suggestion (hide it from the list)
 */
export async function dismissSuggestion(
  suggestionId: string
): Promise<{
  success: boolean;
  error?: string;
}> {
  const userId = await requireAuth();

  if (!userId) {
    return { success: false, error: "Not authenticated" };
  }

  try {
    // Verify ownership
    const suggestion = await db.query.subscriptionSuggestions.findFirst({
      where: and(
        eq(subscriptionSuggestions.id, suggestionId),
        eq(subscriptionSuggestions.userId, userId)
      ),
    });

    if (!suggestion) {
      return { success: false, error: "Suggestion not found" };
    }

    // Update status to dismissed
    await db
      .update(subscriptionSuggestions)
      .set({
        status: "dismissed",
        updatedAt: new Date(),
      })
      .where(eq(subscriptionSuggestions.id, suggestionId));

    revalidatePath("/subscriptions");

    return { success: true };
  } catch (error) {
    console.error("Failed to dismiss suggestion:", error);
    return { success: false, error: "Failed to dismiss suggestion" };
  }
}
