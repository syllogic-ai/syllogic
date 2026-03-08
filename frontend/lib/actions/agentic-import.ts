"use server";

import { getBackendBaseUrl } from "@/lib/backend-url";
import { createInternalAuthHeaders } from "@/lib/internal-auth";
import { getAuthenticatedSession } from "@/lib/auth-helpers";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface UploadResult {
  success: boolean;
  error?: string;
  data?: {
    import_id: string;
    status: "profile_matched" | "needs_analysis";
    fingerprint: string;
    headers: string[];
    sample_rows?: string[][];
    profile_label?: string | null;
    mapping_summary?: string | null;
    transformation_description?: string | null;
    balance_column?: string | null;
    sample_transactions?: Record<string, unknown>[];
    total_rows?: number;
  };
}

export interface AnalyzeResult {
  success: boolean;
  error?: string;
  data?: {
    status: "preview_ready" | "needs_clarification" | "failed";
    question?: string;
    mapping_summary?: string;
    transformation_description?: string;
    balance_column?: string | null;
    sample_transactions?: Record<string, unknown>[];
    total_rows?: number;
    error?: string;
  };
}

export interface ApproveResult {
  success: boolean;
  error?: string;
  data?: {
    success: boolean;
    total_rows: number;
    imported: number;
    duplicates_skipped: number;
    failed_rows: { row_number: number; reason: string }[];
    balance_anchors_detected: boolean;
    error?: string;
  };
}

// ---------------------------------------------------------------------------
// Actions
// ---------------------------------------------------------------------------

export async function uploadFileForAgenticImport(
  formData: FormData
): Promise<UploadResult> {
  const session = await getAuthenticatedSession();
  if (!session?.user?.id) {
    return { success: false, error: "Not authenticated" };
  }

  try {
    const backendUrl = getBackendBaseUrl();
    const pathWithQuery = "/api/agentic-import/upload";

    formData.append("user_id", session.user.id);

    const headers = createInternalAuthHeaders({
      method: "POST",
      pathWithQuery,
      userId: session.user.id,
    });

    const response = await fetch(`${backendUrl}${pathWithQuery}`, {
      method: "POST",
      headers,
      body: formData,
    });

    if (!response.ok) {
      const text = await response.text();
      let detail = text;
      try {
        detail = JSON.parse(text).detail || text;
      } catch {}
      return { success: false, error: detail };
    }

    const data = await response.json();
    return { success: true, data };
  } catch (err) {
    console.error("Agentic import upload failed:", err);
    return { success: false, error: "Failed to upload file" };
  }
}

export async function analyzeImport(
  importId: string,
  clarificationResponse?: string
): Promise<AnalyzeResult> {
  const session = await getAuthenticatedSession();
  if (!session?.user?.id) {
    return { success: false, error: "Not authenticated" };
  }

  try {
    const backendUrl = getBackendBaseUrl();
    const pathWithQuery = "/api/agentic-import/analyze";

    const response = await fetch(`${backendUrl}${pathWithQuery}`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...createInternalAuthHeaders({
          method: "POST",
          pathWithQuery,
          userId: session.user.id,
        }),
      },
      body: JSON.stringify({
        import_id: importId,
        clarification_response: clarificationResponse || null,
      }),
    });

    if (!response.ok) {
      const text = await response.text();
      let detail = text;
      try {
        detail = JSON.parse(text).detail || text;
      } catch {}
      return { success: false, error: detail };
    }

    const data = await response.json();
    return { success: true, data };
  } catch (err) {
    console.error("Agentic import analyze failed:", err);
    return { success: false, error: "Failed to analyze file" };
  }
}

export async function approveAgenticImport(
  importId: string,
  accountId: string
): Promise<ApproveResult> {
  const session = await getAuthenticatedSession();
  if (!session?.user?.id) {
    return { success: false, error: "Not authenticated" };
  }

  try {
    const backendUrl = getBackendBaseUrl();
    const pathWithQuery = "/api/agentic-import/approve";

    const response = await fetch(`${backendUrl}${pathWithQuery}`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...createInternalAuthHeaders({
          method: "POST",
          pathWithQuery,
          userId: session.user.id,
        }),
      },
      body: JSON.stringify({
        import_id: importId,
        account_id: accountId,
      }),
    });

    if (!response.ok) {
      const text = await response.text();
      let detail = text;
      try {
        detail = JSON.parse(text).detail || text;
      } catch {}
      return { success: false, error: detail };
    }

    const data = await response.json();
    return { success: true, data };
  } catch (err) {
    console.error("Agentic import approve failed:", err);
    return { success: false, error: "Failed to approve import" };
  }
}

export async function checkOpenAiAvailable(): Promise<boolean> {
  return !!process.env.OPENAI_API_KEY;
}
