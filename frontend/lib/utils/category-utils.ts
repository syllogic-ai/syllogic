/**
 * Category filtering utilities
 * Provides reusable functions for filtering categories by type
 */

export type CategoryType = "expense" | "income" | "transfer";

/**
 * Filter out categories that should be hidden from manual selection
 * (e.g., "Balancing Transfer" which is system-assigned only)
 */
export function filterSelectableCategories<T extends { hideFromSelection?: boolean | null; name?: string }>(
  categories: T[]
): T[] {
  return categories.filter((c) => !c.hideFromSelection);
}

/**
 * Filter categories by a specific type
 */
export function filterCategoriesByType<T extends { categoryType: string | null }>(
  categories: T[],
  type: CategoryType
): T[] {
  return categories.filter((c) => c.categoryType === type);
}

/**
 * Group categories by their type
 */
export function groupCategoriesByType<T extends { categoryType: string | null }>(categories: T[]): {
  expense: T[];
  income: T[];
  transfer: T[];
} {
  return {
    expense: filterCategoriesByType(categories, "expense"),
    income: filterCategoriesByType(categories, "income"),
    transfer: filterCategoriesByType(categories, "transfer"),
  };
}

/**
 * Get categories that apply to a transaction type
 * For debits: expense and transfer categories
 * For credits: income and transfer categories
 * Automatically filters out categories hidden from selection
 */
export function getCategoriesForTransactionType<T extends { categoryType: string | null; hideFromSelection?: boolean | null }>(
  categories: T[],
  transactionType: "debit" | "credit"
): T[] {
  const selectableCategories = filterSelectableCategories(categories);
  if (transactionType === "debit") {
    return selectableCategories.filter(
      (c) => c.categoryType === "expense" || c.categoryType === "transfer"
    );
  }
  return selectableCategories.filter(
    (c) => c.categoryType === "income" || c.categoryType === "transfer"
  );
}

/**
 * Get a human-readable label for a category type
 */
export function getCategoryTypeLabel(type: CategoryType): string {
  switch (type) {
    case "expense":
      return "Expense";
    case "income":
      return "Income";
    case "transfer":
      return "Transfer";
  }
}
