"use server";

import { revalidatePath } from "next/cache";
import { eq } from "drizzle-orm";
import { db } from "@/lib/db";
import { users, categories, transactions, accounts, type User } from "@/lib/db/schema";
import { getAuthenticatedSession, requireAuth } from "@/lib/auth-helpers";
import { storage } from "@/lib/storage";

/**
 * Check if the OpenAI API key is configured in the environment.
 * This is used to determine whether to show the CSV import option.
 */
export async function hasOpenAiApiKey(): Promise<boolean> {
  return !!process.env.OPENAI_API_KEY;
}

/**
 * Get the current user's profile data.
 */
export async function getCurrentUserProfile(): Promise<User | null> {
  const userId = await requireAuth();

  if (!userId) {
    return null;
  }

  const user = await db.query.users.findFirst({
    where: eq(users.id, userId),
  });

  return user || null;
}

/**
 * Update the current user's profile data.
 */
export async function updateUserProfile(
  formData: FormData
): Promise<{ success: boolean; error?: string }> {
  const session = await getAuthenticatedSession();

  if (!session?.user?.id) {
    return { success: false, error: "Not authenticated" };
  }

  try {
    const name = formData.get("name") as string;
    const profilePhotoEntry = formData.get("profilePhoto");
    const profilePhoto = profilePhotoEntry instanceof File ? profilePhotoEntry : null;

    if (!name?.trim()) {
      return { success: false, error: "Name is required" };
    }

    let profilePhotoPath: string | undefined;

    // Handle profile photo upload
    if (profilePhoto && profilePhoto.size > 0) {
      const fileExtension = profilePhoto.name.split(".").pop()?.toLowerCase() || "jpg";
      const fileName = `profile/${session.user.id}.${fileExtension}`;
      const buffer = Buffer.from(await profilePhoto.arrayBuffer());

      const uploadedFile = await storage.upload(fileName, buffer, {
        contentType: profilePhoto.type,
      });

      // Add cache-busting timestamp to prevent browser caching
      profilePhotoPath = `${uploadedFile.url}?v=${Date.now()}`;
    }

    await db
      .update(users)
      .set({
        name: name.trim(),
        ...(profilePhotoPath && { profilePhotoPath, image: profilePhotoPath }),
        updatedAt: new Date(),
      })
      .where(eq(users.id, session.user.id));

    // Ensure layout consumers (sidebar avatar) pick up the updated image immediately.
    revalidatePath("/", "layout");
    revalidatePath("/settings");
    return { success: true };
  } catch (error) {
    console.error("Failed to update user profile:", error);
    return { success: false, error: "Failed to update profile" };
  }
}

/**
 * Delete all transactions and reset account balances to starting balance.
 * This is a destructive operation that cannot be undone.
 */
export async function deleteAllTransactionsAndResetBalances(): Promise<{
  success: boolean;
  error?: string;
  deletedCount?: number;
  accountsReset?: number;
}> {
  const userId = await requireAuth();

  if (!userId) {
    return { success: false, error: "Not authenticated" };
  }

  try {
    // Delete all transactions for the user
    const deleted = await db
      .delete(transactions)
      .where(eq(transactions.userId, userId))
      .returning({ id: transactions.id });

    // Reset all account balances to their starting balance
    const userAccounts = await db.query.accounts.findMany({
      where: eq(accounts.userId, userId),
    });

    for (const account of userAccounts) {
      await db
        .update(accounts)
        .set({
          functionalBalance: account.startingBalance || "0",
          balanceAvailable: null,
          updatedAt: new Date(),
        })
        .where(eq(accounts.id, account.id));
    }

    revalidatePath("/");
    revalidatePath("/transactions");
    revalidatePath("/settings");

    return {
      success: true,
      deletedCount: deleted.length,
      accountsReset: userAccounts.length,
    };
  } catch (error) {
    console.error("Failed to delete transactions and reset balances:", error);
    return { success: false, error: "Failed to delete transactions and reset balances" };
  }
}
