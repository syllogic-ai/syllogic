"use server";

import { db } from "@/lib/db";
import { accounts, transactions, categories, users, properties, vehicles } from "@/lib/db/schema";
import { getAuthenticatedSession } from "@/lib/auth-helpers";
import { eq, sql, gte, and, desc } from "drizzle-orm";

async function getUserCurrency(userId: string): Promise<string> {
  const result = await db
    .select({ functionalCurrency: users.functionalCurrency })
    .from(users)
    .where(eq(users.id, userId))
    .limit(1);

  return result[0]?.functionalCurrency || "EUR";
}

export async function getTotalBalance() {
  const session = await getAuthenticatedSession();

  if (!session?.user?.id) {
    return { total: 0, currency: "EUR" };
  }

  const [result, currency] = await Promise.all([
    db
      .select({
        total: sql<string>`COALESCE(SUM(${accounts.functionalBalance}), 0)`,
      })
      .from(accounts)
      .where(
        and(eq(accounts.userId, session.user.id), eq(accounts.isActive, true))
      ),
    getUserCurrency(session.user.id),
  ]);

  return {
    total: parseFloat(result[0]?.total || "0"),
    currency,
  };
}

export async function getBalanceHistory(days: number = 7) {
  const session = await getAuthenticatedSession();

  if (!session?.user?.id) {
    return [];
  }

  const startDate = new Date();
  startDate.setDate(startDate.getDate() - days);

  // For balance history, we calculate running balance by summing transactions
  // This is a simplified approach - in production you'd want balance snapshots
  const result = await db
    .select({
      date: sql<string>`DATE(${transactions.bookedAt})`,
      netChange: sql<string>`COALESCE(SUM(
        CASE
          WHEN ${transactions.transactionType} = 'credit' THEN ${transactions.amount}
          ELSE -ABS(${transactions.amount})
        END
      ), 0)`,
    })
    .from(transactions)
    .where(
      and(
        eq(transactions.userId, session.user.id),
        gte(transactions.bookedAt, startDate)
      )
    )
    .groupBy(sql`DATE(${transactions.bookedAt})`)
    .orderBy(sql`DATE(${transactions.bookedAt})`);

  // Get current balance to work backwards
  const balanceResult = await db
    .select({
      total: sql<string>`COALESCE(SUM(${accounts.functionalBalance}), 0)`,
    })
    .from(accounts)
    .where(
      and(eq(accounts.userId, session.user.id), eq(accounts.isActive, true))
    );

  const currentBalance = parseFloat(balanceResult[0]?.total || "0");

  // Calculate cumulative balance for each day
  let runningBalance = currentBalance;
  const reversedData = [...result].reverse();
  const balanceHistory: { date: string; value: number }[] = [];

  // Start from most recent and work backwards
  for (const row of reversedData) {
    balanceHistory.unshift({
      date: row.date,
      value: runningBalance,
    });
    runningBalance -= parseFloat(row.netChange);
  }

  return balanceHistory;
}

export async function getMonthlySpending() {
  const session = await getAuthenticatedSession();

  if (!session?.user?.id) {
    return { total: 0, currency: "EUR" };
  }

  const startOfMonth = new Date();
  startOfMonth.setDate(1);
  startOfMonth.setHours(0, 0, 0, 0);

  const [result, currency] = await Promise.all([
    db
      .select({
        total: sql<string>`COALESCE(SUM(ABS(${transactions.amount})), 0)`,
      })
      .from(transactions)
      .where(
        and(
          eq(transactions.userId, session.user.id),
          eq(transactions.transactionType, "debit"),
          gte(transactions.bookedAt, startOfMonth)
        )
      ),
    getUserCurrency(session.user.id),
  ]);

  return {
    total: parseFloat(result[0]?.total || "0"),
    currency,
  };
}

export async function getMonthlyIncome() {
  const session = await getAuthenticatedSession();

  if (!session?.user?.id) {
    return { total: 0, currency: "EUR" };
  }

  const startOfMonth = new Date();
  startOfMonth.setDate(1);
  startOfMonth.setHours(0, 0, 0, 0);

  const [result, currency] = await Promise.all([
    db
      .select({
        total: sql<string>`COALESCE(SUM(${transactions.amount}), 0)`,
      })
      .from(transactions)
      .where(
        and(
          eq(transactions.userId, session.user.id),
          eq(transactions.transactionType, "credit"),
          gte(transactions.bookedAt, startOfMonth)
        )
      ),
    getUserCurrency(session.user.id),
  ]);

  return {
    total: parseFloat(result[0]?.total || "0"),
    currency,
  };
}

export async function getSpendingHistory(days: number = 7) {
  const session = await getAuthenticatedSession();

  if (!session?.user?.id) {
    return [];
  }

  const startDate = new Date();
  startDate.setDate(startDate.getDate() - days);

  const result = await db
    .select({
      date: sql<string>`DATE(${transactions.bookedAt})`,
      value: sql<string>`COALESCE(SUM(ABS(${transactions.amount})), 0)`,
    })
    .from(transactions)
    .where(
      and(
        eq(transactions.userId, session.user.id),
        eq(transactions.transactionType, "debit"),
        gte(transactions.bookedAt, startDate)
      )
    )
    .groupBy(sql`DATE(${transactions.bookedAt})`)
    .orderBy(sql`DATE(${transactions.bookedAt})`);

  return result.map((row) => ({
    date: row.date,
    value: parseFloat(row.value),
  }));
}

export async function getIncomeHistory(days: number = 7) {
  const session = await getAuthenticatedSession();

  if (!session?.user?.id) {
    return [];
  }

  const startDate = new Date();
  startDate.setDate(startDate.getDate() - days);

  const result = await db
    .select({
      date: sql<string>`DATE(${transactions.bookedAt})`,
      value: sql<string>`COALESCE(SUM(${transactions.amount}), 0)`,
    })
    .from(transactions)
    .where(
      and(
        eq(transactions.userId, session.user.id),
        eq(transactions.transactionType, "credit"),
        gte(transactions.bookedAt, startDate)
      )
    )
    .groupBy(sql`DATE(${transactions.bookedAt})`)
    .orderBy(sql`DATE(${transactions.bookedAt})`);

  return result.map((row) => ({
    date: row.date,
    value: parseFloat(row.value),
  }));
}

export async function getIncomeExpenseData() {
  const session = await getAuthenticatedSession();

  if (!session?.user?.id) {
    return [];
  }

  // Calculate the start date (12 months ago from the first of current month)
  const now = new Date();
  const startDate = new Date(now.getFullYear(), now.getMonth() - 11, 1);

  // Get monthly income and expenses for the last 12 months
  const result = await db
    .select({
      year: sql<number>`EXTRACT(YEAR FROM ${transactions.bookedAt})::int`,
      month: sql<number>`EXTRACT(MONTH FROM ${transactions.bookedAt})::int`,
      income: sql<string>`COALESCE(SUM(
        CASE WHEN ${transactions.transactionType} = 'credit' THEN ${transactions.amount} ELSE 0 END
      ), 0)`,
      expenses: sql<string>`COALESCE(SUM(
        CASE WHEN ${transactions.transactionType} = 'debit' THEN ABS(${transactions.amount}) ELSE 0 END
      ), 0)`,
    })
    .from(transactions)
    .where(
      and(
        eq(transactions.userId, session.user.id),
        gte(transactions.bookedAt, startDate)
      )
    )
    .groupBy(
      sql`EXTRACT(YEAR FROM ${transactions.bookedAt})`,
      sql`EXTRACT(MONTH FROM ${transactions.bookedAt})`
    )
    .orderBy(
      sql`EXTRACT(YEAR FROM ${transactions.bookedAt})`,
      sql`EXTRACT(MONTH FROM ${transactions.bookedAt})`
    );

  const monthNames = [
    "Jan",
    "Feb",
    "Mar",
    "Apr",
    "May",
    "Jun",
    "Jul",
    "Aug",
    "Sep",
    "Oct",
    "Nov",
    "Dec",
  ];

  // Create array of last 12 months with proper labels
  const months: { month: string; income: number; expenses: number }[] = [];
  for (let i = 0; i < 12; i++) {
    const date = new Date(now.getFullYear(), now.getMonth() - 11 + i, 1);
    const monthLabel = monthNames[date.getMonth()];
    months.push({
      month: monthLabel,
      income: 0,
      expenses: 0,
    });
  }

  // Fill in the data
  for (const row of result) {
    // Find the corresponding month in our array
    const rowDate = new Date(row.year, row.month - 1, 1);
    const monthIndex = months.findIndex((_, i) => {
      const targetDate = new Date(now.getFullYear(), now.getMonth() - 11 + i, 1);
      return (
        targetDate.getFullYear() === rowDate.getFullYear() &&
        targetDate.getMonth() === rowDate.getMonth()
      );
    });

    if (monthIndex !== -1) {
      months[monthIndex].income = parseFloat(row.income);
      months[monthIndex].expenses = parseFloat(row.expenses);
    }
  }

  return months;
}

export async function getSpendingByCategory(limit: number = 5) {
  const session = await getAuthenticatedSession();

  if (!session?.user?.id) {
    return { categories: [], total: 0 };
  }

  const startOfMonth = new Date();
  startOfMonth.setDate(1);
  startOfMonth.setHours(0, 0, 0, 0);

  // Get spending by category, including uncategorized transactions
  // Use COALESCE to fall back to categorySystemId when categoryId is null
  const categorizedResult = await db
    .select({
      id: categories.id,
      name: categories.name,
      icon: categories.icon,
      color: categories.color,
      amount: sql<string>`COALESCE(SUM(ABS(${transactions.amount})), 0)`,
    })
    .from(transactions)
    .leftJoin(
      categories,
      sql`${categories.id} = COALESCE(${transactions.categoryId}, ${transactions.categorySystemId})`
    )
    .where(
      and(
        eq(transactions.userId, session.user.id),
        eq(transactions.transactionType, "debit"),
        gte(transactions.bookedAt, startOfMonth),
        sql`COALESCE(${transactions.categoryId}, ${transactions.categorySystemId}) IS NOT NULL`
      )
    )
    .groupBy(categories.id, categories.name, categories.icon, categories.color)
    .orderBy(desc(sql`SUM(ABS(${transactions.amount}))`))
    .limit(limit);

  // Get uncategorized spending
  const uncategorizedResult = await db
    .select({
      amount: sql<string>`COALESCE(SUM(ABS(${transactions.amount})), 0)`,
    })
    .from(transactions)
    .where(
      and(
        eq(transactions.userId, session.user.id),
        eq(transactions.transactionType, "debit"),
        gte(transactions.bookedAt, startOfMonth),
        sql`${transactions.categoryId} IS NULL AND ${transactions.categorySystemId} IS NULL`
      )
    );

  // Get total spending for the month
  const totalResult = await db
    .select({
      total: sql<string>`COALESCE(SUM(ABS(${transactions.amount})), 0)`,
    })
    .from(transactions)
    .where(
      and(
        eq(transactions.userId, session.user.id),
        eq(transactions.transactionType, "debit"),
        gte(transactions.bookedAt, startOfMonth)
      )
    );

  const categorizedCategories = categorizedResult.map((row) => ({
    id: row.id,
    name: row.name,
    icon: row.icon,
    color: row.color,
    amount: parseFloat(row.amount),
  }));

  // Add uncategorized if there's any amount
  const uncategorizedAmount = parseFloat(uncategorizedResult[0]?.amount || "0");
  if (uncategorizedAmount > 0) {
    categorizedCategories.push({
      id: "uncategorized",
      name: "Uncategorized",
      icon: null,
      color: null,
      amount: uncategorizedAmount,
    });
  }

  // Sort by amount and limit
  const sortedCategories = categorizedCategories
    .sort((a, b) => b.amount - a.amount)
    .slice(0, limit);

  return {
    categories: sortedCategories,
    total: parseFloat(totalResult[0]?.total || "0"),
  };
}

// Asset category types and mapping
type AssetCategoryKey = "cash" | "investment" | "crypto" | "property" | "vehicle" | "other";

const ASSET_CATEGORY_COLORS: Record<AssetCategoryKey, string> = {
  cash: "#3B82F6",
  investment: "#10B981",
  crypto: "#F59E0B",
  property: "#8B5CF6",
  vehicle: "#EC4899",
  other: "#6B7280",
};

const ASSET_CATEGORY_LABELS: Record<AssetCategoryKey, string> = {
  cash: "Cash",
  investment: "Investment",
  crypto: "Crypto",
  property: "Property",
  vehicle: "Vehicle",
  other: "Other",
};

// Map account types to asset categories
function getAssetCategory(accountType: string): AssetCategoryKey {
  const typeMap: Record<string, AssetCategoryKey> = {
    checking: "cash",
    savings: "cash",
    credit: "other",
    investment: "investment",
    brokerage: "investment",
    crypto: "crypto",
    property: "property",
    vehicle: "vehicle",
  };
  return typeMap[accountType.toLowerCase()] || "other";
}

interface AssetAccount {
  id: string;
  name: string;
  institution: string | null;
  value: number;
  percentage: number;
  currency: string;
  initial: string;
}

interface AssetCategory {
  key: AssetCategoryKey;
  label: string;
  color: string;
  value: number;
  percentage: number;
  isActive: boolean;
  accounts: AssetAccount[];
}

interface AssetsOverviewData {
  total: number;
  currency: string;
  categories: AssetCategory[];
}

export async function getAssetsOverview(): Promise<AssetsOverviewData> {
  const session = await getAuthenticatedSession();

  if (!session?.user?.id) {
    return {
      total: 0,
      currency: "EUR",
      categories: Object.keys(ASSET_CATEGORY_LABELS).map((key) => ({
        key: key as AssetCategoryKey,
        label: ASSET_CATEGORY_LABELS[key as AssetCategoryKey],
        color: ASSET_CATEGORY_COLORS[key as AssetCategoryKey],
        value: 0,
        percentage: 0,
        isActive: false,
        accounts: [],
      })),
    };
  }

  const [userAccounts, userProperties, userVehicles, currency] = await Promise.all([
    db
      .select({
        id: accounts.id,
        name: accounts.name,
        accountType: accounts.accountType,
        institution: accounts.institution,
        functionalBalance: accounts.functionalBalance,
        currency: accounts.currency,
      })
      .from(accounts)
      .where(and(eq(accounts.userId, session.user.id), eq(accounts.isActive, true))),
    db
      .select({
        id: properties.id,
        name: properties.name,
        propertyType: properties.propertyType,
        address: properties.address,
        currentValue: properties.currentValue,
        currency: properties.currency,
      })
      .from(properties)
      .where(and(eq(properties.userId, session.user.id), eq(properties.isActive, true))),
    db
      .select({
        id: vehicles.id,
        name: vehicles.name,
        vehicleType: vehicles.vehicleType,
        make: vehicles.make,
        model: vehicles.model,
        year: vehicles.year,
        currentValue: vehicles.currentValue,
        currency: vehicles.currency,
      })
      .from(vehicles)
      .where(and(eq(vehicles.userId, session.user.id), eq(vehicles.isActive, true))),
    getUserCurrency(session.user.id),
  ]);

  // Group accounts by asset category
  const categoryMap = new Map<AssetCategoryKey, AssetAccount[]>();
  let total = 0;

  // Process bank accounts
  for (const account of userAccounts) {
    const category = getAssetCategory(account.accountType);
    const value = parseFloat(account.functionalBalance || "0");

    // Only include positive balances in assets
    if (value > 0) {
      total += value;

      if (!categoryMap.has(category)) {
        categoryMap.set(category, []);
      }

      categoryMap.get(category)!.push({
        id: account.id,
        name: account.name,
        institution: account.institution,
        value,
        percentage: 0, // Will calculate after totals
        currency: account.currency || currency,
        initial: account.name.charAt(0).toUpperCase(),
      });
    }
  }

  // Process properties
  for (const property of userProperties) {
    const value = parseFloat(property.currentValue || "0");

    if (value > 0) {
      total += value;

      if (!categoryMap.has("property")) {
        categoryMap.set("property", []);
      }

      // Extract city/state from address for display
      const addressParts = property.address?.split(",").map(p => p.trim()) || [];
      const location = addressParts.length > 1 ? addressParts.slice(-2).join(", ") : property.address;

      categoryMap.get("property")!.push({
        id: property.id,
        name: property.name,
        institution: location || null, // Use location as "institution" for display
        value,
        percentage: 0,
        currency: property.currency || currency,
        initial: property.name.charAt(0).toUpperCase(),
      });
    }
  }

  // Process vehicles
  for (const vehicle of userVehicles) {
    const value = parseFloat(vehicle.currentValue || "0");

    if (value > 0) {
      total += value;

      if (!categoryMap.has("vehicle")) {
        categoryMap.set("vehicle", []);
      }

      // Build make/model string for display
      const makeModel = [vehicle.make, vehicle.model].filter(Boolean).join(" ") || null;

      categoryMap.get("vehicle")!.push({
        id: vehicle.id,
        name: vehicle.name,
        institution: makeModel, // Use make/model as "institution" for display
        value,
        percentage: 0,
        currency: vehicle.currency || currency,
        initial: vehicle.name.charAt(0).toUpperCase(),
      });
    }
  }

  // Build categories with percentages
  const categoryOrder: AssetCategoryKey[] = ["cash", "investment", "crypto", "property", "vehicle", "other"];

  const categories: AssetCategory[] = categoryOrder.map((key) => {
    const accountsInCategory = categoryMap.get(key) || [];
    const categoryValue = accountsInCategory.reduce((sum, acc) => sum + acc.value, 0);
    const categoryPercentage = total > 0 ? (categoryValue / total) * 100 : 0;

    // Calculate account percentages relative to category total
    const accountsWithPercentages = accountsInCategory.map((acc) => ({
      ...acc,
      percentage: categoryValue > 0 ? (acc.value / categoryValue) * 100 : 0,
    }));

    // Sort accounts by value descending
    accountsWithPercentages.sort((a, b) => b.value - a.value);

    return {
      key,
      label: ASSET_CATEGORY_LABELS[key],
      color: ASSET_CATEGORY_COLORS[key],
      value: categoryValue,
      percentage: categoryPercentage,
      isActive: categoryValue > 0,
      accounts: accountsWithPercentages,
    };
  });

  return {
    total,
    currency,
    categories,
  };
}

export async function getDashboardData() {
  const session = await getAuthenticatedSession();

  if (!session?.user?.id) {
    return {
      balance: { total: 0, currency: "EUR" },
      balanceHistory: [],
      monthlySpending: { total: 0, currency: "EUR" },
      monthlyIncome: { total: 0, currency: "EUR" },
      spendingHistory: [],
      incomeHistory: [],
      incomeExpense: [],
      spendingByCategory: { categories: [], total: 0 },
      assetsOverview: {
        total: 0,
        currency: "EUR",
        categories: Object.keys(ASSET_CATEGORY_LABELS).map((key) => ({
          key: key as AssetCategoryKey,
          label: ASSET_CATEGORY_LABELS[key as AssetCategoryKey],
          color: ASSET_CATEGORY_COLORS[key as AssetCategoryKey],
          value: 0,
          percentage: 0,
          isActive: false,
          accounts: [],
        })),
      },
    };
  }

  const [
    balance,
    balanceHistory,
    monthlySpending,
    monthlyIncome,
    spendingHistory,
    incomeHistory,
    incomeExpense,
    spendingByCategory,
    assetsOverview,
  ] = await Promise.all([
    getTotalBalance(),
    getBalanceHistory(7),
    getMonthlySpending(),
    getMonthlyIncome(),
    getSpendingHistory(7),
    getIncomeHistory(7),
    getIncomeExpenseData(),
    getSpendingByCategory(5),
    getAssetsOverview(),
  ]);

  return {
    balance,
    balanceHistory,
    monthlySpending,
    monthlyIncome,
    spendingHistory,
    incomeHistory,
    incomeExpense,
    spendingByCategory,
    assetsOverview,
  };
}
