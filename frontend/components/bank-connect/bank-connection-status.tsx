"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { toast } from "sonner";
import {
  RiBankLine,
  RiRefreshLine,
  RiDeleteBinLine,
  RiLoader4Line,
  RiCheckLine,
  RiErrorWarningLine,
  RiTimeLine,
} from "@remixicon/react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
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
import {
  BankConnection,
  triggerManualSync,
  disconnectBank,
} from "@/lib/actions/bank-connections";

interface BankConnectionStatusProps {
  connection: BankConnection;
  onUpdate?: () => void;
}

export function BankConnectionStatus({
  connection,
  onUpdate,
}: BankConnectionStatusProps) {
  const router = useRouter();
  const [isSyncing, setIsSyncing] = useState(false);
  const [isDisconnecting, setIsDisconnecting] = useState(false);

  const handleSync = async () => {
    setIsSyncing(true);

    try {
      const result = await triggerManualSync(connection.id);

      if (result.success) {
        const totalSynced = (result.transactionsCreated || 0) + (result.transactionsUpdated || 0);
        const suggestionsCount = result.suggestionsCount || 0;

        if (suggestionsCount > 0) {
          toast.success(
            `Synced ${totalSynced} transaction(s). ${suggestionsCount} subscription suggestion(s) found.`,
            {
              action: {
                label: "View Suggestions",
                onClick: () => router.push("/subscriptions"),
              },
            }
          );
        } else {
          toast.success(`Synced ${totalSynced} transaction(s)`);
        }

        onUpdate?.();
      } else {
        toast.error(result.error || "Failed to sync");
      }
    } catch (error) {
      console.error("Sync error:", error);
      toast.error("Failed to sync. Please try again.");
    } finally {
      setIsSyncing(false);
    }
  };

  const handleDisconnect = async () => {
    setIsDisconnecting(true);

    try {
      const result = await disconnectBank(connection.id);

      if (result.success) {
        toast.success("Bank disconnected. Accounts converted to manual.");
        onUpdate?.();
      } else {
        toast.error(result.error || "Failed to disconnect");
      }
    } catch (error) {
      console.error("Disconnect error:", error);
      toast.error("Failed to disconnect. Please try again.");
    } finally {
      setIsDisconnecting(false);
    }
  };

  const getSyncStatusBadge = () => {
    const syncStatus = connection.syncStatus || "idle";

    switch (syncStatus) {
      case "syncing":
        return (
          <Badge variant="secondary" className="gap-1">
            <RiLoader4Line className="h-3 w-3 animate-spin" />
            Syncing
          </Badge>
        );
      case "error":
        return (
          <Badge variant="destructive" className="gap-1">
            <RiErrorWarningLine className="h-3 w-3" />
            Error
          </Badge>
        );
      default:
        return (
          <Badge variant="outline" className="gap-1">
            <RiCheckLine className="h-3 w-3" />
            Connected
          </Badge>
        );
    }
  };

  const formatLastSynced = () => {
    if (!connection.lastSyncedAt) {
      return "Never synced";
    }

    const date = new Date(connection.lastSyncedAt);
    const now = new Date();
    const diff = now.getTime() - date.getTime();
    const hours = Math.floor(diff / (1000 * 60 * 60));
    const days = Math.floor(hours / 24);

    if (days > 0) {
      return `${days} day${days > 1 ? "s" : ""} ago`;
    }
    if (hours > 0) {
      return `${hours} hour${hours > 1 ? "s" : ""} ago`;
    }
    const minutes = Math.floor(diff / (1000 * 60));
    if (minutes > 0) {
      return `${minutes} minute${minutes > 1 ? "s" : ""} ago`;
    }
    return "Just now";
  };

  return (
    <Card>
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="h-10 w-10 rounded-full bg-muted flex items-center justify-center">
              <RiBankLine className="h-5 w-5 text-muted-foreground" />
            </div>
            <div>
              <CardTitle className="text-base">
                {connection.institutionName || "Bank Connection"}
              </CardTitle>
              <CardDescription>
                {connection.accountCount} account{connection.accountCount !== 1 ? "s" : ""}
              </CardDescription>
            </div>
          </div>
          {getSyncStatusBadge()}
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        {connection.errorMessage && (
          <div className="text-sm text-destructive bg-destructive/10 p-2 rounded">
            {connection.errorMessage}
          </div>
        )}

        <div className="flex items-center justify-between text-sm text-muted-foreground">
          <div className="flex items-center gap-1">
            <RiTimeLine className="h-4 w-4" />
            Last synced: {formatLastSynced()}
          </div>
        </div>

        <div className="flex gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={handleSync}
            disabled={isSyncing || connection.syncStatus === "syncing"}
            className="flex-1"
          >
            {isSyncing || connection.syncStatus === "syncing" ? (
              <>
                <RiLoader4Line className="mr-2 h-4 w-4 animate-spin" />
                Syncing...
              </>
            ) : (
              <>
                <RiRefreshLine className="mr-2 h-4 w-4" />
                Sync Now
              </>
            )}
          </Button>

          <AlertDialog>
            <AlertDialogTrigger
              disabled={isDisconnecting}
              render={
                <Button
                  variant="outline"
                  size="sm"
                  className="text-destructive hover:text-destructive"
                >
                  {isDisconnecting ? (
                    <RiLoader4Line className="h-4 w-4 animate-spin" />
                  ) : (
                    <RiDeleteBinLine className="h-4 w-4" />
                  )}
                </Button>
              }
            />
            <AlertDialogContent>
              <AlertDialogHeader>
                <AlertDialogTitle>Disconnect Bank?</AlertDialogTitle>
                <AlertDialogDescription>
                  This will disconnect your bank connection and convert all linked
                  accounts to manual accounts. Your transaction history will be
                  preserved.
                </AlertDialogDescription>
              </AlertDialogHeader>
              <AlertDialogFooter>
                <AlertDialogCancel>Cancel</AlertDialogCancel>
                <AlertDialogAction onClick={handleDisconnect}>
                  Disconnect
                </AlertDialogAction>
              </AlertDialogFooter>
            </AlertDialogContent>
          </AlertDialog>
        </div>
      </CardContent>
    </Card>
  );
}
