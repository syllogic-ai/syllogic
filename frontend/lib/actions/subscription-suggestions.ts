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
 */
export async function verifySuggestion(
  suggestionId: string
): Promise<{
  success: boolean;
  subscriptionId?: string;
  linkedCount?: number;
  error?: string;
}> {
  const userId = await requireAuth();

  if (!userId) {
    return { success: false, error: "Not authenticated" };
  }

  try {
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

    // Check for duplicate subscription name
    const existingSubscription = await db.query.recurringTransactions.findFirst({
      where: and(
        eq(recurringTransactions.userId, userId),
        eq(recurringTransactions.name, suggestion.suggestedName)
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
        name: suggestion.suggestedName,
        merchant: suggestion.suggestedMerchant,
        amount: suggestion.suggestedAmount,
        currency: suggestion.currency,
        frequency: suggestion.detectedFrequency as "weekly" | "biweekly" | "monthly" | "quarterly" | "yearly",
        importance: 2, // Default medium importance
        isActive: true,
      })
      .returning({ id: recurringTransactions.id });

    // Link matched transactions to the new subscription
    let linkedCount = 0;
    if (transactionIds.length > 0) {
      // Verify transactions belong to user
      const userTransactions = await db.query.transactions.findMany({
        where: and(
          inArray(transactions.id, transactionIds),
          eq(transactions.userId, userId)
        ),
        columns: { id: true },
      });

      const validIds = userTransactions.map((t) => t.id);

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

    revalidatePath("/subscriptions");
    revalidatePath("/transactions");

    return {
      success: true,
      subscriptionId: created.id,
      linkedCount,
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
