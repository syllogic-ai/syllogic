"use client";

import { useState, useEffect, useRef, useCallback } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { Button, buttonVariants } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import {
  RiBankLine,
  RiRefreshLine,
  RiLinkUnlinkM,
  RiAddLine,
  RiAlertLine,
  RiPriceTag3Line,
} from "@remixicon/react";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/components/ui/alert-dialog";
import { triggerSync, disconnectBank, triggerRecategorize } from "@/lib/actions/bank-connections";
type BankConnectionItem = {
  id: string;
  aspspName: string;
  aspspCountry: string;
  status: string;
  lastSyncedAt: Date | null;
  lastSyncError: string | null;
  consentExpiresAt: Date | null;
  createdAt: Date | null;
};

interface BankConnectionsManagerProps {
  connections: BankConnectionItem[];
}

type SyncProgress = {
  stage: string;
  accounts_done: number;
  accounts_total: number;
  transactions_created: number;
  transactions_updated: number;
  started_at?: string;
};

export function BankConnectionsManager({ connections }: BankConnectionsManagerProps) {
  const router = useRouter();
  const [syncingIds, setSyncingIds] = useState<Set<string>>(new Set());
  const [recategorizingIds, setRecategorizingIds] = useState<Set<string>>(new Set());
  const [disconnectingIds, setDisconnectingIds] = useState<Set<string>>(new Set());
  const [pollingIds, setPollingIds] = useState<Set<string>>(new Set());
  const [syncProgress, setSyncProgress] = useState<Map<string, SyncProgress>>(new Map());
  const [elapsedSeconds, setElapsedSeconds] = useState<Map<string, number>>(new Map());
  const pollingTimers = useRef<Map<string, NodeJS.Timeout>>(new Map());
  const elapsedTimers = useRef<Map<string, NodeJS.Timeout>>(new Map());
  const initialSyncTimes = useRef<Map<string, string | null>>(new Map());

  // Cleanup all timers on unmount
  useEffect(() => {
    return () => {
      pollingTimers.current.forEach((timer) => clearTimeout(timer));
      elapsedTimers.current.forEach((timer) => clearInterval(timer));
    };
  }, []);

  const stopPolling = useCallback((connectionId: string) => {
    const timer = pollingTimers.current.get(connectionId);
    if (timer) {
      clearTimeout(timer);
      pollingTimers.current.delete(connectionId);
    }
    const elapsedTimer = elapsedTimers.current.get(connectionId);
    if (elapsedTimer) {
      clearInterval(elapsedTimer);
      elapsedTimers.current.delete(connectionId);
    }
    setPollingIds((prev) => {
      const next = new Set(prev);
      next.delete(connectionId);
      return next;
    });
    setSyncingIds((prev) => {
      const next = new Set(prev);
      next.delete(connectionId);
      return next;
    });
    setSyncProgress((prev) => {
      const next = new Map(prev);
      next.delete(connectionId);
      return next;
    });
    setElapsedSeconds((prev) => {
      const next = new Map(prev);
      next.delete(connectionId);
      return next;
    });
  }, []);

  const startPolling = useCallback(
    (connectionId: string, currentLastSyncedAt: string | null) => {
      initialSyncTimes.current.set(connectionId, currentLastSyncedAt);
      setPollingIds((prev) => new Set([...prev, connectionId]));

      // Start elapsed seconds ticker (clear any stale one first)
      const existingElapsed = elapsedTimers.current.get(connectionId);
      if (existingElapsed) clearInterval(existingElapsed);
      setElapsedSeconds((prev) => new Map(prev).set(connectionId, 0));
      const elapsedInterval = setInterval(() => {
        setElapsedSeconds((prev) => {
          const next = new Map(prev);
          next.set(connectionId, (next.get(connectionId) ?? 0) + 1);
          return next;
        });
      }, 1000);
      elapsedTimers.current.set(connectionId, elapsedInterval);

      let elapsed = 0;
      const poll = async () => {
        elapsed += 3000;
        if (elapsed > 600000) {
          stopPolling(connectionId);
          return;
        }

        try {
          const resp = await fetch(`/api/enable-banking/status/${connectionId}`);
          if (!resp.ok) throw new Error(`Status ${resp.status}`);
          const data = await resp.json();

          if (data.sync_progress) {
            setSyncProgress((prev) => new Map(prev).set(connectionId, data.sync_progress));
          }

          const startedAt = initialSyncTimes.current.get(connectionId);
          if (data.last_synced_at && data.last_synced_at !== startedAt) {
            stopPolling(connectionId);
            router.refresh();
            return;
          }

          if (data.last_sync_error) {
            stopPolling(connectionId);
            router.refresh();
            return;
          }
        } catch {
          // Network error, keep polling
        }

        const timer = setTimeout(poll, 3000);
        pollingTimers.current.set(connectionId, timer);
      };

      const timer = setTimeout(poll, 3000);
      pollingTimers.current.set(connectionId, timer);
    },
    [router, stopPolling]
  );

  // Auto-detect connections that are active but have never synced (initial sync after wizard)
  useEffect(() => {
    for (const conn of connections) {
      if (conn.status === "active" && !conn.lastSyncedAt && !pollingIds.has(conn.id)) {
        startPolling(conn.id, null);
        setSyncingIds((prev) => new Set([...prev, conn.id]));
      }
    }
  }, [connections, pollingIds, startPolling]);

  const handleSync = async (connectionId: string) => {
    setSyncingIds((prev) => new Set(prev).add(connectionId));

    const conn = connections.find((c) => c.id === connectionId);
    const currentLastSyncedAt = conn?.lastSyncedAt?.toISOString() || null;

    try {
      const result = await triggerSync(connectionId);
      if (!result.success) {
        console.error("Sync failed:", result.error);
        setSyncingIds((prev) => {
          const next = new Set(prev);
          next.delete(connectionId);
          return next;
        });
        return;
      }
      startPolling(connectionId, currentLastSyncedAt);
    } catch {
      setSyncingIds((prev) => {
        const next = new Set(prev);
        next.delete(connectionId);
        return next;
      });
    }
  };

  const handleRecategorize = async (connectionId: string) => {
    setRecategorizingIds((prev) => new Set(prev).add(connectionId));
    try {
      const result = await triggerRecategorize(connectionId);
      if (!result.success) {
        console.error("Re-categorization failed:", result.error);
      }
    } finally {
      setRecategorizingIds((prev) => {
        const next = new Set(prev);
        next.delete(connectionId);
        return next;
      });
    }
  };

  const handleDisconnect = async (connectionId: string) => {
    setDisconnectingIds((prev) => new Set(prev).add(connectionId));
    try {
      const result = await disconnectBank(connectionId);
      if (!result.success) {
        console.error("Disconnect failed:", result.error);
      }
      router.refresh();
    } finally {
      setDisconnectingIds((prev) => {
        const next = new Set(prev);
        next.delete(connectionId);
        return next;
      });
    }
  };

  const getStatusBadge = (connection: BankConnectionItem) => {
    switch (connection.status) {
      case "active":
        return <Badge variant="default">Active</Badge>;
      case "expired":
        return <Badge variant="destructive">Expired</Badge>;
      case "error":
        return <Badge variant="destructive">Error</Badge>;
      case "disconnected":
        return <Badge variant="secondary">Disconnected</Badge>;
      default:
        return <Badge variant="secondary">{connection.status}</Badge>;
    }
  };

  const isConsentExpiringSoon = (connection: BankConnectionItem) => {
    if (!connection.consentExpiresAt) return false;
    const daysUntilExpiry = Math.ceil(
      (new Date(connection.consentExpiresAt).getTime() - Date.now()) / (1000 * 60 * 60 * 24)
    );
    return daysUntilExpiry <= 14 && daysUntilExpiry > 0;
  };

  const daysUntilExpiry = (connection: BankConnectionItem) => {
    if (!connection.consentExpiresAt) return null;
    return Math.ceil(
      (new Date(connection.consentExpiresAt).getTime() - Date.now()) / (1000 * 60 * 60 * 24)
    );
  };

  const activeConnections = connections.filter((c) => c.status !== "disconnected");

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold">Bank Connections</h2>
          <p className="text-sm text-muted-foreground">
            Connect your bank accounts via Open Banking to automatically sync transactions.
          </p>
        </div>
        <Link
          href="/settings/connect-bank"
          className={buttonVariants({ variant: "default", size: "default" })}
        >
          <RiAddLine className="mr-1.5 h-4 w-4" />
          Connect Bank
        </Link>
      </div>

      {activeConnections.length === 0 ? (
        <div className="rounded-lg border border-dashed p-8 text-center">
          <RiBankLine className="mx-auto mb-3 h-8 w-8 text-muted-foreground" />
          <p className="text-sm text-muted-foreground">
            No bank connections yet. Connect a bank to start syncing transactions automatically.
          </p>
        </div>
      ) : (
        <div className="space-y-3">
          {activeConnections.map((connection) => (
            <div
              key={connection.id}
              className="rounded-lg border p-4"
            >
              <div className="flex items-center justify-between">
              <div className="flex items-center gap-3">
                <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-muted">
                  <RiBankLine className="h-5 w-5" />
                </div>
                <div>
                  <div className="flex items-center gap-2">
                    <span className="font-medium">{connection.aspspName}</span>
                    {getStatusBadge(connection)}
                  </div>
                  <div className="flex items-center gap-2 text-xs text-muted-foreground">
                    <span>{connection.aspspCountry}</span>
                    {connection.lastSyncedAt && (
                      <>
                        <span>·</span>
                        <span>
                          Last synced:{" "}
                          {new Date(connection.lastSyncedAt).toLocaleDateString()}
                        </span>
                      </>
                    )}
                  </div>
                  {isConsentExpiringSoon(connection) && (
                    <div className="mt-1 flex items-center gap-1 text-xs text-amber-600">
                      <RiAlertLine className="h-3 w-3" />
                      <span>
                        Connection expires in {daysUntilExpiry(connection)} days.{" "}
                        <Link
                          href="/settings/connect-bank"
                          className="underline"
                        >
                          Reconnect
                        </Link>
                      </span>
                    </div>
                  )}
                  {connection.status === "expired" && (
                    <div className="mt-1 flex items-center gap-1 text-xs text-destructive">
                      <RiAlertLine className="h-3 w-3" />
                      <span>
                        Connection expired.{" "}
                        <Link
                          href="/settings/connect-bank"
                          className="underline"
                        >
                          Reconnect
                        </Link>
                      </span>
                    </div>
                  )}
                  {connection.lastSyncError && connection.status === "error" && (
                    <p className="mt-1 text-xs text-destructive">
                      {connection.lastSyncError}
                    </p>
                  )}
                </div>
              </div>
              <div className="flex items-center gap-2">
                {connection.status === "active" && (
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => handleSync(connection.id)}
                    disabled={syncingIds.has(connection.id)}
                  >
                    <RiRefreshLine
                      className={`mr-1.5 h-4 w-4 ${
                        syncingIds.has(connection.id) ? "animate-spin" : ""
                      }`}
                    />
                    {syncingIds.has(connection.id) ? "Syncing..." : "Sync Now"}
                  </Button>
                )}
                {connection.status === "active" && (
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => handleRecategorize(connection.id)}
                    disabled={recategorizingIds.has(connection.id)}
                  >
                    <RiPriceTag3Line
                      className={`mr-1.5 h-4 w-4 ${
                        recategorizingIds.has(connection.id) ? "animate-spin" : ""
                      }`}
                    />
                    {recategorizingIds.has(connection.id) ? "Re-categorizing..." : "Fix Categories"}
                  </Button>
                )}
                <AlertDialog>
                  <AlertDialogTrigger
                    disabled={disconnectingIds.has(connection.id)}
                    render={
                      <Button
                        variant="outline"
                        size="sm"
                        disabled={disconnectingIds.has(connection.id)}
                      >
                        <RiLinkUnlinkM className="mr-1.5 h-4 w-4" />
                        Disconnect
                      </Button>
                    }
                  />
                  <AlertDialogContent>
                    <AlertDialogHeader>
                      <AlertDialogTitle>Disconnect {connection.aspspName}?</AlertDialogTitle>
                      <AlertDialogDescription>
                        This will revoke access to your bank data. Your existing
                        transactions will be kept, but no new data will be synced.
                      </AlertDialogDescription>
                    </AlertDialogHeader>
                    <AlertDialogFooter>
                      <AlertDialogCancel>Cancel</AlertDialogCancel>
                      <AlertDialogAction
                        onClick={() => handleDisconnect(connection.id)}
                      >
                        Disconnect
                      </AlertDialogAction>
                    </AlertDialogFooter>
                  </AlertDialogContent>
                </AlertDialog>
              </div>
              </div>
              {syncingIds.has(connection.id) && (
                <div className="mt-3 space-y-1.5">
                  <div className="flex items-center justify-between text-xs text-muted-foreground">
                    <span>
                      {(() => {
                        const progress = syncProgress.get(connection.id);
                        if (progress && progress.accounts_total > 0) {
                          return `Syncing account ${progress.accounts_done} of ${progress.accounts_total} · ${progress.transactions_created} transactions imported`;
                        }
                        return "Preparing sync...";
                      })()}
                    </span>
                    <span>{elapsedSeconds.get(connection.id) ?? 0}s elapsed</span>
                  </div>
                  <Progress
                    value={(() => {
                      const progress = syncProgress.get(connection.id);
                      if (progress && progress.accounts_total > 0) {
                        return (progress.accounts_done / progress.accounts_total) * 100;
                      }
                      return 0;
                    })()}
                  />
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
