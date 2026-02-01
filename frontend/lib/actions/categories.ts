"use server";

import { revalidatePath } from "next/cache";
import { eq, and, count } from "drizzle-orm";
import { db } from "@/lib/db";
import { categories, transactions, type Category, type NewCategory } from "@/lib/db/schema";
import { requireAuth } from "@/lib/auth-helpers";

export interface CategoryCreateInput {
  name: string;
  categoryType: "expense" | "income" | "transfer";
  color: string;
  icon: string;
  description?: string;
  categorizationInstructions?: string;
}

export interface CategoryInput {
  name: string;
  categoryType: "expense" | "income" | "transfer";
  color: string;
  icon: string;
  description?: string;
  categorizationInstructions?: string;
  isSystem?: boolean;
  hideFromSelection?: boolean;
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
  const userId = await requireAuth();

  if (!userId) {
    return { success: false, error: "Not authenticated" };
  }

  try {
    // Check for duplicate name in the same category type
    const existing = await db.query.categories.findFirst({
      where: and(
        eq(categories.userId, userId),
        eq(categories.name, input.name.trim()),
        eq(categories.categoryType, input.categoryType)
      ),
    });

    if (existing) {
      return { success: false, error: "A category with this name already exists" };
    }

    const newCategory: NewCategory = {
      userId,
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
  const userId = await requireAuth();

  if (!userId) {
    return { success: false, error: "Not authenticated" };
  }

  try {
    // Get the existing category
    const existing = await db.query.categories.findFirst({
      where: and(
        eq(categories.id, categoryId),
        eq(categories.userId, userId)
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
          eq(categories.userId, userId),
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
  const userId = await requireAuth();

  if (!userId) {
    return { success: false, error: "Not authenticated" };
  }

  try {
    // Get the existing category
    const existing = await db.query.categories.findFirst({
      where: and(
        eq(categories.id, categoryId),
        eq(categories.userId, userId)
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
  const userId = await requireAuth();

  if (!userId) {
    return [];
  }

  return db.query.categories.findMany({
    where: eq(categories.userId, userId),
    orderBy: (categories, { asc }) => [asc(categories.name)],
  });
}

// Alias for backward compatibility
export const getUserCategories = getCategories;

export async function getCategoriesByType(
  type: "expense" | "income" | "transfer"
): Promise<Category[]> {
  const userId = await requireAuth();

  if (!userId) {
    return [];
  }

  return db.query.categories.findMany({
    where: and(
      eq(categories.userId, userId),
      eq(categories.categoryType, type)
    ),
    orderBy: (categories, { asc }) => [asc(categories.name)],
  });
}

export async function getCategoryByName(name: string): Promise<Category | null> {
  const userId = await requireAuth();

  if (!userId) {
    return null;
  }

  const category = await db.query.categories.findFirst({
    where: and(
      eq(categories.userId, userId),
      eq(categories.name, name)
    ),
  });

  return category || null;
}

/**
 * Get the count of transactions assigned to a category
 */
export async function getCategoryTransactionCount(
  categoryId: string
): Promise<{ count: number; error?: string }> {
  const userId = await requireAuth();

  if (!userId) {
    return { count: 0, error: "Not authenticated" };
  }

  try {
    const result = await db
      .select({ count: count() })
      .from(transactions)
      .where(
        and(
          eq(transactions.userId, userId),
          eq(transactions.categoryId, categoryId)
        )
      );

    return { count: result[0]?.count ?? 0 };
  } catch (error) {
    console.error("Failed to count category transactions:", error);
    return { count: 0, error: "Failed to count transactions" };
  }
}

/**
 * Delete a category with optional reassignment of transactions
 * @param categoryId - The category to delete
 * @param reassignToCategoryId - If provided, reassign transactions to this category; if null, set to uncategorized
 */
export async function deleteCategoryWithReassignment(
  categoryId: string,
  reassignToCategoryId: string | null
): Promise<{ success: boolean; error?: string; reassignedCount?: number }> {
  const userId = await requireAuth();

  if (!userId) {
    return { success: false, error: "Not authenticated" };
  }

  try {
    // Get the category to delete
    const categoryToDelete = await db.query.categories.findFirst({
      where: and(
        eq(categories.id, categoryId),
        eq(categories.userId, userId)
      ),
    });

    if (!categoryToDelete) {
      return { success: false, error: "Category not found" };
    }

    if (categoryToDelete.isSystem) {
      return { success: false, error: "System categories cannot be deleted" };
    }

    // If reassigning to another category, verify it exists and belongs to user
    if (reassignToCategoryId) {
      const targetCategory = await db.query.categories.findFirst({
        where: and(
          eq(categories.id, reassignToCategoryId),
          eq(categories.userId, userId)
        ),
      });

      if (!targetCategory) {
        return { success: false, error: "Target category not found" };
      }

      // Verify same category type
      if (targetCategory.categoryType !== categoryToDelete.categoryType) {
        return { success: false, error: "Cannot reassign to a different category type" };
      }
    }

    // Count affected transactions before update
    const countResult = await db
      .select({ count: count() })
      .from(transactions)
      .where(
        and(
          eq(transactions.userId, userId),
          eq(transactions.categoryId, categoryId)
        )
      );
    const reassignedCount = countResult[0]?.count ?? 0;

    // Reassign transactions
    await db
      .update(transactions)
      .set({ categoryId: reassignToCategoryId })
      .where(
        and(
          eq(transactions.userId, userId),
          eq(transactions.categoryId, categoryId)
        )
      );

    // Delete the category
    await db.delete(categories).where(eq(categories.id, categoryId));

    revalidatePath("/");
    revalidatePath("/settings");
    revalidatePath("/transactions");

    return { success: true, reassignedCount };
  } catch (error) {
    console.error("Failed to delete category:", error);
    return { success: false, error: "Failed to delete category" };
  }
}
