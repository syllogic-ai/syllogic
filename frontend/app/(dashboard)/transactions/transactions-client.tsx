"use client";

import { useState, useCallback, useEffect } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { RiLoader4Line } from "@remixicon/react";
import { Progress } from "@/components/ui/progress";
import { TransactionTable } from "@/components/transactions/transaction-table";
import { AddTransactionButton } from "@/components/transactions/add-transaction-button";
import { AddTransactionDialog } from "@/components/transactions/add-transaction-dialog";
import { useRegisterCommandPaletteCallbacks } from "@/components/command-palette-context";
import { exportTransactionsToCSV } from "@/lib/utils/csv-export";
import {
  useImportStatus,
  getPendingImport,
  clearPendingImport,
} from "@/lib/hooks/use-import-status";
import { useSession } from "@/lib/auth-client";
import type { TransactionWithRelations } from "@/lib/actions/transactions";
import type { CategoryDisplay, AccountForFilter } from "@/types";

interface TransactionsClientProps {
  initialTransactions: TransactionWithRelations[];
  categories: CategoryDisplay[];
  accounts: AccountForFilter[];
}

export function TransactionsClient({
  initialTransactions,
  categories,
  accounts,
}: TransactionsClientProps) {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { data: session } = useSession();
  const [transactions, setTransactions] = useState(initialTransactions);
  const [isAddDialogOpen, setIsAddDialogOpen] = useState(false);
  const [importStatus, setImportStatus] = useState<"importing" | "completed" | "failed" | null>(null);

  useEffect(() => {
    setTransactions(initialTransactions);
  }, [initialTransactions]);

  // Check for pending import from URL or sessionStorage
  const importingId = searchParams.get("importing");
  const [pendingImport, setPendingImportState] = useState<{
    importId: string;
    userId: string;
  } | null>(null);

  // Initialize pending import from URL or storage
  useEffect(() => {
    if (importingId && session?.user?.id) {
      setPendingImportState({ importId: importingId, userId: session.user.id });
    } else {
      if (!session?.user?.id) {
        return;
      }

      const stored = getPendingImport();
      if (stored) {
        if (stored.userId !== session.user.id) {
          clearPendingImport();
          setPendingImportState(null);
          setImportStatus(null);
          return;
        }
        setPendingImportState(stored);
      }
    }
  }, [importingId, session?.user?.id]);

  useEffect(() => {
    if (!session?.user?.id && pendingImport?.importId) {
      clearPendingImport();
      setPendingImportState(null);
      setImportStatus(null);
      return;
    }

    if (
      session?.user?.id &&
      pendingImport?.userId &&
      pendingImport.userId !== session.user.id
    ) {
      clearPendingImport();
      setPendingImportState(null);
      setImportStatus(null);
    }
  }, [session?.user?.id, pendingImport?.importId, pendingImport?.userId]);

  const checkImportStatus = useCallback(async () => {
    if (!pendingImport?.importId || !pendingImport.userId) {
      return;
    }

    try {
      const backendBase =
        process.env.NODE_ENV === "development"
          ? process.env.NEXT_PUBLIC_BACKEND_URL || "http://localhost:8000"
          : process.env.NEXT_PUBLIC_BACKEND_URL || "";

      const base = backendBase
        ? `${backendBase}/api/csv-import/status/${pendingImport.importId}`
        : `/api/csv-import/status/${pendingImport.importId}`;

      const response = await fetch(`${base}?user_id=${pendingImport.userId}`);
      if (response.status === 404 || response.status === 403) {
        clearPendingImport();
        setPendingImportState(null);
        setImportStatus(null);
        if (importingId) {
          router.replace("/transactions");
        }
        return;
      }
      if (!response.ok) return;

      const status = await response.json();
      const importStatusValue = status?.status as
        | "pending"
        | "mapping"
        | "previewing"
        | "importing"
        | "completed"
        | "failed"
        | undefined;

      const totalRows = typeof status?.total_rows === "number"
        ? status.total_rows
        : typeof status?.totalRows === "number"
          ? status.totalRows
          : null;
      const progressCount = typeof status?.progress_count === "number"
        ? status.progress_count
        : typeof status?.progressCount === "number"
          ? status.progressCount
          : null;
      const importedRows = typeof status?.imported_rows === "number"
        ? status.imported_rows
        : typeof status?.importedRows === "number"
          ? status.importedRows
          : null;

      const completedByCounts = totalRows !== null && totalRows > 0 && (
        (progressCount !== null && progressCount >= totalRows) ||
        (importedRows !== null && importedRows >= totalRows)
      );

      if (importStatusValue === "importing") {
        setImportStatus("importing");
      } else if (importStatusValue === "completed") {
        setImportStatus("completed");
      } else if (importStatusValue === "failed") {
        setImportStatus("failed");
      } else if (importStatusValue) {
        setImportStatus(null);
      }

      if (importStatusValue === "completed" || importStatusValue === "failed" || (importStatusValue === "importing" && completedByCounts)) {
        clearPendingImport();
        setPendingImportState(null);
        if (!importStatusValue) {
          setImportStatus(null);
        }
        if (importStatusValue === "importing" && completedByCounts) {
          setImportStatus("completed");
        }
        router.refresh();
        if (importingId) {
          router.replace("/transactions");
        }
      }
    } catch {
      // Status check failed; rely on SSE updates
    }
  }, [pendingImport?.importId, pendingImport?.userId, importingId, router]);

  useEffect(() => {
    checkImportStatus();
  }, [checkImportStatus]);

  // Subscribe to import status updates
  const { isImporting, progress, processedRows, totalRows } = useImportStatus(
    pendingImport?.userId,
    pendingImport?.importId,
    {
      onStarted: () => { setImportStatus("importing"); },
      onProgress: () => { setImportStatus("importing"); },
      onCompleted: () => {
        clearPendingImport();
        setPendingImportState(null);
        setImportStatus("completed");
        router.refresh();
        if (importingId) router.replace("/transactions");
      },
      onFailed: () => {
        clearPendingImport();
        setPendingImportState(null);
        setImportStatus("failed");
        if (importingId) router.replace("/transactions");
      },
      showToasts: false,  // Global ImportStatusNotifier handles toasts
    }
  );

  useEffect(() => {
    if (!pendingImport?.importId || !pendingImport.userId) {
      return;
    }

    if (importStatus !== "importing" && !isImporting) {
      return;
    }

    const interval = setInterval(checkImportStatus, 15000);
    return () => clearInterval(interval);
  }, [importStatus, isImporting, pendingImport?.importId, pendingImport?.userId, checkImportStatus]);

  const handleUpdateTransaction = (
    id: string,
    updates: Partial<TransactionWithRelations>
  ) => {
    setTransactions((prev) =>
      prev.map((tx) => (tx.id === id ? { ...tx, ...updates } : tx))
    );
  };

  const handleDeleteTransaction = (id: string) => {
    setTransactions((prev) => prev.filter((tx) => tx.id !== id));
  };

  const handleBulkUpdate = (transactionIds: string[], categoryId: string | null) => {
    const category = categoryId
      ? categories.find((c) => c.id === categoryId) ?? null
      : null;

    setTransactions((prev) =>
      prev.map((tx) =>
        transactionIds.includes(tx.id)
          ? { ...tx, categoryId, category }
          : tx
      )
    );
  };

  const handleAddManual = useCallback(() => {
    setIsAddDialogOpen(true);
  }, []);

  const handleExportCSV = useCallback(() => {
    exportTransactionsToCSV(transactions);
  }, [transactions]);

  // Register command palette callbacks
  useRegisterCommandPaletteCallbacks(
    {
      onAddTransaction: handleAddManual,
      onExportCSV: handleExportCSV,
    },
    [handleAddManual, handleExportCSV]
  );

  return (
    <>
      <div className="min-h-0 flex-1 flex flex-col">
        <TransactionTable
          transactions={transactions}
          categories={categories}
          accounts={accounts}
          onUpdateTransaction={handleUpdateTransaction}
          onDeleteTransaction={handleDeleteTransaction}
          onBulkUpdate={handleBulkUpdate}
          action={
            <div className="flex flex-row items-center gap-3">
              {importStatus === "importing" && (
                <div className="flex flex-col gap-1 min-w-[180px]">
                  <div className="flex items-center justify-between gap-2 text-sm text-muted-foreground">
                    <div className="flex items-center gap-2">
                      <RiLoader4Line className="h-4 w-4 animate-spin shrink-0" />
                      <span>Importing transactions</span>
                    </div>
                    {progress !== null && (
                      <span className="text-xs font-mono tabular-nums">{progress}%</span>
                    )}
                  </div>
                  {progress !== null && <Progress value={progress} className="h-1.5" />}
                  {processedRows !== null && totalRows !== null && (
                    <span className="text-xs text-muted-foreground font-mono tabular-nums">
                      {processedRows} / {totalRows} rows
                    </span>
                  )}
                </div>
              )}
              <AddTransactionButton onAddManual={handleAddManual} />
            </div>
          }
        />
      </div>
      <AddTransactionDialog
        open={isAddDialogOpen}
        onOpenChange={setIsAddDialogOpen}
        categories={categories}
      />
    </>
  );
}
