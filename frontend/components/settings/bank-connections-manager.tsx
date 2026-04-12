"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { Button, buttonVariants } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  RiBankLine,
  RiRefreshLine,
  RiLinkUnlinkM,
  RiAddLine,
  RiAlertLine,
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
import { triggerSync, disconnectBank } from "@/lib/actions/bank-connections";
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

export function BankConnectionsManager({ connections }: BankConnectionsManagerProps) {
  const router = useRouter();
  const [syncingIds, setSyncingIds] = useState<Set<string>>(new Set());
  const [disconnectingIds, setDisconnectingIds] = useState<Set<string>>(new Set());

  const handleSync = async (connectionId: string) => {
    setSyncingIds((prev) => new Set(prev).add(connectionId));
    try {
      const result = await triggerSync(connectionId);
      if (!result.success) {
        console.error("Sync failed:", result.error);
      }
      router.refresh();
    } finally {
      setSyncingIds((prev) => {
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
              className="flex items-center justify-between rounded-lg border p-4"
            >
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
                <AlertDialog>
                  <AlertDialogTrigger asChild>
                    <Button
                      variant="outline"
                      size="sm"
                      disabled={disconnectingIds.has(connection.id)}
                    >
                      <RiLinkUnlinkM className="mr-1.5 h-4 w-4" />
                      Disconnect
                    </Button>
                  </AlertDialogTrigger>
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
          ))}
        </div>
      )}
    </div>
  );
}
