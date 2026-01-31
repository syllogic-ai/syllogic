"use server";

import { revalidatePath } from "next/cache";
import { eq } from "drizzle-orm";
import { db } from "@/lib/db";
import { users, categories, type NewCategory } from "@/lib/db/schema";
import { getAuthenticatedSession, requireAuth } from "@/lib/auth-helpers";
import { DEFAULT_CATEGORIES, type DefaultCategory } from "@/lib/constants";
import { storage } from "@/lib/storage";

export type OnboardingStatus = "pending" | "step_1" | "step_2" | "completed";

export async function getOnboardingStatus(): Promise<OnboardingStatus | null> {
  const userId = await requireAuth();

  if (!userId) {
    return null;
  }

  const user = await db.query.users.findFirst({
    where: eq(users.id, userId),
    columns: {
      onboardingStatus: true,
    },
  });

  return (user?.onboardingStatus as OnboardingStatus) ?? "pending";
}

export async function getCurrentUser() {
  const userId = await requireAuth();

  if (!userId) {
    return null;
  }

  return db.query.users.findFirst({
    where: eq(users.id, userId),
  });
}

export interface PersonalDetailsData {
  name: string;
  functionalCurrency: string;
}

export async function updatePersonalDetails(formData: FormData): Promise<{ success: boolean; error?: string }> {
  const session = await getAuthenticatedSession();

  if (!session?.user?.id) {
    return { success: false, error: "Not authenticated" };
  }

  try {
    const name = formData.get("name") as string;
    const functionalCurrency = formData.get("functionalCurrency") as string;
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
        functionalCurrency,
        ...(profilePhotoPath && { profilePhotoPath }),
        onboardingStatus: "step_1",
        updatedAt: new Date(),
      })
      .where(eq(users.id, session.user.id));

    revalidatePath("/");
    return { success: true };
  } catch (error) {
    console.error("Failed to update personal details:", error);
    return { success: false, error: "Failed to update personal details" };
  }
}

export interface CategoryInput {
  name: string;
  categoryType: "expense" | "income" | "transfer";
  color: string;
  icon: string;
  description?: string;
  categorizationInstructions?: string;
  isSystem?: boolean;
}

export async function saveOnboardingCategories(
  categoryInputs: CategoryInput[]
): Promise<{ success: boolean; error?: string }> {
  const session = await getAuthenticatedSession();

  if (!session?.user?.id) {
    return { success: false, error: "Not authenticated" };
  }

  try {
    // Delete existing categories for the user (except system ones that might exist)
    await db.delete(categories).where(eq(categories.userId, session.user.id));

    // Insert new categories
    const categoriesToInsert: NewCategory[] = categoryInputs.map((cat) => ({
      userId: session.user.id,
      name: cat.name,
      categoryType: cat.categoryType,
      color: cat.color,
      icon: cat.icon,
      description: cat.description,
      categorizationInstructions: cat.categorizationInstructions,
      isSystem: cat.isSystem ?? false,
    }));

    if (categoriesToInsert.length > 0) {
      await db.insert(categories).values(categoriesToInsert);
    }

    // Update onboarding status to completed
    await db
      .update(users)
      .set({
        onboardingStatus: "completed",
        onboardingCompletedAt: new Date(),
        updatedAt: new Date(),
      })
      .where(eq(users.id, session.user.id));

    revalidatePath("/");
    return { success: true };
  } catch (error) {
    console.error("Failed to save categories:", error);
    return { success: false, error: "Failed to save categories" };
  }
}

export async function getDefaultCategories(): Promise<DefaultCategory[]> {
  return DEFAULT_CATEGORIES;
}

export async function completeOnboarding(): Promise<{ success: boolean; error?: string }> {
  const session = await getAuthenticatedSession();

  if (!session?.user?.id) {
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
      .where(eq(users.id, session.user.id));

    revalidatePath("/");
    return { success: true };
  } catch (error) {
    console.error("Failed to complete onboarding:", error);
    return { success: false, error: "Failed to complete onboarding" };
  }
}

// Note: getUserCategories has been consolidated in lib/actions/categories.ts
// Use: import { getUserCategories } from "@/lib/actions/categories"

export async function completeOnboarding(): Promise<{ success: boolean; error?: string }> {
  const session = await getAuthenticatedSession();

  if (!session?.user?.id) {
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
      .where(eq(users.id, session.user.id));

    revalidatePath("/");
    return { success: true };
  } catch (error) {
    console.error("Failed to complete onboarding:", error);
    return { success: false, error: "Failed to complete onboarding" };
  }
}
