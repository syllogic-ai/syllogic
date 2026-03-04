"use client";

import { useEffect, useState, useCallback, useRef } from "react";
import { toast } from "sonner";

/** Module-level set for toast deduplication across all hook instances */
const shownToastKeys = new Set<string>();

/**
 * Import status event types from the SSE stream
 */
export interface ImportStartedEvent {
  type: "import_started";
  import_id: string;
  total_rows: number;
  timestamp: string;
}

export interface ImportProgressEvent {
  type: "import_progress";
  import_id: string;
  processed_rows: number;
  total_rows: number;
  percentage: number;
  timestamp: string;
}

export interface ImportCompletedEvent {
  type: "import_completed";
  import_id: string;
  imported_count: number;
  skipped_count: number;
  categorization_summary?: {
    total: number;
    categorized: number;
    deterministic: number;
    llm: number;
    uncategorized: number;
    tokens_used: number;
    cost_usd: number;
  };
  timestamp: string;
}

export interface ImportFailedEvent {
  type: "import_failed";
  import_id: string;
  error: string;
  timestamp: string;
}

export interface SubscriptionsStartedEvent {
  type: "subscriptions_started";
  import_id: string;
  timestamp: string;
}

export interface SubscriptionsCompletedEvent {
  type: "subscriptions_completed";
  import_id: string;
  matched_count: number;
  detected_count: number;
  timestamp: string;
}

export type ImportStatusEvent =
  | ImportStartedEvent
  | ImportProgressEvent
  | ImportCompletedEvent
  | ImportFailedEvent
  | SubscriptionsStartedEvent
  | SubscriptionsCompletedEvent;

export interface UseImportStatusOptions {
  /** Called when import starts */
  onStarted?: (event: ImportStartedEvent) => void;
  /** Called on each progress update */
  onProgress?: (event: ImportProgressEvent) => void;
  /** Called when import completes successfully */
  onCompleted?: (event: ImportCompletedEvent) => void;
  /** Called when import fails */
  onFailed?: (event: ImportFailedEvent) => void;
  /** Called when subscription processing starts */
  onSubscriptionsStarted?: (event: SubscriptionsStartedEvent) => void;
  /** Called when subscription processing completes */
  onSubscriptionsCompleted?: (event: SubscriptionsCompletedEvent) => void;
  /** Whether to show toast notifications */
  showToasts?: boolean;
}

export interface UseImportStatusResult {
  /** Current progress percentage (0-100) */
  progress: number | null;
  /** Total rows to import */
  totalRows: number | null;
  /** Number of rows processed so far */
  processedRows: number | null;
  /** Whether the SSE connection is active */
  isConnected: boolean;
  /** Whether the import is currently processing */
  isImporting: boolean;
  /** Whether subscription processing is running */
  isProcessingSubscriptions: boolean;
  /** Whether the entire flow has completed (import + subscriptions) */
  isComplete: boolean;
  /** Error message if import failed */
  error: string | null;
  /** Result of completed import */
  result: ImportCompletedEvent | null;
  /** Result of subscription processing */
  subscriptionsResult: SubscriptionsCompletedEvent | null;
  /** Manually disconnect the SSE connection */
  disconnect: () => void;
}

/**
 * Hook for subscribing to real-time CSV import status updates via SSE.
 *
 * @param userId - The user ID (required to start connection)
 * @param importId - The CSV import ID (required to start connection)
 * @param options - Callback options
 *
 * @example
 * ```tsx
 * const { progress, isImporting, result } = useImportStatus(
 *   session?.user?.id,
 *   pendingImportId,
 *   {
 *     onCompleted: (event) => {
 *       router.refresh();
 *     },
 *     showToasts: true,
 *   }
 * );
 *
 * if (isImporting && progress !== null) {
 *   return <ProgressBanner progress={progress} />;
 * }
 * ```
 */
export function useImportStatus(
  userId: string | null | undefined,
  importId: string | null | undefined,
  options: UseImportStatusOptions = {}
): UseImportStatusResult {
  const {
    onStarted,
    onProgress,
    onCompleted,
    onFailed,
    onSubscriptionsStarted,
    onSubscriptionsCompleted,
    showToasts = true,
  } = options;

  const [progress, setProgress] = useState<number | null>(null);
  const [totalRows, setTotalRows] = useState<number | null>(null);
  const [processedRows, setProcessedRows] = useState<number | null>(null);
  const [isConnected, setIsConnected] = useState(false);
  const [isImporting, setIsImporting] = useState(false);
  const [isProcessingSubscriptions, setIsProcessingSubscriptions] = useState(false);
  const [isComplete, setIsComplete] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<ImportCompletedEvent | null>(null);
  const [subscriptionsResult, setSubscriptionsResult] = useState<SubscriptionsCompletedEvent | null>(null);

  const eventSourceRef = useRef<EventSource | null>(null);

  // Store callbacks in refs to avoid effect re-runs (which would close/reopen SSE connection)
  const onStartedRef = useRef(onStarted);
  const onProgressRef = useRef(onProgress);
  const onCompletedRef = useRef(onCompleted);
  const onFailedRef = useRef(onFailed);
  const onSubscriptionsStartedRef = useRef(onSubscriptionsStarted);
  const onSubscriptionsCompletedRef = useRef(onSubscriptionsCompleted);
  onStartedRef.current = onStarted;
  onProgressRef.current = onProgress;
  onCompletedRef.current = onCompleted;
  onFailedRef.current = onFailed;
  onSubscriptionsStartedRef.current = onSubscriptionsStarted;
  onSubscriptionsCompletedRef.current = onSubscriptionsCompleted;

  const disconnect = useCallback(() => {
    if (eventSourceRef.current) {
      eventSourceRef.current.close();
      eventSourceRef.current = null;
      setIsConnected(false);
    }
  }, []);

  useEffect(() => {
    // Don't connect if missing required params
    if (!userId || !importId) {
      setIsConnected(false);
      setIsImporting(false);
      setIsProcessingSubscriptions(false);
      setIsComplete(false);
      setProgress(null);
      setTotalRows(null);
      setProcessedRows(null);
      setError(null);
      setResult(null);
      setSubscriptionsResult(null);
      return;
    }

    // Don't reconnect if already complete
    if (isComplete) {
      return;
    }

    // Don't create a new connection if one already exists for this import
    if (eventSourceRef.current && eventSourceRef.current.readyState !== EventSource.CLOSED) {
      return;
    }

    const url = `/api/events/import-status/${importId}`;

    const eventSource = new EventSource(url);
    eventSourceRef.current = eventSource;

    eventSource.onopen = () => {
      setIsConnected(true);
    };

    eventSource.onerror = (e) => {
      if (eventSource.readyState === EventSource.CLOSED) {
        setIsConnected(false);
      }
    };

    // Helper to deduplicate toasts across all hook instances (shared module-level set)
    const shouldShowToast = (eventType: string, data: { import_id: string; timestamp?: string }) => {
      const key = `${data.import_id}:${eventType}:${data.timestamp ?? ""}`;
      if (shownToastKeys.has(key)) return false;
      shownToastKeys.add(key);
      return true;
    };

    // Handle import_started event
    eventSource.addEventListener("import_started", (event) => {
      try {
        const data: ImportStartedEvent = JSON.parse(event.data);
        setTotalRows(data.total_rows);
        setIsImporting(true);

        if (showToasts && shouldShowToast("import_started", data)) {
          toast.info(`Importing ${data.total_rows} transactions...`);
        }

        onStartedRef.current?.(data);
      } catch (e) {
        console.error("[useImportStatus] Error parsing import_started event:", e);
      }
    });

    // Handle import_progress event
    eventSource.addEventListener("import_progress", (event) => {
      try {
        const data: ImportProgressEvent = JSON.parse(event.data);
        setProgress(data.percentage);
        setProcessedRows(data.processed_rows);
        setTotalRows(data.total_rows);

        onProgressRef.current?.(data);
      } catch {
        // Error parsing import_progress event - fail silently
      }
    });

    // Handle import_completed event
    eventSource.addEventListener("import_completed", (event) => {
      try {
        const data: ImportCompletedEvent = JSON.parse(event.data);
        // Don't set isComplete yet - wait for subscriptions to finish
        setIsImporting(false);
        setProgress(100);
        setResult(data);

        if (showToasts && shouldShowToast("import_completed", data)) {
          toast.success(
            `Successfully imported ${data.imported_count} transactions`,
            {
              description: data.skipped_count > 0
                ? `${data.skipped_count} duplicates skipped`
                : undefined,
              action: {
                label: "View",
                onClick: () => window.scrollTo(0, 0),
              },
            }
          );
        }

        onCompletedRef.current?.(data);

        // Keep connection open for subscription events
      } catch (e) {
        console.error("[useImportStatus] Error parsing import_completed event:", e);
      }
    });

    // Handle import_failed event
    eventSource.addEventListener("import_failed", (event) => {
      try {
        const data: ImportFailedEvent = JSON.parse(event.data);
        setIsComplete(true);
        setIsImporting(false);
        setError(data.error);

        if (showToasts && shouldShowToast("import_failed", data)) {
          toast.error(`Import failed: ${data.error}`);
        }

        onFailedRef.current?.(data);

        // Close connection after failure
        eventSource.close();
      } catch (e) {
        console.error("[useImportStatus] Error parsing import_failed event:", e);
      }
    });

    // Handle subscriptions_started event
    eventSource.addEventListener("subscriptions_started", (event) => {
      try {
        const data: SubscriptionsStartedEvent = JSON.parse(event.data);
        setIsProcessingSubscriptions(true);
        // No toast - subscription processing is silent
        onSubscriptionsStartedRef.current?.(data);
      } catch (e) {
        console.error("[useImportStatus] Error parsing subscriptions_started event:", e);
      }
    });

    // Handle subscriptions_completed event
    eventSource.addEventListener("subscriptions_completed", (event) => {
      try {
        const data: SubscriptionsCompletedEvent = JSON.parse(event.data);
        setIsProcessingSubscriptions(false);
        setIsComplete(true);
        setSubscriptionsResult(data);

        if (showToasts && shouldShowToast("subscriptions_completed", data)) {
          const hasResults = data.matched_count > 0 || data.detected_count > 0;

          if (hasResults) {
            const parts: string[] = [];
            if (data.matched_count > 0) {
              parts.push(`${data.matched_count} matched`);
            }
            if (data.detected_count > 0) {
              parts.push(`${data.detected_count} new detected`);
            }

            toast.success("Subscription detection complete", {
              description: parts.join(", "),
              action: {
                label: "View",
                onClick: () => {
                  window.location.href = "/subscriptions";
                },
              },
            });
          } else {
            toast.info("Subscription detection complete", {
              description: "No new subscriptions found",
            });
          }
        }

        onSubscriptionsCompletedRef.current?.(data);

        // Close connection after subscriptions complete
        eventSource.close();
      } catch (e) {
        console.error("[useImportStatus] Error parsing subscriptions_completed event:", e);
      }
    });

    // Handle heartbeat (keep-alive)
    eventSource.addEventListener("heartbeat", () => {
      // Just acknowledge heartbeat, no action needed
    });

    // Cleanup on unmount or when dependencies change
    return () => {
      eventSource.close();
      eventSourceRef.current = null;
    };
  }, [userId, importId, isComplete, showToasts]);

  return {
    progress,
    totalRows,
    processedRows,
    isConnected,
    isImporting,
    isProcessingSubscriptions,
    isComplete,
    error,
    result,
    subscriptionsResult,
    disconnect,
  };
}

/**
 * Storage key for persisting pending import ID across navigation
 */
export const PENDING_IMPORT_STORAGE_KEY = "pendingCsvImport";
const PENDING_IMPORT_MAX_AGE_MS = 20 * 60 * 1000;

/**
 * Store a pending import ID in sessionStorage
 */
export function setPendingImport(importId: string, userId: string): void {
  if (typeof window !== "undefined") {
    sessionStorage.setItem(PENDING_IMPORT_STORAGE_KEY, JSON.stringify({
      importId,
      userId,
      timestamp: Date.now(),
    }));
  }
}

/**
 * Get pending import from sessionStorage
 */
export function getPendingImport(): { importId: string; userId: string } | null {
  if (typeof window === "undefined") {
    return null;
  }

  const stored = sessionStorage.getItem(PENDING_IMPORT_STORAGE_KEY);
  if (!stored) {
    return null;
  }

  try {
    const data = JSON.parse(stored);
    // Clear stale pending imports to avoid indefinite "importing" UI state.
    if (Date.now() - data.timestamp > PENDING_IMPORT_MAX_AGE_MS) {
      clearPendingImport();
      return null;
    }
    return { importId: data.importId, userId: data.userId };
  } catch {
    clearPendingImport();
    return null;
  }
}

/**
 * Clear pending import from sessionStorage
 */
export function clearPendingImport(): void {
  if (typeof window !== "undefined") {
    sessionStorage.removeItem(PENDING_IMPORT_STORAGE_KEY);
  }
}
