"use server";

import { revalidatePath } from "next/cache";
import { eq } from "drizzle-orm";
import { db } from "@/lib/db";
import { users, categories, type User, type NewCategory } from "@/lib/db/schema";
import { getAuthenticatedSession, requireAuth } from "@/lib/auth-helpers";
import { storage } from "@/lib/storage";
import { DEFAULT_CATEGORIES, type DefaultCategory } from "@/lib/constants/default-categories";
import { type CategoryInput } from "./categories";

export type OnboardingStatus = "pending" | "step_1" | "step_2" | "step_3" | "completed";

export interface OnboardingStatusResult {
  status: OnboardingStatus;
  isCompleted: boolean;
}

/**
 * Get the current user's onboarding status
 */
export async function getOnboardingStatus(): Promise<OnboardingStatusResult | null> {
  const userId = await requireAuth();

  if (!userId) {
    return null;
  }

  try {
    const user = await db.query.users.findFirst({
      where: eq(users.id, userId),
    });

    if (!user) {
      console.warn(`[Onboarding] User not found: ${userId}`);
      return null;
    }

    const status = (user.onboardingStatus as OnboardingStatus) || "pending";

    return {
      status,
      isCompleted: status === "completed",
    };
  } catch (error: any) {
    // Log detailed error information
    console.error("[Onboarding] Failed to get onboarding status:", {
      error: error?.message || String(error),
      stack: error?.stack,
      userId,
      databaseUrl: process.env.DATABASE_URL ? "set" : "not set",
    });
    
    // Return default status on error to prevent app crash
    return {
      status: "pending",
      isCompleted: false,
    };
  }
}

/**
 * Get the current authenticated user for pre-filling forms
 */
export async function getCurrentUser(): Promise<User | null> {
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
 * Update personal details (step 1)
 * Sets onboardingStatus to step_1 upon success
 */
export async function updatePersonalDetails(
  formData: FormData
): Promise<{ success: boolean; error?: string }> {
  const session = await getAuthenticatedSession();

  if (!session?.user?.id) {
    return { success: false, error: "Not authenticated" };
  }

  try {
    const name = formData.get("name") as string;
    const currency = formData.get("currency") as string;
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
        functionalCurrency: currency || "EUR",
        ...(profilePhotoPath && { profilePhotoPath, image: profilePhotoPath }),
        onboardingStatus: "step_1",
        updatedAt: new Date(),
      })
      .where(eq(users.id, session.user.id));

    // Ensure layout consumers (sidebar avatar) pick up the updated image immediately.
    revalidatePath("/", "layout");
    return { success: true };
  } catch (error) {
    console.error("Failed to update personal details:", error);
    return { success: false, error: "Failed to update profile" };
  }
}

// Re-export CategoryInput for backward compatibility
export type { CategoryInput } from "./categories";

/**
 * Save onboarding categories (step 2)
 * This replaces all existing categories with the provided ones
 * Sets onboardingStatus to step_2 upon success
 */
export async function saveOnboardingCategories(
  categoryInputs: CategoryInput[]
): Promise<{ success: boolean; error?: string }> {
  const userId = await requireAuth();

  if (!userId) {
    return { success: false, error: "Not authenticated" };
  }

  try {
    // Delete existing categories
    await db.delete(categories).where(eq(categories.userId, userId));

    // Insert new categories
    const newCategories: NewCategory[] = categoryInputs.map((cat) => ({
      userId,
      name: cat.name,
      categoryType: cat.categoryType,
      color: cat.color,
      icon: cat.icon,
      description: cat.description || null,
      categorizationInstructions: cat.categorizationInstructions || null,
      isSystem: cat.isSystem || false,
      hideFromSelection: cat.hideFromSelection || false,
    }));

    if (newCategories.length > 0) {
      await db.insert(categories).values(newCategories);
    }

    // Update onboarding status
    await db
      .update(users)
      .set({
        onboardingStatus: "step_2",
        updatedAt: new Date(),
      })
      .where(eq(users.id, userId));

    revalidatePath("/");
    return { success: true };
  } catch (error) {
    console.error("Failed to save onboarding categories:", error);
    return { success: false, error: "Failed to save categories" };
  }
}

/**
 * Complete onboarding (step 3)
 * Sets onboardingStatus to completed with timestamp
 */
export async function completeOnboarding(): Promise<{ success: boolean; error?: string }> {
  const userId = await requireAuth();

  if (!userId) {
    return { success: false, error: "Not authenticated" };
  }

  try {
    await db
      .update(users)
      .set({
        onboardingStatus: "completed",
        onboardingCompletedAt: new Date(),
        updatedAt: new Date(),
      })
      .where(eq(users.id, userId));

    revalidatePath("/");
    return { success: true };
  } catch (error) {
    console.error("Failed to complete onboarding:", error);
    return { success: false, error: "Failed to complete onboarding" };
  }
}

/**
 * Get default categories for onboarding
 */
export async function getDefaultCategories(): Promise<DefaultCategory[]> {
  return DEFAULT_CATEGORIES;
}

/**
 * Get the redirect path based on onboarding status
 */
export async function getOnboardingRedirectPath(status: OnboardingStatus): Promise<string> {
  switch (status) {
    case "pending":
      return "/step-1";
    case "step_1":
      return "/step-2";
    case "step_2":
      return "/step-3";
    case "step_3":
    case "completed":
      return "/";
    default:
      return "/step-1";
  }
}
