import { NextRequest, NextResponse } from "next/server";
import { db } from "@/lib/db";
import {
  accounts,
  transactions,
  accountBalances,
  bankConnections,
} from "@/lib/db/schema";
import { eq, and, like, inArray, sql } from "drizzle-orm";

/**
 * Temporary admin endpoint to clean up "Unknown Account" entries
 * and expired bank connections for a specific user.
 *
 * Auth: requires INTERNAL_AUTH_SECRET as Bearer token.
 *
 * POST /api/admin/cleanup-accounts
 * Body: { "email": "user@example.com", "accountNamePattern": "Unknown Account%" }
 *
 * TODO: Remove this endpoint after cleanup is complete.
 */
export async function POST(req: NextRequest) {
  // Authenticate with internal secret
  const authHeader = req.headers.get("authorization");
  const secret = process.env.INTERNAL_AUTH_SECRET?.trim();
  if (!secret || authHeader !== `Bearer ${secret}`) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  try {
    const body = await req.json();
    const email = body.email as string;
    const accountNamePattern = (body.accountNamePattern as string) || "Unknown Account%";
    const deleteExpiredConnections = body.deleteExpiredConnections !== false;

    if (!email) {
      return NextResponse.json({ error: "email is required" }, { status: 400 });
    }

    // Find user by email
    // db.execute() with postgres.js returns a RowList which is array-like directly
    const userRows = await db.execute(
      sql`SELECT id, email FROM "user" WHERE email = ${email}`
    );
    if (!userRows.length) {
      return NextResponse.json({ error: "User not found" }, { status: 404 });
    }
    const userId = (userRows[0] as Record<string, unknown>).id as string;

    // Find matching accounts
    const matchingAccounts = await db
      .select({ id: accounts.id, name: accounts.name, bankConnectionId: accounts.bankConnectionId })
      .from(accounts)
      .where(and(eq(accounts.userId, userId), like(accounts.name, accountNamePattern)));

    if (!matchingAccounts.length) {
      return NextResponse.json({
        message: "No matching accounts found",
        userId,
        accountNamePattern,
      });
    }

    const accountIds = matchingAccounts.map((a) => a.id);

    // Delete account balances for these accounts
    const deletedBalances = await db
      .delete(accountBalances)
      .where(inArray(accountBalances.accountId, accountIds))
      .returning({ id: accountBalances.id });

    // Delete transactions for these accounts
    const deletedTransactions = await db
      .delete(transactions)
      .where(
        and(inArray(transactions.accountId, accountIds), eq(transactions.userId, userId))
      )
      .returning({ id: transactions.id });

    // Delete the accounts themselves
    const deletedAccounts = await db
      .delete(accounts)
      .where(inArray(accounts.id, accountIds))
      .returning({ id: accounts.id, name: accounts.name });

    // Optionally delete expired bank connections
    let deletedConnections: { id: string; aspspName: string }[] = [];
    if (deleteExpiredConnections) {
      const expired = await db
        .delete(bankConnections)
        .where(
          and(eq(bankConnections.userId, userId), eq(bankConnections.status, "expired"))
        )
        .returning({ id: bankConnections.id, aspspName: bankConnections.aspspName });
      deletedConnections = expired;
    }

    return NextResponse.json({
      success: true,
      userId,
      deletedAccounts: deletedAccounts.map((a) => ({ id: a.id, name: a.name })),
      deletedTransactionsCount: deletedTransactions.length,
      deletedBalancesCount: deletedBalances.length,
      deletedExpiredConnections: deletedConnections.map((c) => ({
        id: c.id,
        aspspName: c.aspspName,
      })),
    });
  } catch (error) {
    console.error("Cleanup failed:", error);
    return NextResponse.json(
      { error: "Cleanup failed", detail: String(error) },
      { status: 500 }
    );
  }
}
