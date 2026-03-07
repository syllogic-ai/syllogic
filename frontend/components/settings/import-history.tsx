"use client";

import { useState, useEffect, useCallback } from "react";
import { toast } from "sonner";
import { format } from "date-fns";
import {
  RiFileTextLine,
  RiLoader4Line,
  RiArrowGoBackLine,
} from "@remixicon/react";
import { Button } from "@/components/ui/button";
import {
  getImportHistory,
  revertImport,
  type ImportHistoryItem,
} from "@/lib/actions/transaction-delete";
import { DeleteTransactionsDialog } from "@/components/transactions/delete-transactions-dialog";

export function ImportHistory() {
  const [imports, setImports] = useState<ImportHistoryItem[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [revertingImportId, setRevertingImportId] = useState<string | null>(null);
  const [showRevertDialog, setShowRevertDialog] = useState(false);
  const [selectedImport, setSelectedImport] = useState<ImportHistoryItem | null>(null);
  const [isReverting, setIsReverting] = useState(false);

  const loadImports = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    const result = await getImportHistory();
    if (result.success && result.imports) {
      setImports(result.imports);
    } else {
      setError(result.error || "Failed to load import history");
    }
    setIsLoading(false);
  }, []);

  useEffect(() => {
    loadImports();
  }, [loadImports]);

  const handleRevertClick = (imp: ImportHistoryItem) => {
    setSelectedImport(imp);
    setShowRevertDialog(true);
  };

  const handleRevertConfirm = async () => {
    if (!selectedImport) return;
    setIsReverting(true);
    try {
      const result = await revertImport(selectedImport.id, "delete transactions");
      if (result.success) {
        toast.success(
          `Reverted import "${selectedImport.file_name}". ${result.deletedCount} transactions deleted. Balance recalculation in progress.`
        );
        setShowRevertDialog(false);
        setSelectedImport(null);
        loadImports();
      } else {
        toast.error(result.error || "Failed to revert import");
      }
    } catch {
      toast.error("An error occurred. Please try again.");
    } finally {
      setIsReverting(false);
    }
  };

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-12">
        <RiLoader4Line className="h-6 w-6 animate-spin text-muted-foreground" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="text-center py-12 text-sm text-muted-foreground">
        {error}
      </div>
    );
  }

  if (imports.length === 0) {
    return (
      <div className="text-center py-12 space-y-2">
        <RiFileTextLine className="h-8 w-8 mx-auto text-muted-foreground/50" />
        <p className="text-sm text-muted-foreground">No imports yet.</p>
        <p className="text-xs text-muted-foreground">
          Import transactions from the Transactions page using CSV files.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-3">
      <p className="text-sm text-muted-foreground">
        Past CSV imports. Reverting an import permanently deletes all transactions from that upload.
      </p>

      <div className="border divide-y">
        {imports.map((imp) => {
          const isReverted = imp.status === "reverted";
          const isCompleted = imp.status === "completed";
          const canRevert = isCompleted && imp.transaction_count > 0;

          return (
            <div
              key={imp.id}
              className="flex items-center justify-between p-3 gap-4"
            >
              <div className="min-w-0 flex-1 space-y-1">
                <div className="flex items-center gap-2">
                  <RiFileTextLine className="h-4 w-4 text-muted-foreground shrink-0" />
                  <span className="text-sm font-medium truncate">
                    {imp.file_name}
                  </span>
                  <span
                    className={`text-[10px] px-1.5 py-0.5 font-medium ${
                      isReverted
                        ? "bg-muted text-muted-foreground"
                        : isCompleted
                          ? "bg-emerald-500/10 text-emerald-600"
                          : "bg-yellow-500/10 text-yellow-600"
                    }`}
                  >
                    {imp.status}
                  </span>
                </div>
                <div className="flex items-center gap-3 text-xs text-muted-foreground">
                  <span>{imp.account_name}</span>
                  {imp.imported_rows != null && (
                    <span>{imp.imported_rows} rows imported</span>
                  )}
                  {imp.transaction_count > 0 && (
                    <span>{imp.transaction_count} transactions</span>
                  )}
                  {imp.created_at && (
                    <span>
                      {format(new Date(imp.created_at), "MMM d, yyyy")}
                    </span>
                  )}
                </div>
              </div>

              {canRevert && (
                <Button
                  variant="outline"
                  size="sm"
                  className="text-destructive hover:text-destructive hover:bg-destructive/10 shrink-0"
                  onClick={() => handleRevertClick(imp)}
                >
                  <RiArrowGoBackLine className="h-3.5 w-3.5 mr-1" />
                  Revert
                </Button>
              )}
            </div>
          );
        })}
      </div>

      {selectedImport && (
        <DeleteTransactionsDialog
          open={showRevertDialog}
          onOpenChange={setShowRevertDialog}
          transactionIds={[]}
          onConfirm={handleRevertConfirm}
          isDeleting={isReverting}
          importMode
          importFileName={selectedImport.file_name}
          importId={selectedImport.id}
        />
      )}
    </div>
  );
}
