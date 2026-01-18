"use server";

import { eq, and, desc } from "drizzle-orm";
import { db } from "@/lib/db";
import { accounts, properties, vehicles, transactions } from "@/lib/db/schema";
import { requireAuth } from "@/lib/auth-helpers";
import { ASSET_CATEGORY_COLORS } from "@/components/assets/types";

export interface CommandPaletteAccount {
  id: string;
  name: string;
  institution: string | null;
  balance: number;
  currency: string;
  accountType: string;
}

export interface CommandPaletteAsset {
  id: string;
  name: string;
  value: number;
  currency: string;
  category: "property" | "vehicle";
  categoryColor: string;
  subtitle: string;
}

export interface CommandPaletteTransaction {
  id: string;
  merchant: string | null;
  description: string | null;
  amount: number;
  currency: string;
  bookedAt: Date;
  transactionType: string | null;
}

export interface CommandPaletteData {
  accounts: CommandPaletteAccount[];
  assets: CommandPaletteAsset[];
  transactions: CommandPaletteTransaction[];
}

export async function getCommandPaletteData(): Promise<CommandPaletteData> {
  const userId = await requireAuth();

  if (!userId) {
    return {
      accounts: [],
      assets: [],
      transactions: [],
    };
  }

  // Fetch all data in parallel
  const [accountsData, propertiesData, vehiclesData, transactionsData] = await Promise.all([
    db.query.accounts.findMany({
      where: and(eq(accounts.userId, userId), eq(accounts.isActive, true)),
      orderBy: [desc(accounts.createdAt)],
    }),
    db.query.properties.findMany({
      where: and(eq(properties.userId, userId), eq(properties.isActive, true)),
      orderBy: [desc(properties.createdAt)],
    }),
    db.query.vehicles.findMany({
      where: and(eq(vehicles.userId, userId), eq(vehicles.isActive, true)),
      orderBy: [desc(vehicles.createdAt)],
    }),
    db.query.transactions.findMany({
      where: eq(transactions.userId, userId),
      orderBy: [desc(transactions.bookedAt)],
      limit: 50,
    }),
  ]);

  // Transform accounts
  const formattedAccounts: CommandPaletteAccount[] = accountsData.map((account) => ({
    id: account.id,
    name: account.name,
    institution: account.institution,
    balance: parseFloat(account.functionalBalance || "0"),
    currency: account.currency || "EUR",
    accountType: account.accountType,
  }));

  // Transform assets (combine properties and vehicles)
  const formattedAssets: CommandPaletteAsset[] = [
    ...propertiesData.map((property) => ({
      id: property.id,
      name: property.name,
      value: parseFloat(property.currentValue || "0"),
      currency: property.currency || "EUR",
      category: "property" as const,
      categoryColor: ASSET_CATEGORY_COLORS.property,
      subtitle: property.address || property.propertyType || "",
    })),
    ...vehiclesData.map((vehicle) => ({
      id: vehicle.id,
      name: vehicle.name,
      value: parseFloat(vehicle.currentValue || "0"),
      currency: vehicle.currency || "EUR",
      category: "vehicle" as const,
      categoryColor: ASSET_CATEGORY_COLORS.vehicle,
      subtitle: [vehicle.make, vehicle.model, vehicle.year].filter(Boolean).join(" ") || vehicle.vehicleType || "",
    })),
  ];

  // Transform transactions
  const formattedTransactions: CommandPaletteTransaction[] = transactionsData.map((tx) => ({
    id: tx.id,
    merchant: tx.merchant,
    description: tx.description,
    amount: parseFloat(tx.amount),
    currency: tx.currency || "EUR",
    bookedAt: tx.bookedAt,
    transactionType: tx.transactionType,
  }));

  return {
    accounts: formattedAccounts,
    assets: formattedAssets,
    transactions: formattedTransactions,
  };
}
