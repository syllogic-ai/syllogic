"use server";

import { headers } from "next/headers";
import { revalidatePath } from "next/cache";
import { eq, and } from "drizzle-orm";
import { db } from "@/lib/db";
import { categories, type Category, type NewCategory } from "@/lib/db/schema";
import { auth } from "@/lib/auth";

export interface CategoryCreateInput {
  name: string;
  categoryType: "expense" | "income" | "transfer";
  color: string;
  icon: string;
  description?: string;
  categorizationInstructions?: string;
}

export interface CategoryUpdateInput {
  name?: string;
  color?: string;
  icon?: string;
  description?: string;
  categorizationInstructions?: string;
}

export async function createCategory(
  input: CategoryCreateInput
): Promise<{ success: boolean; error?: string; categoryId?: string }> {
  const session = await auth.api.getSession({
    headers: await headers(),
  });

  if (!session?.user?.id) {
    return { success: false, error: "Not authenticated" };
  }

  try {
    // Check for duplicate name in the same category type
    const existing = await db.query.categories.findFirst({
      where: and(
        eq(categories.userId, session.user.id),
        eq(categories.name, input.name.trim()),
        eq(categories.categoryType, input.categoryType)
      ),
    });

    if (existing) {
      return { success: false, error: "A category with this name already exists" };
    }

    const newCategory: NewCategory = {
      userId: session.user.id,
      name: input.name.trim(),
      categoryType: input.categoryType,
      color: input.color,
      icon: input.icon,
      description: input.description?.trim() || null,
      categorizationInstructions: input.categorizationInstructions?.trim() || null,
      isSystem: false,
    };

    const [inserted] = await db.insert(categories).values(newCategory).returning({ id: categories.id });

    revalidatePath("/");
    revalidatePath("/settings");
    return { success: true, categoryId: inserted.id };
  } catch (error) {
    console.error("Failed to create category:", error);
    return { success: false, error: "Failed to create category" };
  }
}

export async function updateCategory(
  categoryId: string,
  input: CategoryUpdateInput
): Promise<{ success: boolean; error?: string }> {
  const session = await auth.api.getSession({
    headers: await headers(),
  });

  if (!session?.user?.id) {
    return { success: false, error: "Not authenticated" };
  }

  try {
    // Get the existing category
    const existing = await db.query.categories.findFirst({
      where: and(
        eq(categories.id, categoryId),
        eq(categories.userId, session.user.id)
      ),
    });

    if (!existing) {
      return { success: false, error: "Category not found" };
    }

    if (existing.isSystem) {
      return { success: false, error: "System categories cannot be modified" };
    }

    // Check for duplicate name if name is being changed
    if (input.name && input.name.trim() !== existing.name && existing.categoryType) {
      const duplicate = await db.query.categories.findFirst({
        where: and(
          eq(categories.userId, session.user.id),
          eq(categories.name, input.name.trim()),
          eq(categories.categoryType, existing.categoryType)
        ),
      });

      if (duplicate) {
        return { success: false, error: "A category with this name already exists" };
      }
    }

    await db
      .update(categories)
      .set({
        ...(input.name && { name: input.name.trim() }),
        ...(input.color && { color: input.color }),
        ...(input.icon && { icon: input.icon }),
        ...(input.description !== undefined && { description: input.description?.trim() || null }),
        ...(input.categorizationInstructions !== undefined && {
          categorizationInstructions: input.categorizationInstructions?.trim() || null,
        }),
      })
      .where(eq(categories.id, categoryId));

    revalidatePath("/");
    revalidatePath("/settings");
    return { success: true };
  } catch (error) {
    console.error("Failed to update category:", error);
    return { success: false, error: "Failed to update category" };
  }
}

export async function deleteCategory(
  categoryId: string
): Promise<{ success: boolean; error?: string }> {
  const session = await auth.api.getSession({
    headers: await headers(),
  });

  if (!session?.user?.id) {
    return { success: false, error: "Not authenticated" };
  }

  try {
    // Get the existing category
    const existing = await db.query.categories.findFirst({
      where: and(
        eq(categories.id, categoryId),
        eq(categories.userId, session.user.id)
      ),
    });

    if (!existing) {
      return { success: false, error: "Category not found" };
    }

    if (existing.isSystem) {
      return { success: false, error: "System categories cannot be deleted" };
    }

    await db.delete(categories).where(eq(categories.id, categoryId));

    revalidatePath("/");
    revalidatePath("/settings");
    return { success: true };
  } catch (error) {
    console.error("Failed to delete category:", error);
    return { success: false, error: "Failed to delete category" };
  }
}

export async function getCategories(): Promise<Category[]> {
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

export async function getCategoriesByType(
  type: "expense" | "income" | "transfer"
): Promise<Category[]> {
  const session = await auth.api.getSession({
    headers: await headers(),
  });

  if (!session?.user?.id) {
    return [];
  }

  return db.query.categories.findMany({
    where: and(
      eq(categories.userId, session.user.id),
      eq(categories.categoryType, type)
    ),
    orderBy: (categories, { asc }) => [asc(categories.name)],
  });
}
