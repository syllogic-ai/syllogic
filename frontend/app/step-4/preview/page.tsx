"use client";

import { useState, useEffect, useCallback, useMemo, Suspense } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { RiArrowLeftLine, RiCheckLine, RiAlertLine } from "@remixicon/react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { OnboardingProgress } from "@/components/onboarding/onboarding-progress";
import { CsvPreviewTable } from "@/components/transactions/csv-preview-table";
import { cn } from "@/lib/utils";
import {
  previewImportedTransactions,
  enqueueBackgroundImport,
  getCsvImportSession,
  type PreviewTransaction,
  type BalanceVerification,
} from "@/lib/actions/csv-import";
import { setPendingImport } from "@/lib/hooks/use-import-status";
import { useSession } from "@/lib/auth-client";

const SHORTCUTS: Array<{ keys: string[]; label: string }> = [
  { keys: ["Cmd", "K"], label: "Open command palette" },
  { keys: ["B"], label: "Go to dashboard" },
  { keys: ["T"], label: "Go to transactions" },
  { keys: ["A"], label: "Go to assets" },
  { keys: ["S"], label: "Go to settings" },
  { keys: ["N"], label: "New transaction" },
  { keys: ["M"], label: "Toggle theme" },
];

function ShortcutKeys({ keys }: { keys: string[] }) {
  return (
    <div className="flex items-center gap-1">
      {keys.map((key) => (
        <kbd
          key={key}
          className="inline-flex h-6 items-center rounded border bg-muted px-2 text-[10px] font-mono text-muted-foreground"
        >
          {key}
        </kbd>
      ))}
    </div>
  );
}

function PreviewPageContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const importId = searchParams.get("id");
  const { data: session } = useSession();

  const [isLoading, setIsLoading] = useState(true);
  const [isImporting, setIsImporting] = useState(false);
  const [hasStartedImport, setHasStartedImport] = useState(false);
  const [showSuccessModal, setShowSuccessModal] = useState(false);
  const [transactions, setTransactions] = useState<PreviewTransaction[]>([]);
  const [selectedIndices, setSelectedIndices] = useState<number[]>([]);
  const [balanceVerification, setBalanceVerification] = useState<BalanceVerification | null>(null);

  const loadData = useCallback(async () => {
    if (!importId) {
      toast.error("Import ID not found");
      router.push("/step-4");
      return;
    }

    try {
      const session = await getCsvImportSession(importId);
      if (!session) {
        toast.error("Import session not found");
        router.push("/step-4");
        return;
      }

      if (!session.columnMapping) {
        toast.error("Column mapping not found");
        router.push(`/step-4/mapping?id=${importId}`);
        return;
      }

      const result = await previewImportedTransactions(importId);
      if (result.success && result.transactions) {
        setTransactions(result.transactions);
        setSelectedIndices(
          result.transactions.filter((tx) => !tx.isDuplicate).map((tx) => tx.rowIndex)
        );
        if (result.balanceVerification) {
          setBalanceVerification(result.balanceVerification);
        }
      } else {
        toast.error(result.error || "Failed to preview transactions");
        router.push(`/step-4/mapping?id=${importId}`);
      }
    } catch (error) {
      console.error("Failed to load preview:", error);
      toast.error("Failed to load preview");
      router.push("/step-4");
    } finally {
      setIsLoading(false);
    }
  }, [importId, router]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  useEffect(() => {
    if (!showSuccessModal) return;

    let active = true;

    const fireConfetti = async () => {
      try {
        const mod = await import("canvas-confetti");
        const confetti = "default" in mod ? mod.default : mod;

        if (!active) return;

        confetti({
          particleCount: 90,
          spread: 70,
          origin: { y: 0.6 },
        });

        setTimeout(() => {
          if (!active) return;
          confetti({
            particleCount: 60,
            spread: 90,
            origin: { y: 0.4 },
          });
        }, 250);
      } catch {
        // Ignore confetti failures
      }
    };

    fireConfetti();

    return () => {
      active = false;
    };
  }, [showSuccessModal]);

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

    if (!session?.user?.id) {
      toast.error("Not authenticated");
      return;
    }

    setIsImporting(true);

    try {
      const result = await enqueueBackgroundImport(importId, selectedIndices);

      if (result.success && result.importId) {
        setPendingImport(result.importId, session.user.id);
        setHasStartedImport(true);
        setShowSuccessModal(true);
      } else {
        toast.error(result.error || "Failed to start import");
      }
    } catch (error) {
      console.error("Import error:", error);
      toast.error("Failed to start import");
    } finally {
      setIsImporting(false);
    }
  };

  if (isLoading) {
    return (
      <div className="space-y-8">
        <OnboardingProgress currentStep={4} />
        <Card className="min-h-[640px] h-[640px] flex flex-col">
          <CardContent className="flex items-center justify-center py-12">
            <div className="text-center">
              <div className="mx-auto mb-4 h-8 w-8 animate-spin rounded-full border-2 border-muted border-t-primary" />
              <p className="text-muted-foreground">Loading preview...</p>
            </div>
          </CardContent>
        </Card>
      </div>
    );
  }

  return (
    <div className="space-y-8">
      <OnboardingProgress currentStep={4} />
      <Card className="min-h-[640px] h-[640px] flex flex-col">
        <CardHeader>
          <CardTitle>Preview your import</CardTitle>
          <CardDescription>
            Review what will be imported before we add transactions to your account.
          </CardDescription>
        </CardHeader>
        <CardContent className="flex-1 min-h-0 flex flex-col gap-4">
          {balanceVerification?.hasBalanceData && (
            <div
              className={cn(
                "rounded-lg border p-4",
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
              {balanceVerification.hasBalanceData && (
                <p className="mt-2 text-xs text-muted-foreground">
                  Daily balances from the CSV will be used to update the account balance history.
                </p>
              )}
            </div>
          )}

          <Tabs defaultValue="to-import" className="flex min-h-0 flex-1 flex-col">
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
        </CardContent>
        <CardFooter className="flex justify-between">
          <Button
            type="button"
            variant="outline"
            onClick={() => router.push(`/step-4/mapping?id=${importId ?? ""}`)}
          >
            <RiArrowLeftLine className="mr-2 h-4 w-4" />
            Back to Mapping
          </Button>
          <Button
            onClick={handleImport}
            disabled={isImporting || selectedIndices.length === 0 || hasStartedImport}
          >
            {isImporting ? "Importing..." : `Import ${selectedIndices.length} Transactions`}
            <RiCheckLine className="ml-2 h-4 w-4" />
          </Button>
        </CardFooter>
      </Card>

      <Dialog open={showSuccessModal} onOpenChange={setShowSuccessModal}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Your first account is being created!</DialogTitle>
            <DialogDescription>
              This can take a few minutes depending on the number of transactions.
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-4">
            <div className="rounded-lg border bg-muted/40 p-3">
              <p className="text-xs text-muted-foreground">
                Tip: Press Cmd + K anytime to open the command palette.
              </p>
            </div>

            <div className="space-y-2">
              <p className="text-xs font-medium text-muted-foreground">Shortcuts</p>
              <div className="grid gap-2 sm:grid-cols-2">
                {SHORTCUTS.map((shortcut) => (
                  <div
                    key={`${shortcut.label}-${shortcut.keys.join("-")}`}
                    className="flex items-center justify-between rounded border bg-background px-3 py-2 text-xs"
                  >
                    <span className="text-muted-foreground">{shortcut.label}</span>
                    <ShortcutKeys keys={shortcut.keys} />
                  </div>
                ))}
              </div>
            </div>

            <p className="text-xs text-muted-foreground">
              Press M to toggle the theme and try it out.
            </p>
          </div>

          <div className="flex justify-end">
            <Button
              onClick={() => {
                setShowSuccessModal(false);
                router.push("/?tour=1");
              }}
            >
              Get Started
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}

export default function PreviewPage() {
  return (
    <Suspense
      fallback={
        <div className="space-y-8">
          <OnboardingProgress currentStep={4} />
          <Card className="min-h-[640px] h-[640px] flex flex-col">
            <CardContent className="flex items-center justify-center py-12">
              <div className="text-center">
                <div className="mx-auto mb-4 h-8 w-8 animate-spin rounded-full border-2 border-muted border-t-primary" />
                <p className="text-muted-foreground">Loading...</p>
              </div>
            </CardContent>
          </Card>
        </div>
      }
    >
      <PreviewPageContent />
    </Suspense>
  );
}
