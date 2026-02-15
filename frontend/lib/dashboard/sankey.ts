export interface SankeyCategoryInput {
  categoryId?: string | null;
  categoryName: string;
  total: number;
  categoryType: "income" | "expense";
}

export interface BuiltSankeyNode {
  name: string;
  categoryId?: string | null;
  categoryType?: "income" | "expense";
  total?: number;
}

export interface BuiltSankeyLink {
  source: number;
  target: number;
  value: number;
}

interface WorkingCategory {
  name: string;
  categoryId?: string | null;
  total: number;
  categoryType: "income" | "expense";
}

function sanitizeCategories(
  categories: SankeyCategoryInput[],
  type: "income" | "expense"
): WorkingCategory[] {
  return categories
    .filter((category) => Number.isFinite(category.total) && category.total > 0)
    .map((category) => ({
      name: category.categoryName || (type === "income" ? "Other Income" : "Other Expenses"),
      categoryId: category.categoryId ?? null,
      total: category.total,
      categoryType: type,
    }));
}

export function buildConservativeSankey(
  incomeCategoriesInput: SankeyCategoryInput[],
  expenseCategoriesInput: SankeyCategoryInput[]
): { nodes: BuiltSankeyNode[]; links: BuiltSankeyLink[] } {
  const incomeCategories = sanitizeCategories(incomeCategoriesInput, "income");
  const expenseCategories = sanitizeCategories(expenseCategoriesInput, "expense");

  if (incomeCategories.length === 0 || expenseCategories.length === 0) {
    return { nodes: [], links: [] };
  }

  const totalIncome = incomeCategories.reduce((sum, category) => sum + category.total, 0);
  const totalExpense = expenseCategories.reduce((sum, category) => sum + category.total, 0);

  if (totalIncome > totalExpense) {
    expenseCategories.push({
      name: "Savings",
      total: totalIncome - totalExpense,
      categoryType: "expense",
    });
  } else if (totalExpense > totalIncome) {
    incomeCategories.push({
      name: "Funding Gap",
      total: totalExpense - totalIncome,
      categoryType: "income",
    });
  }

  const adjustedTotalExpense = expenseCategories.reduce(
    (sum, category) => sum + category.total,
    0
  );

  if (adjustedTotalExpense <= 0) {
    return { nodes: [], links: [] };
  }

  const nodes: BuiltSankeyNode[] = [];
  const incomeNodeIndices: number[] = [];
  const expenseNodeIndices: number[] = [];

  incomeCategories.forEach((category) => {
    incomeNodeIndices.push(nodes.length);
    nodes.push({
      name: category.name,
      categoryId: category.categoryId,
      categoryType: "income",
      total: category.total,
    });
  });

  expenseCategories.forEach((category) => {
    expenseNodeIndices.push(nodes.length);
    nodes.push({
      name: category.name,
      categoryId: category.categoryId,
      categoryType: "expense",
      total: category.total,
    });
  });

  const links: BuiltSankeyLink[] = [];
  incomeCategories.forEach((incomeCategory, incomeIndex) => {
    expenseCategories.forEach((expenseCategory, expenseIndex) => {
      const value = (incomeCategory.total * expenseCategory.total) / adjustedTotalExpense;
      if (value <= 0) return;
      links.push({
        source: incomeNodeIndices[incomeIndex],
        target: expenseNodeIndices[expenseIndex],
        value,
      });
    });
  });

  return { nodes, links };
}
