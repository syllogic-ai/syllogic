"use server";

import { revalidatePath } from "next/cache";
import { eq, and, desc } from "drizzle-orm";
import { db } from "@/lib/db";
import { bankConnections } from "@/lib/db/schema";
import { requireAuth } from "@/lib/auth-helpers";
import { getBackendBaseUrl } from "@/lib/backend-url";
import { createInternalAuthHeaders } from "@/lib/internal-auth";

export async function getBankConnections() {
  const userId = await requireAuth();
  if (!userId) return [];

  return db
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
    .orderBy(desc(bankConnections.createdAt));
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
  const userId = await requireAuth();
  if (!userId) return { success: false, error: "Not authenticated" };

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
  const userId = await requireAuth();
  if (!userId) return { success: false, error: "Not authenticated" };

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

export async function initiateAuth(
  aspspName: string,
  aspspCountry: string
): Promise<{ success: boolean; url?: string; error?: string }> {
  const userId = await requireAuth();
  if (!userId) return { success: false, error: "Not authenticated" };

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
