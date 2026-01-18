"use server";

import { revalidatePath } from "next/cache";
import { eq } from "drizzle-orm";
import { db } from "@/lib/db";
import { users, categories, type User } from "@/lib/db/schema";
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
    const functionalCurrency = formData.get("functionalCurrency") as string;
    const profilePhoto = formData.get("profilePhoto") as File | null;

    if (!name?.trim()) {
      return { success: false, error: "Name is required" };
    }

    let profilePhotoPath: string | undefined;

    // Handle profile photo upload
    if (profilePhoto && profilePhoto.size > 0) {
      const fileExtension = profilePhoto.name.split(".").pop() || "jpg";
      const fileName = `profile/${session.user.id}.${fileExtension}`;
      const buffer = Buffer.from(await profilePhoto.arrayBuffer());

      const uploadedFile = await storage.upload(fileName, buffer, {
        contentType: profilePhoto.type,
      });

      profilePhotoPath = uploadedFile.url;
    }

    await db
      .update(users)
      .set({
        name: name.trim(),
        functionalCurrency,
        ...(profilePhotoPath && { profilePhotoPath }),
        updatedAt: new Date(),
      })
      .where(eq(users.id, session.user.id));

    revalidatePath("/");
    revalidatePath("/settings");
    return { success: true };
  } catch (error) {
    console.error("Failed to update user profile:", error);
    return { success: false, error: "Failed to update profile" };
  }
}

/**
 * Reset onboarding status to pending and delete all user categories.
 * This allows the user to go through the onboarding flow again.
 */
export async function resetOnboarding(): Promise<{ success: boolean; error?: string }> {
  const userId = await requireAuth();

  if (!userId) {
    return { success: false, error: "Not authenticated" };
  }

  try {
    // Delete all user categories
    await db.delete(categories).where(eq(categories.userId, userId));

    // Reset onboarding status
    await db
      .update(users)
      .set({
        onboardingStatus: "pending",
        onboardingCompletedAt: null,
        updatedAt: new Date(),
      })
      .where(eq(users.id, userId));

    revalidatePath("/");
    return { success: true };
  } catch (error) {
    console.error("Failed to reset onboarding:", error);
    return { success: false, error: "Failed to reset onboarding" };
  }
}
