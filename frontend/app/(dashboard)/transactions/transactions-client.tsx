"use client";

import { useState, useCallback, useEffect } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { RiLoader4Line } from "@remixicon/react";
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
      const stored = getPendingImport();
      if (stored) {
        setPendingImportState(stored);
      }
    }
  }, [importingId, session?.user?.id]);

  // Subscribe to import status updates
  const {
    progress,
    isImporting,
  } = useImportStatus(
    pendingImport?.userId,
    pendingImport?.importId,
    {
      onCompleted: () => {
        // Clear pending import and refresh data
        clearPendingImport();
        setPendingImportState(null);
        router.refresh();
        // Remove importing param from URL
        if (importingId) {
          router.replace("/transactions");
        }
      },
      onFailed: () => {
        clearPendingImport();
        setPendingImportState(null);
        if (importingId) {
          router.replace("/transactions");
        }
      },
      showToasts: true,
    }
  );

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
      {/* Import Progress Banner */}
      {isImporting && progress !== null && (
        <div className="mb-4 rounded-lg border border-blue-200 bg-blue-50 p-4 dark:border-blue-800 dark:bg-blue-950">
          <div className="flex items-center gap-3">
            <RiLoader4Line className="h-5 w-5 animate-spin text-blue-600 dark:text-blue-400" />
            <div className="flex-1">
              <p className="text-sm font-medium text-blue-900 dark:text-blue-100">
                Importing transactions...
              </p>
              <div className="mt-2 h-2 w-full overflow-hidden rounded-full bg-blue-200 dark:bg-blue-800">
                <div
                  className="h-full bg-blue-600 transition-all duration-300 dark:bg-blue-400"
                  style={{ width: `${progress}%` }}
                />
              </div>
              <p className="mt-1 text-xs text-blue-700 dark:text-blue-300">
                {progress}% complete
              </p>
            </div>
          </div>
        </div>
      )}

      <div className="min-h-0 flex-1 flex flex-col">
        <TransactionTable
          transactions={transactions}
          categories={categories}
          accounts={accounts}
          onUpdateTransaction={handleUpdateTransaction}
          onDeleteTransaction={handleDeleteTransaction}
          onBulkUpdate={handleBulkUpdate}
          action={<AddTransactionButton onAddManual={handleAddManual} />}
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
