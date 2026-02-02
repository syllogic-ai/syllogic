"use client";

import { useEffect, useState, useCallback, useRef } from "react";
import { toast } from "sonner";

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

export type ImportStatusEvent =
  | ImportStartedEvent
  | ImportProgressEvent
  | ImportCompletedEvent
  | ImportFailedEvent;

export interface UseImportStatusOptions {
  /** Called when import starts */
  onStarted?: (event: ImportStartedEvent) => void;
  /** Called on each progress update */
  onProgress?: (event: ImportProgressEvent) => void;
  /** Called when import completes successfully */
  onCompleted?: (event: ImportCompletedEvent) => void;
  /** Called when import fails */
  onFailed?: (event: ImportFailedEvent) => void;
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
  /** Whether the import has completed (success or failure) */
  isComplete: boolean;
  /** Error message if import failed */
  error: string | null;
  /** Result of completed import */
  result: ImportCompletedEvent | null;
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
    showToasts = true,
  } = options;

  const [progress, setProgress] = useState<number | null>(null);
  const [totalRows, setTotalRows] = useState<number | null>(null);
  const [processedRows, setProcessedRows] = useState<number | null>(null);
  const [isConnected, setIsConnected] = useState(false);
  const [isImporting, setIsImporting] = useState(false);
  const [isComplete, setIsComplete] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<ImportCompletedEvent | null>(null);

  const eventSourceRef = useRef<EventSource | null>(null);

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
      return;
    }

    // Don't reconnect if already complete
    if (isComplete) {
      return;
    }

    const backendUrl = process.env.NEXT_PUBLIC_BACKEND_URL || "http://localhost:8000";
    const url = `${backendUrl}/api/events/import-status/${userId}/${importId}`;

    const eventSource = new EventSource(url);
    eventSourceRef.current = eventSource;

    eventSource.onopen = () => {
      setIsConnected(true);
      setIsImporting(true);
    };

    eventSource.onerror = (event) => {
      console.error("SSE connection error:", event);
      // EventSource will automatically try to reconnect
      // Only set disconnected if the connection is fully closed
      if (eventSource.readyState === EventSource.CLOSED) {
        setIsConnected(false);
      }
    };

    // Handle connected event
    eventSource.addEventListener("connected", (event) => {
      console.log("SSE connected:", event.data);
    });

    // Handle import_started event
    eventSource.addEventListener("import_started", (event) => {
      try {
        const data: ImportStartedEvent = JSON.parse(event.data);
        setTotalRows(data.total_rows);
        setIsImporting(true);

        if (showToasts) {
          toast.info(`Importing ${data.total_rows} transactions...`);
        }

        onStarted?.(data);
      } catch (e) {
        console.error("Error parsing import_started event:", e);
      }
    });

    // Handle import_progress event
    eventSource.addEventListener("import_progress", (event) => {
      try {
        const data: ImportProgressEvent = JSON.parse(event.data);
        setProgress(data.percentage);
        setProcessedRows(data.processed_rows);
        setTotalRows(data.total_rows);

        onProgress?.(data);
      } catch (e) {
        console.error("Error parsing import_progress event:", e);
      }
    });

    // Handle import_completed event
    eventSource.addEventListener("import_completed", (event) => {
      try {
        const data: ImportCompletedEvent = JSON.parse(event.data);
        setIsComplete(true);
        setIsImporting(false);
        setProgress(100);
        setResult(data);

        if (showToasts) {
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

        onCompleted?.(data);

        // Close connection after completion
        eventSource.close();
      } catch (e) {
        console.error("Error parsing import_completed event:", e);
      }
    });

    // Handle import_failed event
    eventSource.addEventListener("import_failed", (event) => {
      try {
        const data: ImportFailedEvent = JSON.parse(event.data);
        setIsComplete(true);
        setIsImporting(false);
        setError(data.error);

        if (showToasts) {
          toast.error(`Import failed: ${data.error}`);
        }

        onFailed?.(data);

        // Close connection after failure
        eventSource.close();
      } catch (e) {
        console.error("Error parsing import_failed event:", e);
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
  }, [userId, importId, isComplete, showToasts, onStarted, onProgress, onCompleted, onFailed]);

  return {
    progress,
    totalRows,
    processedRows,
    isConnected,
    isImporting,
    isComplete,
    error,
    result,
    disconnect,
  };
}

/**
 * Storage key for persisting pending import ID across navigation
 */
export const PENDING_IMPORT_STORAGE_KEY = "pendingCsvImport";

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
    // Check if the import is older than 1 hour (stale)
    const ONE_HOUR = 60 * 60 * 1000;
    if (Date.now() - data.timestamp > ONE_HOUR) {
      clearPendingImport();
      return null;
    }
    return { importId: data.importId, userId: data.userId };
  } catch {
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
