"use server";

import { revalidatePath } from "next/cache";
import { getBackendBaseUrl } from "@/lib/backend-url";
import { createInternalAuthHeaders } from "@/lib/internal-auth";
import { requireAuth } from "@/lib/auth-helpers";

interface AccountBalanceImpact {
  account_id: string;
  account_name: string;
  institution: string | null;
  currency: string;
  transactions_count: number;
  total_amount: number;
  current_balance: number;
  new_balance: number;
}

interface DeletePreviewResponse {
  success: boolean;
  total_transactions: number;
  affected_accounts: AccountBalanceImpact[];
  confirmation_required: string;
  warnings: string[];
}

interface DeleteResponse {
  success: boolean;
  message: string;
  deleted_count: number;
}

interface ImportHistoryItem {
  id: string;
  account_id: string;
  account_name: string;
  file_name: string;
  status: string;
  total_rows: number | null;
  imported_rows: number | null;
  completed_at: string | null;
  created_at: string;
  transaction_count: number;
}

interface ImportHistoryResponse {
  success: boolean;
  imports: ImportHistoryItem[];
}

interface RevertImportResponse {
  success: boolean;
  message: string;
  deleted_count: number;
}

export async function getDeleteTransactionsPreview(
  transactionIds: string[]
): Promise<{
  success: boolean;
  error?: string;
  totalTransactions?: number;
  affectedAccounts?: AccountBalanceImpact[];
  confirmationRequired?: string;
  warnings?: string[];
}> {
  const userId = await requireAuth();

  if (!userId) {
    return { success: false, error: "Not authenticated" };
  }

  try {
    const backendUrl = getBackendBaseUrl();
    const pathWithQuery = "/api/transactions/delete-preview";

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
      body: JSON.stringify({ transaction_ids: transactionIds }),
    });

    if (!response.ok) {
      const errorText = await response.text();
      console.error("Backend delete preview failed:", response.status, errorText);
      return { success: false, error: `Failed to get delete preview: ${response.status}` };
    }

    const data: DeletePreviewResponse = await response.json();

    if (!data.success) {
      return { success: false, error: "Failed to get delete preview" };
    }

    return {
      success: true,
      totalTransactions: data.total_transactions,
      affectedAccounts: data.affected_accounts,
      confirmationRequired: data.confirmation_required,
      warnings: data.warnings,
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

    const data: ImportHistoryResponse = await response.json();

    if (!data.success) {
      return { success: false, error: "Failed to get import history" };
    }

    return { success: true, imports: data.imports };
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
