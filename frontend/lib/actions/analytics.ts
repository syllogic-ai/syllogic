"use server";

import { db } from "@/lib/db";
import { transactions } from "@/lib/db/schema";
import { requireAuth } from "@/lib/auth-helpers";
import { eq, sql, gte, and, desc } from "drizzle-orm";

// Note: getTotalBalance has been consolidated in lib/actions/dashboard.ts
// Use: import { getTotalBalance } from "@/lib/actions/dashboard"
export { getTotalBalance } from "./dashboard";

export async function getTransactionSummary(days: number = 30) {
  const userId = await requireAuth();

  if (!userId) {
    return [];
  }

  const startDate = new Date();
  startDate.setDate(startDate.getDate() - days);

  const result = await db
    .select({
      date: sql<string>`DATE(${transactions.bookedAt})`,
      income: sql<string>`COALESCE(SUM(CASE WHEN ${transactions.transactionType} = 'credit' THEN ${transactions.amount} ELSE 0 END), 0)`,
      expenses: sql<string>`COALESCE(SUM(CASE WHEN ${transactions.transactionType} = 'debit' THEN ABS(${transactions.amount}) ELSE 0 END), 0)`,
    })
    .from(transactions)
    .where(
      and(
        eq(transactions.userId, userId),
        gte(transactions.bookedAt, startDate)
      )
    )
    .groupBy(sql`DATE(${transactions.bookedAt})`)
    .orderBy(sql`DATE(${transactions.bookedAt})`);

  return result.map((row) => ({
    date: row.date,
    income: parseFloat(row.income),
    expenses: parseFloat(row.expenses),
  }));
}

export async function getRecentTransactions(limit: number = 5) {
  const userId = await requireAuth();

  if (!userId) {
    return [];
  }

  const result = await db
    .select({
      id: transactions.id,
      description: transactions.description,
      merchant: transactions.merchant,
      amount: transactions.amount,
      transactionType: transactions.transactionType,
      bookedAt: transactions.bookedAt,
      currency: transactions.currency,
    })
    .from(transactions)
    .where(eq(transactions.userId, userId))
    .orderBy(desc(transactions.bookedAt))
    .limit(limit);

  return result.map((tx) => ({
    ...tx,
    amount: parseFloat(tx.amount?.toString() || "0"),
  }));
}
