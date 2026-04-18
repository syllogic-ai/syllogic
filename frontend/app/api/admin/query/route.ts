import { NextRequest, NextResponse } from "next/server";
import { db } from "@/lib/db";
import { users, accounts, transactions, bankConnections, accountBalances, recurringTransactions, subscriptionSuggestions } from "@/lib/db/schema";
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
    await db
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

  // Cleanup: delete ALL transactions from bank-synced accounts so next sync creates them fresh
  // (runs full pipeline: FX rate, functional amount, balance, subscription detection, categorisation)
  if (action === "delete_bank_transactions") {
    const bankAccounts = await db
      .select({ id: accounts.id, name: accounts.name })
      .from(accounts)
      .where(and(eq(accounts.userId, userId), isNotNull(accounts.bankConnectionId)));

    if (bankAccounts.length === 0) {
      return NextResponse.json({ deleted: 0, message: "No bank-synced accounts found" });
    }

    const bankAccountIds = bankAccounts.map((a) => a.id);

    const countRows = await db
      .select({ id: transactions.id })
      .from(transactions)
      .where(and(eq(transactions.userId, userId), inArray(transactions.accountId, bankAccountIds)));

    await db
      .delete(transactions)
      .where(and(eq(transactions.userId, userId), inArray(transactions.accountId, bankAccountIds)));

    return NextResponse.json({
      deleted: countRows.length,
      accounts: bankAccounts.map((a) => ({ id: a.id, name: a.name })),
    });
  }

  // Full teardown: delete everything tied to all bank connections for this user
  // (transactions + account_balances cascade when accounts are deleted)
  if (action === "delete_all_bank_connections") {
    const connections = await db
      .select({ id: bankConnections.id, aspspName: bankConnections.aspspName })
      .from(bankConnections)
      .where(eq(bankConnections.userId, userId));

    if (connections.length === 0) {
      return NextResponse.json({ message: "No bank connections found" });
    }

    const connectionIds = connections.map((c) => c.id);

    const linkedAccounts = await db
      .select({ id: accounts.id, name: accounts.name })
      .from(accounts)
      .where(and(eq(accounts.userId, userId), inArray(accounts.bankConnectionId, connectionIds)));

    const accountIds = linkedAccounts.map((a) => a.id);

    let deletedTransactions = 0;
    let deletedBalances = 0;

    if (accountIds.length > 0) {
      // Count before deletion for the response
      const txnRows = await db
        .select({ id: transactions.id })
        .from(transactions)
        .where(and(eq(transactions.userId, userId), inArray(transactions.accountId, accountIds)));
      deletedTransactions = txnRows.length;

      const balRows = await db
        .select({ id: accountBalances.id })
        .from(accountBalances)
        .where(inArray(accountBalances.accountId, accountIds));
      deletedBalances = balRows.length;

      // Delete in order: subscriptions → balances → transactions → accounts
      // Subscriptions have ON DELETE SET NULL on account_id, so must be deleted explicitly.
      await db.delete(subscriptionSuggestions).where(inArray(subscriptionSuggestions.accountId, accountIds));
      await db.delete(recurringTransactions).where(inArray(recurringTransactions.accountId, accountIds));
      await db.delete(accountBalances).where(inArray(accountBalances.accountId, accountIds));
      await db.delete(transactions).where(
        and(eq(transactions.userId, userId), inArray(transactions.accountId, accountIds))
      );
      await db.delete(accounts).where(
        and(eq(accounts.userId, userId), inArray(accounts.id, accountIds))
      );
    }

    await db.delete(bankConnections).where(
      and(eq(bankConnections.userId, userId), inArray(bankConnections.id, connectionIds))
    );

    return NextResponse.json({
      deleted: {
        bank_connections: connections.length,
        accounts: linkedAccounts.length,
        transactions: deletedTransactions,
        account_balances: deletedBalances,
      },
      connections: connections.map((c) => c.aspspName),
    });
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
