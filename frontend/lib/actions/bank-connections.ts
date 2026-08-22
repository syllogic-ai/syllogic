"use server";

import { revalidatePath } from "next/cache";
import { eq, and, desc, isNull, isNotNull } from "drizzle-orm";
import { db } from "@/lib/db";
import { bankConnections, accounts } from "@/lib/db/schema";
import { requireAuth, getAuthenticatedSession } from "@/lib/auth-helpers";
import { getBackendBaseUrl } from "@/lib/backend-url";
import { createInternalAuthHeaders } from "@/lib/internal-auth";
import { isDemoRestrictedUserEmail, DEMO_RESTRICTED_ACTION_ERROR } from "@/lib/demo-access";

export async function getBankConnections() {
  const userId = await requireAuth();
  if (!userId) return [];

  const [connections, linkedAccounts] = await Promise.all([
    db
      .select({
        id: bankConnections.id,
        userId: bankConnections.userId,
        provider: bankConnections.provider,
        aspspName: bankConnections.aspspName,
        aspspCountry: bankConnections.aspspCountry,
        consentExpiresAt: bankConnections.consentExpiresAt,
        status: bankConnections.status,
        lastSyncedAt: bankConnections.lastSyncedAt,
        lastSyncError: bankConnections.lastSyncError,
        createdAt: bankConnections.createdAt,
        updatedAt: bankConnections.updatedAt,
      })
      .from(bankConnections)
      .where(eq(bankConnections.userId, userId))
      .orderBy(desc(bankConnections.createdAt)),
    // Several connections to the same bank are otherwise indistinguishable —
    // same name, same country. The mapped accounts are what tells them apart.
    // IBAN can't be shown: it is only stored encrypted, and the key is server-side.
    db
      .select({
        id: accounts.id,
        name: accounts.name,
        currency: accounts.currency,
        bankConnectionId: accounts.bankConnectionId,
      })
      .from(accounts)
      .where(and(eq(accounts.userId, userId), isNotNull(accounts.bankConnectionId)))
      .orderBy(accounts.name),
  ]);

  const byConnection = new Map<string, { id: string; name: string; currency: string | null }[]>();
  for (const account of linkedAccounts) {
    const key = account.bankConnectionId!;
    const list = byConnection.get(key) ?? [];
    list.push({ id: account.id, name: account.name, currency: account.currency });
    byConnection.set(key, list);
  }

  return connections.map((connection) => ({
    ...connection,
    accounts: byConnection.get(connection.id) ?? [],
  }));
}

export async function getActiveBankConnectionsWithExpiry(): Promise<
  Array<{ id: string; aspspName: string; consentExpiresAt: Date | null; status: string }>
> {
  const userId = await requireAuth();
  if (!userId) return [];

  const connections = await db
    .select({
      id: bankConnections.id,
      aspspName: bankConnections.aspspName,
      consentExpiresAt: bankConnections.consentExpiresAt,
      status: bankConnections.status,
    })
    .from(bankConnections)
    .where(
      and(
        eq(bankConnections.userId, userId),
        eq(bankConnections.status, "active"),
      )
    );

  return connections;
}

export async function triggerSync(
  connectionId: string
): Promise<{ success: boolean; error?: string }> {
  const session = await getAuthenticatedSession();
  const userId = session?.user?.id;
  if (!userId) return { success: false, error: "Not authenticated" };
  if (isDemoRestrictedUserEmail(session.user.email)) {
    return { success: false, error: DEMO_RESTRICTED_ACTION_ERROR };
  }

  try {
    const backendBase = getBackendBaseUrl().replace(/\/+$/, "");
    const url = `${backendBase}/api/enable-banking/sync/${connectionId}`;

    const signatureHeaders = createInternalAuthHeaders({
      method: "POST",
      pathWithQuery: `/api/enable-banking/sync/${connectionId}`,
      userId,
    });

    const resp = await fetch(url, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...signatureHeaders,
      },
    });

    if (!resp.ok) {
      const data = await resp.json().catch(() => ({ detail: "Sync failed" }));
      return { success: false, error: data.detail || "Sync failed" };
    }

    revalidatePath("/settings");
    return { success: true };
  } catch (e) {
    return { success: false, error: "Failed to trigger sync" };
  }
}

export async function disconnectBank(
  connectionId: string
): Promise<{ success: boolean; error?: string }> {
  const session = await getAuthenticatedSession();
  const userId = session?.user?.id;
  if (!userId) return { success: false, error: "Not authenticated" };
  if (isDemoRestrictedUserEmail(session.user.email)) {
    return { success: false, error: DEMO_RESTRICTED_ACTION_ERROR };
  }

  try {
    const backendBase = getBackendBaseUrl().replace(/\/+$/, "");
    const url = `${backendBase}/api/enable-banking/${connectionId}`;

    const signatureHeaders = createInternalAuthHeaders({
      method: "DELETE",
      pathWithQuery: `/api/enable-banking/${connectionId}`,
      userId,
    });

    const resp = await fetch(url, {
      method: "DELETE",
      headers: signatureHeaders,
    });

    if (!resp.ok) {
      const data = await resp.json().catch(() => ({ detail: "Disconnect failed" }));
      return { success: false, error: data.detail || "Disconnect failed" };
    }

    revalidatePath("/settings");
    return { success: true };
  } catch (e) {
    return { success: false, error: "Failed to disconnect bank" };
  }
}

/**
 * Start a bank authorization. Pass connectionId to renew an existing
 * connection's consent in place — its accounts stay mapped and the callback
 * skips the mapping wizard.
 */
export async function initiateAuth(
  aspspName: string,
  aspspCountry: string,
  connectionId?: string
): Promise<{ success: boolean; url?: string; error?: string }> {
  const session = await getAuthenticatedSession();
  const userId = session?.user?.id;
  if (!userId) return { success: false, error: "Not authenticated" };
  if (isDemoRestrictedUserEmail(session.user.email)) {
    return { success: false, error: DEMO_RESTRICTED_ACTION_ERROR };
  }

  try {
    const backendBase = getBackendBaseUrl().replace(/\/+$/, "");
    const url = `${backendBase}/api/enable-banking/auth`;

    const signatureHeaders = createInternalAuthHeaders({
      method: "POST",
      pathWithQuery: "/api/enable-banking/auth",
      userId,
    });

    const resp = await fetch(url, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...signatureHeaders,
      },
      body: JSON.stringify({
        aspsp_name: aspspName,
        aspsp_country: aspspCountry,
        connection_id: connectionId,
      }),
    });

    if (!resp.ok) {
      const data = await resp.json().catch(() => ({ detail: "Auth failed" }));
      return { success: false, error: data.detail || "Auth failed" };
    }

    const data = await resp.json();
    return { success: true, url: data.url };
  } catch (e) {
    return { success: false, error: "Failed to initiate bank connection" };
  }
}

export async function getConnectionForMapping(connectionId: string) {
  const userId = await requireAuth();
  if (!userId) return null;

  const connection = await db
    .select({
      id: bankConnections.id,
      aspspName: bankConnections.aspspName,
      aspspCountry: bankConnections.aspspCountry,
      status: bankConnections.status,
      rawSessionData: bankConnections.rawSessionData,
    })
    .from(bankConnections)
    .where(
      and(
        eq(bankConnections.id, connectionId),
        eq(bankConnections.userId, userId),
        eq(bankConnections.status, "pending_setup")
      )
    )
    .then((rows) => rows[0] || null);

  return connection;
}

export async function getLinkableAccounts() {
  const userId = await requireAuth();
  if (!userId) return [];

  return db
    .select({
      id: accounts.id,
      name: accounts.name,
      currency: accounts.currency,
      accountType: accounts.accountType,
      institution: accounts.institution,
      bankConnectionId: accounts.bankConnectionId,
    })
    .from(accounts)
    .where(
      and(
        eq(accounts.userId, userId),
        isNull(accounts.bankConnectionId)
      )
    )
    .orderBy(accounts.name);
}

export async function submitAccountMappings(
  connectionId: string,
  mappings: Array<{
    bank_uid: string;
    action: "create" | "link";
    name?: string;
    existing_account_id?: string;
  }>,
  initialSyncDays: number
): Promise<{ success: boolean; error?: string }> {
  const session = await getAuthenticatedSession();
  const userId = session?.user?.id;
  if (!userId) return { success: false, error: "Not authenticated" };
  if (isDemoRestrictedUserEmail(session.user.email)) {
    return { success: false, error: DEMO_RESTRICTED_ACTION_ERROR };
  }

  try {
    const backendBase = getBackendBaseUrl().replace(/\/+$/, "");
    const pathWithQuery = `/api/enable-banking/connections/${connectionId}/map-accounts`;
    const url = `${backendBase}${pathWithQuery}`;

    const signatureHeaders = createInternalAuthHeaders({
      method: "POST",
      pathWithQuery,
      userId,
    });

    const resp = await fetch(url, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...signatureHeaders,
      },
      body: JSON.stringify({
        mappings,
        initial_sync_days: initialSyncDays,
      }),
    });

    if (!resp.ok) {
      const data = await resp.json().catch(() => ({ detail: "Mapping failed" }));
      return { success: false, error: data.detail || "Mapping failed" };
    }

    revalidatePath("/settings");
    return { success: true };
  } catch (e) {
    return { success: false, error: "Failed to submit account mappings" };
  }
}

export async function triggerRecategorize(
  connectionId: string
): Promise<{ success: boolean; error?: string }> {
  const session = await getAuthenticatedSession();
  const userId = session?.user?.id;
  if (!userId) return { success: false, error: "Not authenticated" };
  if (isDemoRestrictedUserEmail(session.user.email)) {
    return { success: false, error: DEMO_RESTRICTED_ACTION_ERROR };
  }

  try {
    const backendBase = getBackendBaseUrl().replace(/\/+$/, "");
    const pathWithQuery = `/api/enable-banking/connections/${connectionId}/recategorize`;
    const url = `${backendBase}${pathWithQuery}`;

    const signatureHeaders = createInternalAuthHeaders({
      method: "POST",
      pathWithQuery,
      userId,
    });

    const resp = await fetch(url, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...signatureHeaders,
      },
    });

    if (!resp.ok) {
      const data = await resp.json().catch(() => ({ detail: "Re-categorization failed" }));
      return { success: false, error: data.detail || "Re-categorization failed" };
    }

    return { success: true };
  } catch (e) {
    return { success: false, error: "Failed to trigger re-categorization" };
  }
}

export async function getConnectionStatus(
  connectionId: string
): Promise<{
  lastSyncedAt: string | null;
  lastSyncError: string | null;
  status: string;
} | null> {
  const session = await getAuthenticatedSession();
  const userId = session?.user?.id;
  if (!userId) return null;

  try {
    const backendBase = getBackendBaseUrl().replace(/\/+$/, "");
    const pathWithQuery = `/api/enable-banking/status/${connectionId}`;
    const url = `${backendBase}${pathWithQuery}`;

    const signatureHeaders = createInternalAuthHeaders({
      method: "GET",
      pathWithQuery,
      userId,
    });

    const resp = await fetch(url, {
      method: "GET",
      headers: signatureHeaders,
    });

    if (!resp.ok) return null;
    const data = await resp.json();
    return {
      lastSyncedAt: data.last_synced_at,
      lastSyncError: data.last_sync_error,
      status: data.status,
    };
  } catch {
    return null;
  }
}

export type SuggestedMapping = {
  bank_uid: string;
  bank_name: string;
  suggested_action: "link" | "create";
  suggested_account_id: string | null;
  suggested_account_name: string | null;
};

export async function getSuggestedMappings(
  connectionId: string
): Promise<SuggestedMapping[]> {
  const session = await getAuthenticatedSession();
  const userId = session?.user?.id;
  if (!userId) return [];

  try {
    const backendBase = getBackendBaseUrl().replace(/\/+$/, "");
    const pathWithQuery = `/api/enable-banking/connections/${connectionId}/suggested-mappings`;
    const url = `${backendBase}${pathWithQuery}`;

    const signatureHeaders = createInternalAuthHeaders({
      method: "GET",
      pathWithQuery,
      userId,
    });

    const resp = await fetch(url, {
      method: "GET",
      headers: signatureHeaders,
    });

    if (!resp.ok) {
      console.warn(`getSuggestedMappings: backend returned ${resp.status} for ${connectionId}`);
      return [];
    }
    return await resp.json();
  } catch {
    return [];
  }
}
