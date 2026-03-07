"use client";

import { useState, useEffect } from "react";
import { toast } from "sonner";
import { RiAlertLine, RiDeleteBinLine, RiLoader4Line } from "@remixicon/react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Separator } from "@/components/ui/separator";
import { getDeleteTransactionsPreview } from "@/lib/actions/transaction-delete";

interface AccountImpact {
  account_id: string;
  account_name: string;
  currency: string;
  current_balance: number | null;
  balance_change: number;
  projected_balance: number | null;
  has_anchored_balances: boolean;
  anchored_balance_count: number;
}

interface DeletePreview {
  transaction_count: number;
  total_amount: number;
  affected_accounts: AccountImpact[];
  has_modified_transactions: boolean;
  modified_transaction_count: number;
}

interface DeleteTransactionsDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  transactionIds: string[];
  onConfirm: () => void;
  isDeleting?: boolean;
  importMode?: boolean;
  importFileName?: string;
  importId?: string;
}

function formatCurrencyValue(amount: number, currency: string): string {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency,
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(amount);
}

export function DeleteTransactionsDialog({
  open,
  onOpenChange,
  transactionIds,
  onConfirm,
  isDeleting = false,
  importMode = false,
  importFileName,
  importId,
}: DeleteTransactionsDialogProps) {
  const [preview, setPreview] = useState<DeletePreview | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [confirmText, setConfirmText] = useState("");

  const isConfirmed = confirmText.trim().toLowerCase() === "delete transactions";

  useEffect(() => {
    if (!open) return;
    if (transactionIds.length === 0 && !importId) return;

    let cancelled = false;
    setConfirmText("");
    setError(null);
    setPreview(null);
    setIsLoading(true);

    (async () => {
      try {
        const result = await getDeleteTransactionsPreview(transactionIds, importId);
        if (cancelled) return;
        if (result.success && result.preview) {
          setPreview(result.preview);
        } else {
          setError(result.error || "Failed to load deletion preview.");
          toast.error("Failed to load deletion preview");
        }
      } catch {
        if (cancelled) return;
        setError("Failed to load deletion preview. Please try again.");
        toast.error("Failed to load deletion preview");
      } finally {
        if (!cancelled) setIsLoading(false);
      }
    })();

    return () => { cancelled = true; };
  }, [open, transactionIds, importId]);

  const handleOpenChange = (nextOpen: boolean) => {
    if (!isDeleting) {
      onOpenChange(nextOpen);
    }
  };

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent className="sm:max-w-[520px]" showCloseButton={!isDeleting}>
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <RiDeleteBinLine className="h-5 w-5 text-destructive" />
            {importMode ? "Revert Import" : "Delete Transactions"}
          </DialogTitle>
          <DialogDescription>
            {importMode
              ? `Revert the import${importFileName ? ` "${importFileName}"` : ""} and delete all associated transactions.`
              : `Permanently delete ${preview?.transaction_count ?? transactionIds.length} transaction${(preview?.transaction_count ?? transactionIds.length) !== 1 ? "s" : ""}.`}
          </DialogDescription>
        </DialogHeader>

        {isLoading ? (
          <div className="flex flex-col items-center justify-center py-12 gap-4">
            <RiLoader4Line className="h-8 w-8 animate-spin text-muted-foreground" />
            <p className="text-sm text-muted-foreground">Loading impact preview…</p>
          </div>
        ) : error ? (
          <div className="flex flex-col items-center justify-center py-12 gap-4">
            <RiAlertLine className="h-8 w-8 text-destructive" />
            <p className="text-sm text-muted-foreground">{error}</p>
          </div>
        ) : preview ? (
          <div className="space-y-4">
            {/* Permanent warning */}
            <div className="flex items-start gap-3 rounded-none border border-destructive/30 bg-destructive/5 p-3">
              <RiAlertLine className="h-5 w-5 text-destructive shrink-0 mt-0.5" />
              <div className="text-xs text-destructive">
                <p className="font-medium">This action is permanent and cannot be undone.</p>
                <p className="mt-1 text-destructive/80">
                  Account balances will be recalculated after deletion.
                </p>
              </div>
            </div>

            {/* Impact summary */}
            <div className="space-y-2">
              <p className="text-xs font-medium">
                {preview.transaction_count} transaction{preview.transaction_count !== 1 ? "s" : ""} will be deleted
              </p>
            </div>

            {/* Per-account balance impact */}
            {preview.affected_accounts.length > 0 && (
              <div className="space-y-2">
                <p className="text-xs font-medium text-muted-foreground">Balance Impact</p>
                <div className="border divide-y">
                  {preview.affected_accounts.map((account) => (
                    <div key={account.account_id} className="p-2.5 space-y-1.5">
                      <div className="flex items-center justify-between">
                        <span className="text-xs font-medium truncate">{account.account_name}</span>
                        <span className="text-xs font-mono text-muted-foreground">{account.currency}</span>
                      </div>
                      <div className="grid grid-cols-3 gap-2 text-xs">
                        <div>
                          <p className="text-muted-foreground">Current</p>
                          <p className="font-mono">
                            {account.current_balance !== null
                              ? formatCurrencyValue(account.current_balance, account.currency)
                              : "—"}
                          </p>
                        </div>
                        <div>
                          <p className="text-muted-foreground">Change</p>
                          <p className={`font-mono ${account.balance_change > 0 ? "text-emerald-600" : account.balance_change < 0 ? "text-destructive" : ""}`}>
                            {account.balance_change > 0 ? "+" : ""}
                            {formatCurrencyValue(account.balance_change, account.currency)}
                          </p>
                        </div>
                        <div>
                          <p className="text-muted-foreground">Projected</p>
                          <p className="font-mono">
                            {account.projected_balance !== null
                              ? formatCurrencyValue(account.projected_balance, account.currency)
                              : "—"}
                          </p>
                        </div>
                      </div>

                      {account.has_anchored_balances && (
                        <div className="flex items-start gap-2 mt-1 rounded-none bg-yellow-500/10 p-2">
                          <RiAlertLine className="h-3.5 w-3.5 text-yellow-600 shrink-0 mt-0.5" />
                          <p className="text-[11px] text-yellow-700 dark:text-yellow-400">
                            This account has {account.anchored_balance_count} anchored balance{account.anchored_balance_count !== 1 ? "s" : ""}. Deleting these transactions may create reconciliation gaps.
                          </p>
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Modified transactions warning (import revert) */}
            {importMode && preview.has_modified_transactions && (
              <div className="flex items-start gap-3 rounded-none border border-yellow-500/30 bg-yellow-500/5 p-3">
                <RiAlertLine className="h-5 w-5 text-yellow-600 shrink-0 mt-0.5" />
                <div className="text-xs text-yellow-700 dark:text-yellow-400">
                  <p className="font-medium">
                    {preview.modified_transaction_count} transaction{preview.modified_transaction_count !== 1 ? "s have" : " has"} been modified since import.
                  </p>
                  <p className="mt-1 opacity-80">
                    Category changes and other edits will be lost.
                  </p>
                </div>
              </div>
            )}

            <Separator />

            {/* Confirmation input */}
            <div className="space-y-2">
              <Label htmlFor="delete-confirm" className="text-xs">
                Type <span className="font-mono font-medium">delete transactions</span> to confirm
              </Label>
              <Input
                id="delete-confirm"
                value={confirmText}
                onChange={(e) => setConfirmText(e.target.value)}
                placeholder="delete transactions"
                disabled={isDeleting}
                autoComplete="off"
              />
            </div>
          </div>
        ) : null}

        <DialogFooter>
          <Button
            variant="outline"
            onClick={() => onOpenChange(false)}
            disabled={isDeleting}
          >
            Cancel
          </Button>
          <Button
            variant="destructive"
            onClick={onConfirm}
            disabled={!isConfirmed || isLoading || !!error || isDeleting}
          >
            <RiDeleteBinLine className="h-4 w-4" />
            {isDeleting
              ? "Deleting…"
              : importMode
                ? "Revert Import"
                : `Delete ${transactionIds.length} Transaction${transactionIds.length !== 1 ? "s" : ""}`}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
