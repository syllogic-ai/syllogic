"use server";

import { revalidatePath } from "next/cache";
import { getBackendBaseUrl } from "@/lib/backend-url";
import { createInternalAuthHeaders } from "@/lib/internal-auth";
import { requireAuth } from "@/lib/auth-helpers";

export interface AccountBalanceImpact {
  account_id: string;
  account_name: string;
  currency: string;
  current_balance: number | null;
  balance_change: number;
  projected_balance: number | null;
  has_anchored_balances: boolean;
  anchored_balance_count: number;
}

interface DeletePreviewResponse {
  transaction_count: number;
  total_amount: number;
  affected_accounts: AccountBalanceImpact[];
  has_modified_transactions: boolean;
  modified_transaction_count: number;
  category_impacts: Array<{ category_id: string | null; amount: number; count: number }>;
}

interface DeleteResponse {
  success: boolean;
  deleted_count: number;
  affected_account_ids: string[];
  balance_recalculation: string;
}

export interface ImportHistoryItem {
  id: string;
  account_id: string;
  account_name: string;
  file_name: string;
  status: string;
  total_rows: number | null;
  imported_rows: number | null;
  duplicates_found: number | null;
  completed_at: string | null;
  created_at: string | null;
  transaction_count: number;
}

interface RevertImportResponse {
  success: boolean;
  deleted_count: number;
  import_id: string;
  affected_account_ids: string[];
  balance_recalculation: string;
}

export async function getDeleteTransactionsPreview(
  transactionIds: string[],
  importId?: string
): Promise<{
  success: boolean;
  error?: string;
  preview?: DeletePreviewResponse;
}> {
  const userId = await requireAuth();

  if (!userId) {
    return { success: false, error: "Not authenticated" };
  }

  try {
    const backendUrl = getBackendBaseUrl();
    const pathWithQuery = "/api/transactions/delete-preview";

    const body: Record<string, unknown> = {};
    if (importId) {
      body.import_id = importId;
    } else {
      body.transaction_ids = transactionIds;
    }

    const response = await fetch(`${backendUrl}${pathWithQuery}`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...createInternalAuthHeaders({
          method: "POST",
          pathWithQuery,
          userId,
        }),
      },
      body: JSON.stringify(body),
    });

    if (!response.ok) {
      const errorText = await response.text();
      console.error("Backend delete preview failed:", response.status, errorText);
      return { success: false, error: `Failed to get delete preview: ${response.status}` };
    }

    const data: DeletePreviewResponse = await response.json();

    return {
      success: true,
      preview: data,
    };
  } catch (error) {
    console.error("Failed to get delete transactions preview:", error);
    return { success: false, error: "Failed to get delete preview" };
  }
}

export async function deleteTransactions(
  transactionIds: string[],
  confirmation: string
): Promise<{ success: boolean; error?: string; deletedCount?: number }> {
  const userId = await requireAuth();

  if (!userId) {
    return { success: false, error: "Not authenticated" };
  }

  try {
    const backendUrl = getBackendBaseUrl();
    const pathWithQuery = "/api/transactions/delete";

    const response = await fetch(`${backendUrl}${pathWithQuery}`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...createInternalAuthHeaders({
          method: "POST",
          pathWithQuery,
          userId,
        }),
      },
      body: JSON.stringify({ transaction_ids: transactionIds, confirmation }),
    });

    if (!response.ok) {
      const errorText = await response.text();
      console.error("Backend delete failed:", response.status, errorText);
      return { success: false, error: `Failed to delete transactions: ${response.status}` };
    }

    const data: DeleteResponse = await response.json();

    if (!data.success) {
      return { success: false, error: data.message };
    }

    revalidatePath("/transactions");
    revalidatePath("/");
    revalidatePath("/settings");
    revalidatePath("/assets");

    return { success: true, deletedCount: data.deleted_count };
  } catch (error) {
    console.error("Failed to delete transactions:", error);
    return { success: false, error: "Failed to delete transactions" };
  }
}

export async function getImportHistory(): Promise<{
  success: boolean;
  error?: string;
  imports?: ImportHistoryItem[];
}> {
  const userId = await requireAuth();

  if (!userId) {
    return { success: false, error: "Not authenticated" };
  }

  try {
    const backendUrl = getBackendBaseUrl();
    const pathWithQuery = "/api/csv-import/history";

    const response = await fetch(`${backendUrl}${pathWithQuery}`, {
      method: "GET",
      headers: {
        "Content-Type": "application/json",
        ...createInternalAuthHeaders({
          method: "GET",
          pathWithQuery,
          userId,
        }),
      },
    });

    if (!response.ok) {
      const errorText = await response.text();
      console.error("Backend import history failed:", response.status, errorText);
      return { success: false, error: `Failed to get import history: ${response.status}` };
    }

    const data: ImportHistoryItem[] = await response.json();

    return { success: true, imports: data };
  } catch (error) {
    console.error("Failed to get import history:", error);
    return { success: false, error: "Failed to get import history" };
  }
}

export async function revertImport(
  importId: string,
  confirmation: string
): Promise<{ success: boolean; error?: string; deletedCount?: number }> {
  const userId = await requireAuth();

  if (!userId) {
    return { success: false, error: "Not authenticated" };
  }

  try {
    const backendUrl = getBackendBaseUrl();
    const pathWithQuery = "/api/transactions/revert-import";

    const response = await fetch(`${backendUrl}${pathWithQuery}`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...createInternalAuthHeaders({
          method: "POST",
          pathWithQuery,
          userId,
        }),
      },
      body: JSON.stringify({ import_id: importId, confirmation }),
    });

    if (!response.ok) {
      const errorText = await response.text();
      console.error("Backend revert import failed:", response.status, errorText);
      return { success: false, error: `Failed to revert import: ${response.status}` };
    }

    const data: RevertImportResponse = await response.json();

    if (!data.success) {
      return { success: false, error: data.message };
    }

    revalidatePath("/transactions");
    revalidatePath("/");
    revalidatePath("/settings");
    revalidatePath("/assets");

    return { success: true, deletedCount: data.deleted_count };
  } catch (error) {
    console.error("Failed to revert import:", error);
    return { success: false, error: "Failed to revert import" };
  }
}
