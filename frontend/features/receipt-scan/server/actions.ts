"use server";

import { logger } from "@/lib/logger";
import { and, eq } from "drizzle-orm";
import { db } from "@/lib/db";
import { accounts } from "@/lib/db/schema";
import { getAuthenticatedSession } from "@/lib/auth-helpers";
import {
  isDemoRestrictedUserEmail,
  DEMO_RESTRICTED_ACTION_ERROR,
} from "@/lib/demo-access";
import { getBackendBaseUrl } from "@/lib/backend-url";
import { createInternalAuthHeaders } from "@/lib/internal-auth";
import type {
  ReceiptGroup,
  ReceiptGroupPreview,
  ReceiptLineCorrections,
  ReceiptLineItem,
  ReceiptScanResult,
  ReceiptScanStatus,
  ReceiptValidationError,
} from "../domain/contracts";

const MAX_UPLOAD_BYTES = 10 * 1024 * 1024;

interface BackendReceiptLineItem {
  line_ref: string | null;
  description: string | null;
  amount: string | number | null;
  category_id: string | null;
  category_name: string | null;
  category_confidence: string | null;
  category_reason: string | null;
  user_edited: boolean | null;
}

interface BackendValidationError {
  code: string;
  message: string;
  line_refs: string[];
}

interface BackendExtractResponse {
  receipt_scan_id: string;
  status: string;
  merchant_name: string | null;
  receipt_total: string | number | null;
  currency: string | null;
  items: BackendReceiptLineItem[];
  validation_errors: BackendValidationError[];
  error_message: string | null;
}

interface BackendResolvedGroup {
  category_id: string | null;
  category_name: string | null;
  amount: string | number;
  line_refs: string[];
}

interface BackendResolvePreviewResponse {
  uncollapsed: BackendResolvedGroup[];
  resolved: BackendResolvedGroup[];
}

interface BackendTransaction {
  id: string;
  [key: string]: unknown;
}

interface BackendConfirmResponse {
  transactions: BackendTransaction[];
  already_booked: boolean;
}

function toReceiptLineItem(
  item: BackendReceiptLineItem,
  index: number,
): ReceiptLineItem {
  return {
    key: `${index}-${item.line_ref ?? item.description ?? index}`,
    lineRef: item.line_ref,
    description: item.description ?? "",
    amount: item.amount === null ? "" : String(item.amount),
    categoryId: item.category_id,
    categoryName: item.category_name,
    categoryConfidence: item.category_confidence,
    categoryReason: item.category_reason,
    userEdited: Boolean(item.user_edited),
    transactionType: "debit",
  };
}

function toReceiptValidationError(
  error: BackendValidationError,
): ReceiptValidationError {
  return {
    code: error.code,
    message: error.message,
    lineRefs: error.line_refs ?? [],
  };
}

function toReceiptGroup(group: BackendResolvedGroup): ReceiptGroup {
  return {
    categoryId: group.category_id,
    categoryName: group.category_name,
    amount: String(group.amount),
    lineRefs: group.line_refs ?? [],
  };
}

function toReceiptScanResult(backendResponse: BackendExtractResponse): ReceiptScanResult {
  return {
    receiptScanId: backendResponse.receipt_scan_id,
    status: backendResponse.status as ReceiptScanStatus,
    merchantName: backendResponse.merchant_name,
    receiptTotal:
      backendResponse.receipt_total === null
        ? null
        : String(backendResponse.receipt_total),
    currency: backendResponse.currency,
    items: backendResponse.items.map(toReceiptLineItem),
    validationErrors: (backendResponse.validation_errors ?? []).map(
      toReceiptValidationError,
    ),
    errorMessage: backendResponse.error_message,
  };
}

async function getReceiptScanAccess() {
  const session = await getAuthenticatedSession();
  if (!session) {
    return { error: "Not authenticated" } as const;
  }
  if (isDemoRestrictedUserEmail(session.user.email)) {
    return { error: DEMO_RESTRICTED_ACTION_ERROR } as const;
  }
  return { session } as const;
}

export async function uploadAndExtractReceipt(
  accountId: string,
  fileBuffer: ArrayBuffer,
  contentType: string,
): Promise<{ success: boolean; error?: string; result?: ReceiptScanResult }> {
  const access = await getReceiptScanAccess();
  if ("error" in access) {
    return { success: false, error: access.error };
  }
  const { session } = access;

  const account = await db.query.accounts.findFirst({
    where: and(
      eq(accounts.id, accountId),
      eq(accounts.userId, session.user.id),
    ),
  });
  if (!account) {
    return { success: false, error: "Account not found" };
  }

  const imageBuffer = Buffer.from(fileBuffer);
  if (imageBuffer.length === 0 || imageBuffer.length > MAX_UPLOAD_BYTES) {
    return { success: false, error: "Receipt image is too large or empty" };
  }

  try {
    // The backend is the storage owner for receipt blobs: it OCRs and
    // persists the bytes sent in this request body directly (see
    // docs/specs/receipt-ingestion.md Part 4.2). Metadata travels in the
    // query string, not JSON/base64 -- the internal-auth middleware already
    // buffers and signs the whole body, so base64-in-JSON would only add a
    // second buffering pass and ~33% size inflation for nothing, and the
    // query string is already covered by that same signature.
    const backendUrl = getBackendBaseUrl();
    const pathWithQuery =
      `/api/receipt-scan/extract?account_id=${encodeURIComponent(accountId)}` +
      `&content_type=${encodeURIComponent(contentType)}`;

    const response = await fetch(`${backendUrl}${pathWithQuery}`, {
      method: "POST",
      headers: {
        "Content-Type": "application/octet-stream",
        ...createInternalAuthHeaders({
          method: "POST",
          pathWithQuery,
          userId: session.user.id,
          body: imageBuffer,
        }),
      },
      body: imageBuffer,
    });

    if (!response.ok) {
      const errorText = await response.text();
      logger.error("Receipt scan extract failed", { status: response.status, body: errorText });
      return { success: false, error: "Failed to process receipt" };
    }

    const backendResponse: BackendExtractResponse = await response.json();

    return { success: true, result: toReceiptScanResult(backendResponse) };
  } catch (error) {
    logger.error("Failed to extract receipt", { error });
    return { success: false, error: "Failed to process receipt" };
  }
}

/**
 * Polls the status of a previously-enqueued extraction. `uploadAndExtractReceipt`
 * only ever returns `status: "pending"` (the POST enqueues and returns
 * immediately -- spec 4.4); the caller (`useReceiptScanController`) calls
 * this on an interval until the scan leaves `pending`.
 */
export async function getReceiptScanStatus(
  receiptScanId: string,
): Promise<{ success: boolean; error?: string; result?: ReceiptScanResult }> {
  const access = await getReceiptScanAccess();
  if ("error" in access) {
    return { success: false, error: access.error };
  }
  const { session } = access;

  try {
    const backendUrl = getBackendBaseUrl();
    const pathWithQuery = `/api/receipt-scan/${receiptScanId}`;

    const response = await fetch(`${backendUrl}${pathWithQuery}`, {
      method: "GET",
      headers: createInternalAuthHeaders({
        method: "GET",
        pathWithQuery,
        userId: session.user.id,
      }),
    });

    if (!response.ok) {
      const errorText = await response.text();
      logger.error("Receipt scan status fetch failed", {
        status: response.status,
        body: errorText,
      });
      return { success: false, error: "Failed to check receipt status" };
    }

    const backendResponse: BackendExtractResponse = await response.json();
    return { success: true, result: toReceiptScanResult(backendResponse) };
  } catch (error) {
    logger.error("Failed to fetch receipt scan status", { error });
    return { success: false, error: "Failed to check receipt status" };
  }
}

/**
 * Stateless preview of stage 3 (backend `receipt_resolve.resolve`, spec
 * 6.1): given the user's in-progress per-line category edits (`overrides`,
 * for lines not yet saved), returns both the raw per-category grouping and
 * the policy-applied (collapsed) grouping confirm would actually book.
 * Never books anything. The grouping/collapse policy is never
 * reimplemented here -- this always reflects what the backend computed.
 */
export async function previewReceiptScanGroups(
  receiptScanId: string,
  overrides: Array<{ lineRef: string; categoryId: string | null }>,
): Promise<{ success: boolean; error?: string; preview?: ReceiptGroupPreview }> {
  const access = await getReceiptScanAccess();
  if ("error" in access) {
    return { success: false, error: access.error };
  }
  const { session } = access;

  try {
    const backendUrl = getBackendBaseUrl();
    const pathWithQuery = `/api/receipt-scan/${receiptScanId}/resolve`;
    const requestBody = JSON.stringify({
      overrides: overrides.map((o) => ({
        line_ref: o.lineRef,
        category_id: o.categoryId,
      })),
    });

    const response = await fetch(`${backendUrl}${pathWithQuery}`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...createInternalAuthHeaders({
          method: "POST",
          pathWithQuery,
          userId: session.user.id,
          body: requestBody,
        }),
      },
      body: requestBody,
    });

    if (!response.ok) {
      const errorText = await response.text();
      logger.error("Receipt scan resolve preview failed", {
        status: response.status,
        body: errorText,
      });
      return { success: false, error: "Failed to compute how this receipt will be booked" };
    }

    const backendResponse: BackendResolvePreviewResponse = await response.json();
    return {
      success: true,
      preview: {
        uncollapsed: backendResponse.uncollapsed.map(toReceiptGroup),
        resolved: backendResponse.resolved.map(toReceiptGroup),
      },
    };
  } catch (error) {
    logger.error("Failed to preview receipt scan resolve", { error });
    return { success: false, error: "Failed to compute how this receipt will be booked" };
  }
}

/**
 * Phase 6.5: the only way to correct a `needs_review` scan (spec 1.2's whole
 * point -- refusing to book a misread receipt is only better than booking it
 * silently if correcting it is actually possible). The backend re-runs
 * `receipt_validate.validate()` on the corrected set and flips `status`
 * both ways rather than trusting this payload's arithmetic, so the returned
 * `ReceiptScanResult` -- not this function's input -- is the source of
 * truth for what actually got applied (including server-assigned
 * `lineRef`s for any inserted line).
 */
export async function correctReceiptScanLines(
  receiptScanId: string,
  corrections: ReceiptLineCorrections,
): Promise<{ success: boolean; error?: string; result?: ReceiptScanResult }> {
  const access = await getReceiptScanAccess();
  if ("error" in access) {
    return { success: false, error: access.error };
  }
  const { session } = access;

  if (
    corrections.edits.length === 0 &&
    corrections.inserts.length === 0 &&
    corrections.deletes.length === 0
  ) {
    return { success: false, error: "No corrections to apply" };
  }

  try {
    const backendUrl = getBackendBaseUrl();
    const pathWithQuery = `/api/receipt-scan/${receiptScanId}/lines`;
    const requestBody = JSON.stringify({
      edits: corrections.edits.map((edit) => ({
        line_ref: edit.lineRef,
        ...(edit.name !== undefined ? { name: edit.name } : {}),
        ...(edit.netAmount !== undefined ? { net_amount: edit.netAmount } : {}),
      })),
      inserts: corrections.inserts.map((insert) => ({
        name: insert.name,
        net_amount: insert.netAmount,
      })),
      deletes: corrections.deletes,
    });

    const response = await fetch(`${backendUrl}${pathWithQuery}`, {
      method: "PATCH",
      headers: {
        "Content-Type": "application/json",
        ...createInternalAuthHeaders({
          method: "PATCH",
          pathWithQuery,
          userId: session.user.id,
          body: requestBody,
        }),
      },
      body: requestBody,
    });

    if (response.status === 409) {
      return {
        success: false,
        error: "This receipt has already been booked and can no longer be edited",
      };
    }

    if (!response.ok) {
      const errorText = await response.text();
      logger.error("Receipt scan line correction failed", {
        status: response.status,
        body: errorText,
      });
      return { success: false, error: "Failed to save your corrections" };
    }

    const backendResponse: BackendExtractResponse = await response.json();
    return { success: true, result: toReceiptScanResult(backendResponse) };
  } catch (error) {
    logger.error("Failed to correct receipt scan lines", { error });
    return { success: false, error: "Failed to save your corrections" };
  }
}

/**
 * Books the receipt -- one Transaction per resolved category group, not per
 * line (spec 6.2). `groups` must be exactly what the last `/resolve`
 * preview returned as `resolved`: the server re-runs `resolve` itself and
 * rejects (409) a submission that doesn't match, so this is never trusted
 * client-side math.
 */
export async function confirmReceiptScan(
  receiptScanId: string,
  groups: ReceiptGroup[],
  bookedAt?: string,
): Promise<{
  success: boolean;
  error?: string;
  transactionCount?: number;
  alreadyBooked?: boolean;
}> {
  const access = await getReceiptScanAccess();
  if ("error" in access) {
    return { success: false, error: access.error };
  }
  const { session } = access;

  if (groups.length === 0) {
    return { success: false, error: "No groups to import" };
  }

  try {
    const backendUrl = getBackendBaseUrl();
    const pathWithQuery = `/api/receipt-scan/${receiptScanId}/confirm`;
    const requestBody = JSON.stringify({
      groups: groups.map((group) => ({
        category_id: group.categoryId,
        amount: group.amount,
        description: group.categoryName ?? "Receipt",
        line_refs: group.lineRefs,
        transaction_type: "debit",
      })),
      ...(bookedAt ? { booked_at: bookedAt } : {}),
    });

    const response = await fetch(`${backendUrl}${pathWithQuery}`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...createInternalAuthHeaders({
          method: "POST",
          pathWithQuery,
          userId: session.user.id,
          body: requestBody,
        }),
      },
      body: requestBody,
    });

    if (response.status === 409) {
      logger.error("Receipt scan confirm rejected: grouping changed server-side", {
        receiptScanId,
      });
      return {
        success: false,
        error: "How this receipt should be booked just changed -- please re-review and try again",
      };
    }

    if (!response.ok) {
      const errorText = await response.text();
      logger.error("Receipt scan confirm failed", { status: response.status, body: errorText });
      return { success: false, error: "Failed to save transactions" };
    }

    const created: BackendConfirmResponse = await response.json();
    return {
      success: true,
      transactionCount: created.transactions.length,
      alreadyBooked: created.already_booked,
    };
  } catch (error) {
    logger.error("Failed to confirm receipt scan", { error });
    return { success: false, error: "Failed to save transactions" };
  }
}
