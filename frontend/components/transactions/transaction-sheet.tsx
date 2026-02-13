"use client";

import { useState, useEffect, useRef } from "react";
import { useRouter } from "next/navigation";
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetDescription,
} from "@/components/ui/sheet";
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
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Button } from "@/components/ui/button";
import {
  Select,
  SelectTrigger,
  SelectValue,
  SelectContent,
  SelectItem,
} from "@/components/ui/select";
import { Separator } from "@/components/ui/separator";
import { cn, formatDate, formatAmount } from "@/lib/utils";
import type { TransactionWithRelations } from "@/lib/actions/transactions";
import { updateTransactionCategory, updateTransactionIncludeInAnalytics, deleteBalancingTransaction } from "@/lib/actions/transactions";
import { Switch } from "@/components/ui/switch";
import type { CategoryDisplay } from "@/types";
import { filterSelectableCategories } from "@/lib/utils/category-utils";
import { RiDeleteBinLine, RiLoopRightLine } from "@remixicon/react";
import { toast } from "sonner";
import { SubscriptionDetectionDialog } from "./subscription-detection-dialog";
import { SubscriptionLinkedDialog } from "./subscription-linked-dialog";
import { LinkReimbursementsDialog } from "./link-reimbursements-dialog";
import { LinkedTransactionsSection } from "./linked-transactions-section";

interface TransactionSheetProps {
  transaction: TransactionWithRelations | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onUpdateTransaction?: (id: string, updates: Partial<TransactionWithRelations>) => void;
  onDeleteTransaction?: (id: string) => void;
  categories?: CategoryDisplay[];
}

export function TransactionSheet({
  transaction,
  open,
  onOpenChange,
  onUpdateTransaction,
  onDeleteTransaction,
  categories = [],
}: TransactionSheetProps) {
  const router = useRouter();
  // Filter out categories hidden from manual selection (e.g., Balancing Transfer)
  const selectableCategories = filterSelectableCategories(categories);

  const [selectedCategoryId, setSelectedCategoryId] = useState<string | null>(null);
  const [includeInAnalytics, setIncludeInAnalytics] = useState<boolean>(true);
  const [instructions, setInstructions] = useState<string>("");
  const [hasChanges, setHasChanges] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [isReverting, setIsReverting] = useState(false);
  const [isTogglingAnalytics, setIsTogglingAnalytics] = useState(false);
  const [showSubscriptionDialog, setShowSubscriptionDialog] = useState(false);
  const [showLinkedSubscriptionDialog, setShowLinkedSubscriptionDialog] = useState(false);
  const [showLinkReimbursementsDialog, setShowLinkReimbursementsDialog] = useState(false);

  const isBalancingTransfer = transaction?.category?.name === "Balancing Transfer";
  const isExpense = transaction?.transactionType === "debit";
  const hasLinkedSubscription = !!transaction?.recurringTransactionId;

  // Track previous transaction ID to only reset state when a different transaction is opened
  const prevTransactionIdRef = useRef<string | null>(null);

  const handleRevertBalancingTransfer = async () => {
    if (!transaction) return;

    setIsReverting(true);
    try {
      const result = await deleteBalancingTransaction(transaction.id);

      if (result.success) {
        toast.success("Balancing transfer reverted successfully");
        onDeleteTransaction?.(transaction.id);
        onOpenChange(false);
      } else {
        toast.error(result.error || "Failed to revert balancing transfer");
      }
    } catch (error) {
      toast.error("Failed to revert balancing transfer");
    } finally {
      setIsReverting(false);
    }
  };

  // Reset state only when a different transaction is opened (not when same transaction updates)
  useEffect(() => {
    if (transaction && transaction.id !== prevTransactionIdRef.current) {
      prevTransactionIdRef.current = transaction.id;
      setSelectedCategoryId(transaction.categoryId);
      setIncludeInAnalytics(transaction.includeInAnalytics ?? true);
      setInstructions("");
      setHasChanges(false);
    }
  }, [transaction]);

  // Reset ref when sheet closes so reopening same transaction reinitializes properly
  useEffect(() => {
    if (!open) {
      prevTransactionIdRef.current = null;
    }
  }, [open]);

  const handleCategoryChange = (value: string | null) => {
    if (!value) return;
    const newCategoryId = value === "uncategorized" ? null : value;
    setSelectedCategoryId(newCategoryId);
    setHasChanges(newCategoryId !== transaction?.categoryId);
  };

  const handleInstructionsChange = (value: string) => {
    setInstructions(value);
  };

  const handleIncludeInAnalyticsChange = async (checked: boolean) => {
    if (!transaction) return;

    setIsTogglingAnalytics(true);
    try {
      const result = await updateTransactionIncludeInAnalytics(transaction.id, checked);

      if (result.success) {
        setIncludeInAnalytics(checked);
        onUpdateTransaction?.(transaction.id, {
          includeInAnalytics: checked,
        });
        toast.success(checked ? "Transaction included in analytics" : "Transaction excluded from analytics");
      } else {
        toast.error(result.error || "Failed to update transaction");
      }
    } catch {
      toast.error("Failed to update transaction");
    } finally {
      setIsTogglingAnalytics(false);
    }
  };

  const handleSave = async () => {
    if (!transaction || !hasChanges) return;

    setIsSaving(true);
    try {
      const result = await updateTransactionCategory(transaction.id, selectedCategoryId);

      if (result.success) {
        const newCategory = selectedCategoryId
          ? categories.find((cat) => cat.id === selectedCategoryId) || null
          : null;

        onUpdateTransaction?.(transaction.id, {
          categoryId: selectedCategoryId,
          category: newCategory,
        });

        setHasChanges(false);
      }
    } finally {
      setIsSaving(false);
    }
  };

  const handleSubscriptionSuccess = () => {
    // Refresh the transaction to show updated subscription link
    onOpenChange(false);
    router.refresh();
  };

  const handleSubscriptionButtonClick = () => {
    if (hasLinkedSubscription) {
      setShowLinkedSubscriptionDialog(true);
    } else {
      setShowSubscriptionDialog(true);
    }
  };

  if (!transaction) return null;

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent side="right" className="sm:max-w-md flex flex-col h-full overflow-hidden px-2.5">
        {/* Fixed Header */}
        <SheetHeader className="space-y-1 p-0 pt-4 shrink-0">
          <SheetDescription className="text-muted-foreground">
            {formatDate(transaction.bookedAt)}
          </SheetDescription>
          <SheetTitle className="text-lg font-medium break-all">
            {transaction.description}
          </SheetTitle>
          <div
            className={cn(
              "text-3xl font-semibold tracking-tight pt-2",
              transaction.amount > 0 && "text-[#22C55E]"
            )}
          >
            {formatAmount(transaction.amount, transaction.currency || "EUR")}
          </div>
        </SheetHeader>

        <Separator className="my-4 shrink-0" />

        {/* Scrollable Content */}
        <div className="flex-1 overflow-y-auto overflow-x-hidden min-h-0 space-y-6 pr-1">
          {/* Category Section */}
          <div className="space-y-3">
            <Label htmlFor="category">Category</Label>
            <Select
              value={selectedCategoryId || "uncategorized"}
              onValueChange={handleCategoryChange}
            >
              <SelectTrigger id="category" className="w-full">
                <SelectValue placeholder="Select category">
                  {selectedCategoryId ? (
                    <div className="flex items-center gap-2">
                      <div
                        className="h-3 w-3 shrink-0"
                        style={{
                          backgroundColor:
                            categories.find((c) => c.id === selectedCategoryId)?.color ||
                            "#A1A1AA",
                        }}
                      />
                      <span>
                        {categories.find((c) => c.id === selectedCategoryId)?.name ||
                          "Unknown"}
                      </span>
                    </div>
                  ) : (
                    <div className="flex items-center gap-2">
                      <div className="h-3 w-3 shrink-0 bg-muted-foreground/30" />
                      <span className="text-muted-foreground">Uncategorized</span>
                    </div>
                  )}
                </SelectValue>
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="uncategorized">
                  <div className="flex items-center gap-2">
                    <div className="h-3 w-3 shrink-0 bg-muted-foreground/30" />
                    <span>Uncategorized</span>
                  </div>
                </SelectItem>
                {selectableCategories.map((category) => (
                  <SelectItem key={category.id} value={category.id}>
                    <div className="flex items-center gap-2">
                      <div
                        className="h-3 w-3 shrink-0"
                        style={{ backgroundColor: category.color || "#A1A1AA" }}
                      />
                      <span>{category.name}</span>
                    </div>
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            {/* Show AI-assigned category if different from user selection */}
            {transaction.categorySystemId &&
              transaction.categorySystemId !== selectedCategoryId && (
                <p className="text-xs text-muted-foreground flex items-center gap-1.5">
                  <span>AI suggested:</span>
                  <span
                    className="inline-flex items-center gap-1"
                  >
                    <span
                      className="h-2 w-2 shrink-0 inline-block"
                      style={{ backgroundColor: transaction.categorySystem?.color || "#A1A1AA" }}
                    />
                    {transaction.categorySystem?.name || "Unknown"}
                  </span>
                </p>
              )}
          </div>

          {/* Linked Transactions Section */}
          {!isBalancingTransfer && (
            <LinkedTransactionsSection
              transactionId={transaction.id}
              currency={transaction.currency || "EUR"}
              onLinkClick={() => setShowLinkReimbursementsDialog(true)}
              onUpdate={handleSubscriptionSuccess}
            />
          )}

          {/* Categorization Instructions */}
          <div className="space-y-3">
            <Label htmlFor="instructions">Categorization Instructions</Label>
            <Textarea
              id="instructions"
              placeholder="Add instructions for how this merchant or similar transactions should be categorized in the future..."
              value={instructions}
              onChange={(e) => handleInstructionsChange(e.target.value)}
              className="min-h-[100px] resize-none"
            />
          </div>

          {/* Include in Analytics Toggle */}
          <div className="flex items-center justify-between">
            <div className="space-y-0.5">
              <Label htmlFor="include-analytics">Include in Analytics</Label>
              <p className="text-xs text-muted-foreground">
                When disabled, this transaction won&apos;t appear in charts or reports
              </p>
            </div>
            <Switch
              id="include-analytics"
              checked={includeInAnalytics}
              onCheckedChange={handleIncludeInAnalyticsChange}
              disabled={isTogglingAnalytics}
            />
          </div>

          <Separator />

          {/* Transaction Details */}
          <div className="space-y-4 pb-2">
            <h3 className="text-sm font-medium">Details</h3>

            <div className="grid gap-3 text-sm">
              <div className="flex justify-between">
                <span className="text-muted-foreground">Merchant</span>
                <span>{transaction.merchant || "-"}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-muted-foreground">Account</span>
                <span>{transaction.account?.name || "Unknown"}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-muted-foreground">Institution</span>
                <span>{transaction.account?.institution || "—"}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-muted-foreground">Status</span>
                <span>{transaction.pending ? "Pending" : "Completed"}</span>
              </div>
            </div>
          </div>
        </div>

        {/* Fixed Footer with Save Button, Subscription Button and Revert Option */}
        <div className="pt-4 pb-4 border-t space-y-3 shrink-0 mt-auto">
          {/* Subscription button - only show for expenses and not balancing transfers */}
          {isExpense && !isBalancingTransfer && (
            <Button
              variant="outline"
              className="w-full"
              onClick={handleSubscriptionButtonClick}
            >
              <RiLoopRightLine className="h-4 w-4 mr-2" />
              {hasLinkedSubscription
                ? `Linked: ${transaction.recurringTransaction?.name}`
                : "Mark as Subscription"}
            </Button>
          )}

          <Button
            onClick={handleSave}
            disabled={!hasChanges || isSaving}
            className="w-full"
          >
            {isSaving ? "Saving..." : "Save Changes"}
          </Button>

          {/* Revert button for balancing transfers */}
          {isBalancingTransfer && (
            <AlertDialog>
              <AlertDialogTrigger
                disabled={isReverting}
                render={
                  <Button
                    variant="destructive"
                    className="w-full"
                    disabled={isReverting}
                  >
                    <RiDeleteBinLine className="h-4 w-4 mr-2" />
                    {isReverting ? "Reverting..." : "Revert Balancing Transfer"}
                  </Button>
                }
              />
              <AlertDialogContent>
                <AlertDialogHeader>
                  <AlertDialogTitle>Revert Balancing Transfer?</AlertDialogTitle>
                  <AlertDialogDescription>
                    This will delete the balancing transfer and recalculate the account balance
                    as if this adjustment never existed. This action cannot be undone.
                  </AlertDialogDescription>
                </AlertDialogHeader>
                <AlertDialogFooter>
                  <AlertDialogCancel>Cancel</AlertDialogCancel>
                  <AlertDialogAction
                    onClick={handleRevertBalancingTransfer}
                    className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
                  >
                    Revert
                  </AlertDialogAction>
                </AlertDialogFooter>
              </AlertDialogContent>
            </AlertDialog>
          )}
        </div>
      </SheetContent>

      {/* Subscription Detection Dialog */}
      <SubscriptionDetectionDialog
        transaction={transaction}
        open={showSubscriptionDialog}
        onOpenChange={setShowSubscriptionDialog}
        onSuccess={handleSubscriptionSuccess}
        categories={categories}
      />

      {/* Linked Subscription Dialog */}
      <SubscriptionLinkedDialog
        transaction={transaction}
        open={showLinkedSubscriptionDialog}
        onOpenChange={setShowLinkedSubscriptionDialog}
        onSuccess={handleSubscriptionSuccess}
      />

      {/* Link Reimbursements Dialog */}
      <LinkReimbursementsDialog
        transaction={transaction}
        open={showLinkReimbursementsDialog}
        onOpenChange={setShowLinkReimbursementsDialog}
        onSuccess={handleSubscriptionSuccess}
      />
    </Sheet>
  );
}
