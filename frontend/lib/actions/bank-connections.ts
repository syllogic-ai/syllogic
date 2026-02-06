"use server";

import { revalidatePath } from "next/cache";
import { eq, and } from "drizzle-orm";
import { db } from "@/lib/db";
import { bankConnections, accounts } from "@/lib/db/schema";
import { requireAuth } from "@/lib/auth-helpers";
import { getBackendBaseUrl } from "@/lib/backend-url";

const BACKEND_URL = getBackendBaseUrl();

export interface BankConnection {
  id: string;
  institutionName: string | null;
  institutionId: string;
  requisitionId: string | null;
  status: string | null; // pending, linked, expired, revoked
  agreementId: string | null;
  link: string | null;
  accountCount: number;
  createdAt: string | null;
  expiresAt: string | null;
}

export interface InitiateBankConnectionResult {
  success: boolean;
  authorizationUrl?: string;
  state?: string;
  error?: string;
}

export interface CompleteBankConnectionResult {
  success: boolean;
  connectionId?: string;
  accountCount?: number;
  error?: string;
}

export async function initiateBankConnection(): Promise<InitiateBankConnectionResult> {
  const userId = await requireAuth();

  if (!userId) {
    return { success: false, error: "Not authenticated" };
  }

  try {
    const response = await fetch(`${BACKEND_URL}/api/ponto/authorize?user_id=${userId}`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
    });

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}));
      return {
        success: false,
        error: errorData.detail || "Failed to initiate bank connection",
      };
    }

    const data = await response.json();

    return {
      success: true,
      authorizationUrl: data.authorization_url,
      state: data.state,
    };
  } catch (error) {
    console.error("Failed to initiate bank connection:", error);
    return {
      success: false,
      error: "Failed to connect to backend service",
    };
  }
}

export async function completeBankConnection(
  code: string,
  state: string
): Promise<CompleteBankConnectionResult> {
  const userId = await requireAuth();

  if (!userId) {
    return { success: false, error: "Not authenticated" };
  }

  try {
    const response = await fetch(
      `${BACKEND_URL}/api/ponto/callback?code=${encodeURIComponent(code)}&state=${encodeURIComponent(state)}`,
      {
        method: "GET",
        headers: {
          "Content-Type": "application/json",
        },
      }
    );

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}));
      return {
        success: false,
        error: errorData.detail || "Failed to complete bank connection",
      };
    }

    const data = await response.json();

    revalidatePath("/settings");
    revalidatePath("/");

    return {
      success: true,
      connectionId: data.connection_id,
      accountCount: data.account_count,
    };
  } catch (error) {
    console.error("Failed to complete bank connection:", error);
    return {
      success: false,
      error: "Failed to complete bank connection",
    };
  }
}

export async function getBankConnections(): Promise<BankConnection[]> {
  const userId = await requireAuth();

  if (!userId) {
    return [];
  }

  try {
    // Get connections from the database
    const connections = await db.query.bankConnections.findMany({
      where: eq(bankConnections.userId, userId),
    });

    // Get account counts for each connection
    const result: BankConnection[] = [];

    // Get total account count for the user (accounts aren't directly linked to connections)
    const userAccounts = await db.query.accounts.findMany({
      where: eq(accounts.userId, userId),
    });
    const accountCount = userAccounts.length;

    for (const conn of connections) {
      result.push({
        id: conn.id,
        institutionName: conn.institutionName || null,
        institutionId: conn.institutionId,
        requisitionId: conn.requisitionId || null,
        status: conn.status || null,
        agreementId: conn.agreementId || null,
        link: conn.link || null,
        accountCount,
        createdAt: conn.createdAt?.toISOString() || null,
        expiresAt: conn.expiresAt?.toISOString() || null,
      });
    }

    return result;
  } catch (error) {
    console.error("Failed to get bank connections:", error);
    return [];
  }
}

export async function disconnectBank(
  connectionId: string
): Promise<{ success: boolean; error?: string }> {
  const userId = await requireAuth();

  if (!userId) {
    return { success: false, error: "Not authenticated" };
  }

  try {
    // Verify ownership
    const connection = await db.query.bankConnections.findFirst({
      where: and(
        eq(bankConnections.id, connectionId),
        eq(bankConnections.userId, userId)
      ),
    });

    if (!connection) {
      return { success: false, error: "Connection not found" };
    }

    const response = await fetch(
      `${BACKEND_URL}/api/ponto/disconnect/${connectionId}?user_id=${userId}`,
      {
        method: "DELETE",
        headers: {
          "Content-Type": "application/json",
        },
      }
    );

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}));
      return {
        success: false,
        error: errorData.detail || "Failed to disconnect bank",
      };
    }

    revalidatePath("/settings");
    revalidatePath("/");

    return { success: true };
  } catch (error) {
    console.error("Failed to disconnect bank:", error);
    return { success: false, error: "Failed to disconnect bank" };
  }
}

export async function triggerManualSync(
  connectionId: string
): Promise<{
  success: boolean;
  transactionsCreated?: number;
  transactionsUpdated?: number;
  suggestionsCount?: number;
  error?: string;
}> {
  const userId = await requireAuth();

  if (!userId) {
    return { success: false, error: "Not authenticated" };
  }

  try {
    // Verify ownership
    const connection = await db.query.bankConnections.findFirst({
      where: and(
        eq(bankConnections.id, connectionId),
        eq(bankConnections.userId, userId)
      ),
    });

    if (!connection) {
      return { success: false, error: "Connection not found" };
    }

    const response = await fetch(
      `${BACKEND_URL}/api/ponto/sync/${connectionId}?user_id=${userId}`,
      {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
      }
    );

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}));
      return {
        success: false,
        error: errorData.detail || "Failed to sync",
      };
    }

    const data = await response.json();

    revalidatePath("/transactions");
    revalidatePath("/subscriptions");
    revalidatePath("/");

    return {
      success: true,
      transactionsCreated: data.transactions_created,
      transactionsUpdated: data.transactions_updated,
      suggestionsCount: data.suggestions_count || 0,
    };
  } catch (error) {
    console.error("Failed to trigger sync:", error);
    return { success: false, error: "Failed to trigger sync" };
  }
}

export async function getConnectionAccounts(connectionId: string) {
  const userId = await requireAuth();

  if (!userId) {
    return [];
  }

  try {
    // Verify ownership
    const connection = await db.query.bankConnections.findFirst({
      where: and(
        eq(bankConnections.id, connectionId),
        eq(bankConnections.userId, userId)
      ),
    });

    if (!connection) {
      return [];
    }

    // Note: accounts table doesn't have bankConnectionId field
    // Returning all active accounts for the user for now
    return db.query.accounts.findMany({
      where: and(
        eq(accounts.userId, userId),
        eq(accounts.isActive, true)
      ),
      orderBy: (accounts, { asc }) => [asc(accounts.name)],
    });
  } catch (error) {
    console.error("Failed to get connection accounts:", error);
    return [];
  }
}
