"use server";

import { headers } from "next/headers";
import { revalidatePath } from "next/cache";
import { eq } from "drizzle-orm";
import { db } from "@/lib/db";
import { users, categories, type NewCategory } from "@/lib/db/schema";
import { auth } from "@/lib/auth";
import { DEFAULT_CATEGORIES, type DefaultCategory } from "@/lib/constants";
import { storage } from "@/lib/storage";

export type OnboardingStatus = "pending" | "step_1" | "step_2" | "step_3" | "completed";

export async function getOnboardingStatus(): Promise<OnboardingStatus | null> {
  const session = await auth.api.getSession({
    headers: await headers(),
  });

  if (!session?.user?.id) {
    return null;
  }

  const user = await db.query.users.findFirst({
    where: eq(users.id, session.user.id),
    columns: {
      onboardingStatus: true,
    },
  });

  return (user?.onboardingStatus as OnboardingStatus) ?? "pending";
}

export async function getCurrentUser() {
  const session = await auth.api.getSession({
    headers: await headers(),
  });

  if (!session?.user?.id) {
    return null;
  }

  return db.query.users.findFirst({
    where: eq(users.id, session.user.id),
  });
}

export interface PersonalDetailsData {
  name: string;
  functionalCurrency: string;
}

export async function updatePersonalDetails(formData: FormData): Promise<{ success: boolean; error?: string }> {
  const session = await auth.api.getSession({
    headers: await headers(),
  });

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
  const session = await auth.api.getSession({
    headers: await headers(),
  });

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

    // Update onboarding status
    await db
      .update(users)
      .set({
        onboardingStatus: "step_2",
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

export async function skipBankConnection(): Promise<{ success: boolean; error?: string }> {
  const session = await auth.api.getSession({
    headers: await headers(),
  });

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
    console.error("Failed to skip bank connection:", error);
    return { success: false, error: "Failed to complete onboarding" };
  }
}

export async function completeOnboarding(): Promise<{ success: boolean; error?: string }> {
  const session = await auth.api.getSession({
    headers: await headers(),
  });

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

export async function getDefaultCategories(): Promise<DefaultCategory[]> {
  return DEFAULT_CATEGORIES;
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
