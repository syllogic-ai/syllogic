"use client";

import { useState, useEffect, useCallback, useMemo, Suspense } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { RiArrowLeftLine, RiCheckLine, RiAlertLine } from "@remixicon/react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Header } from "@/components/layout/header";
import { CsvPreviewTable } from "@/components/transactions/csv-preview-table";
import { cn } from "@/lib/utils";
import {
  previewImportedTransactions,
  finalizeImport,
  getCsvImportSession,
  type PreviewTransaction,
  type BalanceVerification,
} from "@/lib/actions/csv-import";

function PreviewPageContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const importId = searchParams.get("id");

  const [isLoading, setIsLoading] = useState(true);
  const [isImporting, setIsImporting] = useState(false);
  const [transactions, setTransactions] = useState<PreviewTransaction[]>([]);
  const [selectedIndices, setSelectedIndices] = useState<number[]>([]);
  const [balanceVerification, setBalanceVerification] = useState<BalanceVerification | null>(null);

  const loadData = useCallback(async () => {
    if (!importId) {
      toast.error("Import ID not found");
      router.push("/transactions/import");
      return;
    }

    try {
      // Check if import session exists
      const session = await getCsvImportSession(importId);
      if (!session) {
        toast.error("Import session not found");
        router.push("/transactions/import");
        return;
      }

      if (!session.columnMapping) {
        toast.error("Column mapping not found");
        router.push(`/transactions/import/mapping?id=${importId}`);
        return;
      }

      // Preview transactions
      const result = await previewImportedTransactions(importId);
      if (result.success && result.transactions) {
        setTransactions(result.transactions);
        // Select all non-duplicate transactions by default
        setSelectedIndices(
          result.transactions
            .filter((tx) => !tx.isDuplicate)
            .map((tx) => tx.rowIndex)
        );
        // Capture balance verification data if present
        if (result.balanceVerification) {
          setBalanceVerification(result.balanceVerification);
        }
      } else {
        toast.error(result.error || "Failed to preview transactions");
        router.push(`/transactions/import/mapping?id=${importId}`);
      }
    } catch (error) {
      console.error("Failed to load preview:", error);
      toast.error("Failed to load preview");
      router.push("/transactions/import");
    } finally {
      setIsLoading(false);
    }
  }, [importId, router]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  // Split transactions into "to import" and "skipped" (duplicates)
  const { toImport, skipped } = useMemo(() => {
    const toImport = transactions.filter((tx) => selectedIndices.includes(tx.rowIndex));
    const skipped = transactions.filter((tx) => !selectedIndices.includes(tx.rowIndex));
    return { toImport, skipped };
  }, [transactions, selectedIndices]);

  const handleImport = async () => {
    if (!importId) return;

    if (selectedIndices.length === 0) {
      toast.error("Please select at least one transaction to import");
      return;
    }

    setIsImporting(true);
    try {
      const result = await finalizeImport(importId, selectedIndices);
      if (result.success) {
        toast.success(`Successfully imported ${result.importedCount} transactions`);
        // Navigate to transactions page with cache-busting query param to ensure fresh data
        router.push(`/transactions?refresh=${Date.now()}`);
        // Also refresh the router to ensure cache is cleared
        router.refresh();
      } else {
        toast.error(result.error || "Failed to import transactions");
      }
    } catch {
      toast.error("Failed to import transactions");
    } finally {
      setIsImporting(false);
    }
  };

  if (isLoading) {
    return (
      <>
        <Header title="Preview Import" />
        <div className="flex flex-1 flex-col gap-4 p-4 pt-0">
          <div className="flex h-[calc(100vh-8rem)] items-center justify-center">
            <div className="text-center">
              <div className="mx-auto mb-4 h-8 w-8 animate-spin rounded-full border-2 border-muted border-t-primary" />
              <p className="text-muted-foreground">Loading preview...</p>
            </div>
          </div>
        </div>
      </>
    );
  }

  return (
    <>
      <Header title="Preview Import" />
      <div className="flex h-[calc(100vh-4rem)] flex-col p-4 pt-0">
        {/* Balance Verification Card */}
        {balanceVerification?.hasBalanceData && (
          <div
            className={cn(
              "mb-4 rounded-lg border p-4",
              !balanceVerification.canVerify
                ? "border-muted bg-muted/30"
                : balanceVerification.isVerified
                  ? "border-green-200 bg-green-50 dark:border-green-800 dark:bg-green-950"
                  : "border-amber-200 bg-amber-50 dark:border-amber-800 dark:bg-amber-950"
            )}
          >
            <div className="flex items-center gap-2 mb-3">
              {!balanceVerification.canVerify ? (
                <RiAlertLine className="h-5 w-5 text-muted-foreground" />
              ) : balanceVerification.isVerified ? (
                <RiCheckLine className="h-5 w-5 text-green-600 dark:text-green-400" />
              ) : (
                <RiAlertLine className="h-5 w-5 text-amber-600 dark:text-amber-400" />
              )}
              <span className="font-medium">
                {!balanceVerification.canVerify
                  ? "Balance Info (partial)"
                  : balanceVerification.isVerified
                    ? "Balance Verified"
                    : "Balance Discrepancy Detected"}
              </span>
            </div>
            <div className="grid grid-cols-2 gap-x-8 gap-y-2 text-sm">
              {balanceVerification.fileStartingBalance !== null && (
                <div className="flex justify-between">
                  <span className="text-muted-foreground">Starting Balance:</span>
                  <span className="font-mono">
                    {balanceVerification.fileStartingBalance.toFixed(2)}
                  </span>
                </div>
              )}
              {balanceVerification.fileEndingBalance !== null && (
                <div className="flex justify-between">
                  <span className="text-muted-foreground">Ending Balance (file):</span>
                  <span className="font-mono">
                    {balanceVerification.fileEndingBalance.toFixed(2)}
                  </span>
                </div>
              )}
              {balanceVerification.calculatedEndingBalance !== null && (
                <div className="flex justify-between">
                  <span className="text-muted-foreground">Calculated Ending:</span>
                  <span className="font-mono">
                    {balanceVerification.calculatedEndingBalance.toFixed(2)}
                  </span>
                </div>
              )}
              {balanceVerification.canVerify &&
                !balanceVerification.isVerified &&
                balanceVerification.discrepancy !== null && (
                  <div className="flex justify-between text-amber-600 dark:text-amber-400">
                    <span>Discrepancy:</span>
                    <span className="font-mono font-medium">
                      {balanceVerification.discrepancy.toFixed(2)}
                    </span>
                  </div>
                )}
            </div>
            {!balanceVerification.canVerify && (
              <p className="mt-2 text-xs text-muted-foreground">
                Map both starting and ending balance columns for full verification.
              </p>
            )}
          </div>
        )}

        <Tabs defaultValue="to-import" className="flex min-h-0 flex-1 flex-col">
          {/* Tabs outside container */}
          <TabsList className="mb-2 w-fit">
            <TabsTrigger value="to-import" className="gap-2">
              To Import
              <span className="rounded-full bg-primary/10 px-2 py-0.5 text-xs font-medium">
                {toImport.length}
              </span>
            </TabsTrigger>
            <TabsTrigger value="skipped" className="gap-2" disabled={skipped.length === 0}>
              Skipped
              <span className="rounded-full bg-muted px-2 py-0.5 text-xs font-medium">
                {skipped.length}
              </span>
            </TabsTrigger>
          </TabsList>

          {/* Container with scrollable table */}
          <div className="min-h-0 flex-1 overflow-hidden rounded-lg border bg-card">
            <TabsContent value="to-import" className="h-full m-0">
              <div className="h-full overflow-y-auto">
                <CsvPreviewTable
                  transactions={toImport}
                  selectedIndices={selectedIndices}
                  onSelectionChange={setSelectedIndices}
                  showCheckboxes={false}
                />
              </div>
            </TabsContent>

            <TabsContent value="skipped" className="h-full m-0">
              <div className="h-full overflow-y-auto">
                <CsvPreviewTable
                  transactions={skipped}
                  selectedIndices={[]}
                  onSelectionChange={() => {}}
                  showCheckboxes={false}
                />
              </div>
            </TabsContent>
          </div>
        </Tabs>

        {/* Footer Actions - always visible */}
        <div className="mt-4 flex shrink-0 items-center justify-between border-t pt-4">
          <Button
            type="button"
            variant="outline"
            onClick={() => router.push(`/transactions/import/mapping?id=${importId}`)}
          >
            <RiArrowLeftLine className="mr-2 h-4 w-4" />
            Back to Mapping
          </Button>
          <Button
            onClick={handleImport}
            disabled={isImporting || selectedIndices.length === 0}
          >
            {isImporting ? "Importing..." : `Import ${selectedIndices.length} Transactions`}
            <RiCheckLine className="ml-2 h-4 w-4" />
          </Button>
        </div>
      </div>
    </>
  );
}

export default function PreviewPage() {
  return (
    <Suspense
      fallback={
        <>
          <Header title="Preview Import" />
          <div className="flex flex-1 flex-col gap-4 p-4 pt-0">
            <div className="flex h-[calc(100vh-8rem)] items-center justify-center">
              <div className="text-center">
                <div className="mx-auto mb-4 h-8 w-8 animate-spin rounded-full border-2 border-muted border-t-primary" />
                <p className="text-muted-foreground">Loading...</p>
              </div>
            </div>
          </div>
        </>
      }
    >
      <PreviewPageContent />
    </Suspense>
  );
}
