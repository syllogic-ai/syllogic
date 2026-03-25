"use client";

import { useState, useEffect, useRef } from "react";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { Separator } from "@/components/ui/separator";
import {
  RiDeleteBinLine,
  RiLoader4Line,
  RiAlertLine,
  RiErrorWarningLine,
} from "@remixicon/react";
import { toast } from "sonner";
import { cn, formatAmount } from "@/lib/utils";
import { getDeleteImpact, deleteTransactions, type DeleteImpact } from "@/lib/actions/transactions";

const CONFIRMATION_PHRASE = "delete transactions";

interface DeleteConfirmationDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  transactionIds: string[];
  onSuccess: (deletedIds: string[]) => void;
}

export function DeleteConfirmationDialog({
  open,
  onOpenChange,
  transactionIds,
  onSuccess,
}: DeleteConfirmationDialogProps) {
  const [impact, setImpact] = useState<DeleteImpact | null>(null);
  const [loadingImpact, setLoadingImpact] = useState(false);
  const [confirmInput, setConfirmInput] = useState("");
  const [deleting, setDeleting] = useState(false);

  const isConfirmed = confirmInput.trim().toLowerCase() === CONFIRMATION_PHRASE;

  // Keep a fresh ref to onOpenChange so async callbacks don't capture a stale closure
  const onOpenChangeRef = useRef(onOpenChange);
  useEffect(() => {
    onOpenChangeRef.current = onOpenChange;
  });

  useEffect(() => {
    if (!open || !transactionIds.length) {
      setImpact(null);
      setConfirmInput("");
      return;
    }

    setLoadingImpact(true);
    getDeleteImpact(transactionIds)
      .then((result) => {
        if (result.success) {
          setImpact(result.data);
        } else {
          toast.error(result.error ?? "Failed to compute impact");
          onOpenChangeRef.current(false);
        }
      })
      .finally(() => setLoadingImpact(false));
  }, [open, transactionIds.join(",")]);

  async function handleDelete() {
    if (!isConfirmed || deleting) return;
    setDeleting(true);
    try {
      const result = await deleteTransactions(transactionIds);
      if (result.success) {
        const count = result.deletedCount ?? transactionIds.length;
        toast.success(
          `${count === 1 ? "Transaction" : `${count} transactions`} deleted`
        );
        onSuccess(transactionIds);
        onOpenChange(false);
      } else {
        toast.error(result.error ?? "Failed to delete transactions");
      }
    } finally {
      setDeleting(false);
    }
  }

  const hasAnchoredAccount = impact?.accountImpacts.some((a) => a.balanceIsAnchored) ?? false;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2 text-destructive">
            <RiDeleteBinLine className="size-4 shrink-0" />
            Delete {transactionIds.length === 1 ? "Transaction" : `${transactionIds.length} Transactions`}
          </DialogTitle>
          <DialogDescription>
            This action is permanent and cannot be undone.
          </DialogDescription>
        </DialogHeader>

        {/* Balance Impact */}
        <div className="space-y-3">
          {loadingImpact ? (
            <div className="space-y-2">
              <Skeleton className="h-4 w-32" />
              <Skeleton className="h-16 w-full" />
              <Skeleton className="h-16 w-full" />
            </div>
          ) : impact ? (
            <>
              <p className="text-xs text-muted-foreground">
                Balance impact across {impact.accountImpacts.length} account
                {impact.accountImpacts.length !== 1 ? "s" : ""}:
              </p>
              <div className="divide-y divide-border rounded-none border">
                {impact.accountImpacts.map((acc) => (
                  <div key={acc.accountId} className="px-3 py-2.5 space-y-1">
                    <div className="flex items-center justify-between">
                      <span className="text-xs font-medium">{acc.accountName}</span>
                      <span
                        className={cn(
                          "text-xs font-mono",
                          acc.amountChange > 0 ? "text-emerald-600" : "text-destructive"
                        )}
                      >
                        {acc.amountChange > 0 ? "+" : ""}
                        {formatAmount(acc.amountChange, acc.currency)}
                      </span>
                    </div>
                    {acc.balanceIsAnchored ? (
                      <div className="flex items-start gap-1.5 text-xs text-amber-600">
                        <RiAlertLine className="size-3.5 shrink-0 mt-0.5" />
                        <span>
                          Anchored balance — deletion will create a reconciliation gap. Verify your balance after deletion.
                        </span>
                      </div>
                    ) : (
                      <div className="flex items-center justify-between text-xs text-muted-foreground">
                        <span>New balance</span>
                        <span className="font-mono">
                          {formatAmount(acc.projectedBalance, acc.currency)}
                        </span>
                      </div>
                    )}
                  </div>
                ))}
              </div>

              {hasAnchoredAccount && (
                <div className="flex items-start gap-2 rounded-none border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-700 dark:border-amber-800 dark:bg-amber-950/30 dark:text-amber-400">
                  <RiErrorWarningLine className="size-4 shrink-0 mt-0.5" />
                  <span>
                    One or more affected accounts have an anchored balance derived from known bank data. After deletion, the opening and closing balances on record may no longer agree with the remaining transactions.
                  </span>
                </div>
              )}
            </>
          ) : null}
        </div>

        <Separator />

        {/* Typed confirmation */}
        <div className="space-y-2">
          <p className="text-xs text-muted-foreground">
            Type{" "}
            <span className="font-mono text-foreground">delete transactions</span>{" "}
            to confirm:
          </p>
          <Input
            value={confirmInput}
            onChange={(e) => setConfirmInput(e.target.value)}
            placeholder="delete transactions"
            className="font-mono text-xs"
            onKeyDown={(e) => {
              if (e.key === "Enter" && isConfirmed && !deleting) handleDelete();
            }}
          />
        </div>

        <DialogFooter>
          <Button
            variant="outline"
            onClick={() => onOpenChange(false)}
            disabled={deleting}
          >
            Cancel
          </Button>
          <Button
            variant="destructive"
            disabled={!isConfirmed || deleting || loadingImpact}
            onClick={handleDelete}
          >
            {deleting ? (
              <>
                <RiLoader4Line className="size-4 animate-spin" />
                Deleting…
              </>
            ) : (
              <>
                <RiDeleteBinLine className="size-4" />
                Delete{" "}
                {transactionIds.length === 1
                  ? "Transaction"
                  : `${transactionIds.length} Transactions`}
              </>
            )}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
