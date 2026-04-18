import { NextRequest, NextResponse } from "next/server";
import { db } from "@/lib/db";
import { users, accounts, transactions } from "@/lib/db/schema";
import { eq, and, desc, isNull, isNotNull, inArray } from "drizzle-orm";

/** Temporary admin endpoint for DB inspection and cleanup. Remove after diagnosis. */
export async function POST(req: NextRequest) {
  const secret = process.env.INTERNAL_AUTH_SECRET?.trim();
  const auth = req.headers.get("authorization");
  if (!secret || auth !== `Bearer ${secret}`) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const body = await req.json();
  const { email, action } = body;
  if (!email) return NextResponse.json({ error: "email required" }, { status: 400 });

  const userRows = await db
    .select({ id: users.id })
    .from(users)
    .where(eq(users.email, email))
    .limit(1);

  if (!userRows.length) return NextResponse.json({ error: "User not found" }, { status: 404 });
  const userId = userRows[0].id;

  // Cleanup: delete all accounts that have never been synced (no lastSyncedAt) and 0 transactions
  if (action === "cleanup_unsynced_accounts") {
    const unsyncedAccounts = await db
      .select({ id: accounts.id, name: accounts.name, bankConnectionId: accounts.bankConnectionId })
      .from(accounts)
      .where(and(eq(accounts.userId, userId), isNull(accounts.lastSyncedAt)));

    // Filter to those with 0 transactions
    const toDelete: string[] = [];
    for (const acc of unsyncedAccounts) {
      const txnRows = await db
        .select({ id: transactions.id })
        .from(transactions)
        .where(eq(transactions.accountId, acc.id))
        .limit(1);
      if (txnRows.length === 0) toDelete.push(acc.id);
    }

    if (toDelete.length === 0) {
      return NextResponse.json({ deleted: 0, message: "Nothing to clean up" });
    }

    await db.delete(accounts).where(inArray(accounts.id, toDelete));
    return NextResponse.json({ deleted: toDelete.length, accountIds: toDelete });
  }

  // Cleanup: clear AI-assigned categories on bank-synced transactions so next sync re-categorises
  if (action === "clear_bank_categories") {
    const bankAccounts = await db
      .select({ id: accounts.id })
      .from(accounts)
      .where(and(eq(accounts.userId, userId), isNotNull(accounts.bankConnectionId)));

    if (bankAccounts.length === 0) {
      return NextResponse.json({ cleared: 0, message: "No bank-synced accounts found" });
    }

    const bankAccountIds = bankAccounts.map((a) => a.id);

    // Only clear category_system_id where user hasn't manually overridden (category_id is null)
    const result = await db
      .update(transactions)
      .set({ categorySystemId: null })
      .where(
        and(
          eq(transactions.userId, userId),
          inArray(transactions.accountId, bankAccountIds),
          isNull(transactions.categoryId),
          isNotNull(transactions.categorySystemId)
        )
      );

    return NextResponse.json({ cleared: true, accountIds: bankAccountIds });
  }

  // Default: inspect accounts + recent transactions
  const userAccounts = await db
    .select({
      id: accounts.id,
      name: accounts.name,
      currency: accounts.currency,
      bankConnectionId: accounts.bankConnectionId,
      functionalBalance: accounts.functionalBalance,
      lastSyncedAt: accounts.lastSyncedAt,
    })
    .from(accounts)
    .where(eq(accounts.userId, userId));

  const accountsWithTxns = await Promise.all(
    userAccounts.map(async (acc) => {
      const txns = await db
        .select({
          id: transactions.id,
          amount: transactions.amount,
          description: transactions.description,
          merchant: transactions.merchant,
          bookedAt: transactions.bookedAt,
          externalId: transactions.externalId,
        })
        .from(transactions)
        .where(and(eq(transactions.accountId, acc.id), eq(transactions.userId, userId)))
        .orderBy(desc(transactions.bookedAt))
        .limit(3);

      const total = await db
        .select({ count: transactions.id })
        .from(transactions)
        .where(and(eq(transactions.accountId, acc.id), eq(transactions.userId, userId)));

      return { ...acc, txnCount: total.length, recentTxns: txns };
    })
  );

  return NextResponse.json({ userId, accounts: accountsWithTxns });
}
