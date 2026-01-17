"use client";

import { useState, useEffect } from "react";
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetDescription,
} from "@/components/ui/sheet";
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
import { cn } from "@/lib/utils";
import type { TransactionWithRelations } from "@/lib/actions/transactions";
import { updateTransactionCategory } from "@/lib/actions/transactions";

interface Category {
  id: string;
  name: string;
  color: string | null;
  icon: string | null;
}

interface TransactionSheetProps {
  transaction: TransactionWithRelations | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onUpdateTransaction?: (id: string, updates: Partial<TransactionWithRelations>) => void;
  categories?: Category[];
}

function formatDate(date: Date): string {
  return new Intl.DateTimeFormat("en-GB", {
    month: "short",
    day: "numeric",
    year: "numeric",
  }).format(date);
}

function formatAmount(amount: number, currency: string): string {
  const formatted = new Intl.NumberFormat("nl-NL", {
    style: "currency",
    currency: currency,
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(Math.abs(amount));

  return amount < 0 ? `-${formatted}` : formatted;
}

export function TransactionSheet({
  transaction,
  open,
  onOpenChange,
  onUpdateTransaction,
  categories = [],
}: TransactionSheetProps) {
  const [selectedCategoryId, setSelectedCategoryId] = useState<string | null>(null);
  const [instructions, setInstructions] = useState<string>("");
  const [hasChanges, setHasChanges] = useState(false);
  const [isSaving, setIsSaving] = useState(false);

  // Reset state when transaction changes
  useEffect(() => {
    if (transaction) {
      setSelectedCategoryId(transaction.categoryId);
      setInstructions("");
      setHasChanges(false);
    }
  }, [transaction]);

  const handleCategoryChange = (value: string | null) => {
    if (!value) return;
    const newCategoryId = value === "uncategorized" ? null : value;
    setSelectedCategoryId(newCategoryId);
    setHasChanges(newCategoryId !== transaction?.categoryId);
  };

  const handleInstructionsChange = (value: string) => {
    setInstructions(value);
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

  if (!transaction) return null;

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent side="right" className="sm:max-w-md overflow-y-auto px-2.5">
        <SheetHeader className="space-y-1 p-0 pt-4">
          <SheetDescription className="text-muted-foreground">
            {formatDate(transaction.bookedAt)}
          </SheetDescription>
          <SheetTitle className="text-lg font-medium">
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

        <Separator className="my-6" />

        <div className="space-y-6">
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
                {categories.map((category) => (
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

          <Separator />

          {/* Transaction Details */}
          <div className="space-y-4">
            <h3 className="text-sm font-medium">Details</h3>

            <div className="grid gap-3 text-sm">
              <div className="flex justify-between">
                <span className="text-muted-foreground">Merchant</span>
                <span>{transaction.merchant || "-"}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-muted-foreground">Account</span>
                <span>{transaction.account.name}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-muted-foreground">Institution</span>
                <span>{transaction.account.institution}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-muted-foreground">Status</span>
                <span>{transaction.pending ? "Pending" : "Completed"}</span>
              </div>
            </div>
          </div>
        </div>

        {/* Footer with Save Button */}
        <div className="mt-6 pt-4 border-t">
          <Button
            onClick={handleSave}
            disabled={!hasChanges || isSaving}
            className="w-full"
          >
            {isSaving ? "Saving..." : "Save Changes"}
          </Button>
        </div>
      </SheetContent>
    </Sheet>
  );
}
