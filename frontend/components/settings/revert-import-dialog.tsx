"use client";

import { useState } from "react";
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
import { Separator } from "@/components/ui/separator";
import { RiDeleteBinLine, RiLoader4Line, RiAlertLine, RiErrorWarningLine } from "@remixicon/react";
import { toast } from "sonner";
import { revertCsvImport, type CsvImportWithStats } from "@/lib/actions/csv-import";

const CONFIRMATION_PHRASE = "delete transactions";

interface RevertImportDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  csvImport: CsvImportWithStats;
  onSuccess: () => void;
}

export function RevertImportDialog({
  open,
  onOpenChange,
  csvImport,
  onSuccess,
}: RevertImportDialogProps) {
  const [confirmInput, setConfirmInput] = useState("");
  const [reverting, setReverting] = useState(false);

  const isConfirmed = confirmInput.trim().toLowerCase() === CONFIRMATION_PHRASE;

  function handleOpenChange(nextOpen: boolean) {
    if (!reverting) {
      if (!nextOpen) setConfirmInput("");
      onOpenChange(nextOpen);
    }
  }

  async function handleRevert() {
    if (!isConfirmed || reverting) return;
    setReverting(true);
    try {
      const result = await revertCsvImport(csvImport.id);
      if (result.success) {
        toast.success(
          `Reverted "${csvImport.fileName}" — ${result.deletedCount} transaction${result.deletedCount !== 1 ? "s" : ""} deleted`
        );
        onSuccess();
        onOpenChange(false);
      } else {
        toast.error(result.error ?? "Failed to revert import");
      }
    } finally {
      setReverting(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2 text-destructive">
            <RiDeleteBinLine className="size-4 shrink-0" />
            Revert Import
          </DialogTitle>
          <DialogDescription>
            This will permanently delete all transactions from this import. This action cannot be undone.
          </DialogDescription>
        </DialogHeader>

        {/* Import summary */}
        <div className="space-y-1 rounded-none border px-3 py-2.5 text-xs">
          <div className="flex items-center justify-between">
            <span className="text-muted-foreground">File</span>
            <span className="font-mono font-medium truncate max-w-[200px]">{csvImport.fileName}</span>
          </div>
          {csvImport.account && (
            <div className="flex items-center justify-between">
              <span className="text-muted-foreground">Account</span>
              <span className="font-medium">{csvImport.account.name}</span>
            </div>
          )}
          <div className="flex items-center justify-between">
            <span className="text-muted-foreground">Transactions to delete</span>
            <span className="font-mono font-medium">{csvImport.transactionCount}</span>
          </div>
        </div>

        {/* Manually edited warning */}
        {csvImport.hasEditedTransactions && (
          <div className="flex items-start gap-2 rounded-none border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-700 dark:border-amber-800 dark:bg-amber-950/30 dark:text-amber-400">
            <RiAlertLine className="size-4 shrink-0 mt-0.5" />
            <span>
              Some transactions from this import have been manually re-categorized. Those changes will also be permanently deleted.
            </span>
          </div>
        )}

        {/* Permanent action warning */}
        <div className="flex items-start gap-2 rounded-none border border-destructive/20 bg-destructive/5 px-3 py-2 text-xs text-destructive">
          <RiErrorWarningLine className="size-4 shrink-0 mt-0.5" />
          <span>
            All balance figures will be recalculated after deletion. This action is permanent — there is no undo.
          </span>
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
              if (e.key === "Enter" && isConfirmed && !reverting) handleRevert();
            }}
          />
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => handleOpenChange(false)} disabled={reverting}>
            Cancel
          </Button>
          <Button
            variant="destructive"
            disabled={!isConfirmed || reverting}
            onClick={handleRevert}
          >
            {reverting ? (
              <>
                <RiLoader4Line className="size-4 animate-spin" />
                Reverting…
              </>
            ) : (
              <>
                <RiDeleteBinLine className="size-4" />
                Revert Import
              </>
            )}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
