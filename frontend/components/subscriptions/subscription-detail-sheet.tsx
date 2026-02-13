"use client";

import { useState, useEffect } from "react";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";
import { ScrollArea } from "@/components/ui/scroll-area";
import {
  RiEditLine,
  RiLink,
  RiLoader4Line,
  RiRepeatLine,
} from "@remixicon/react";
import { format } from "date-fns";
import { toast } from "sonner";
import type { RecurringTransaction } from "@/lib/db/schema";
import {
  getSubscriptionCostAggregations,
  getLinkedTransactions,
  matchTransactionsToSubscription,
} from "@/lib/actions/subscriptions";

interface SubscriptionWithCategory extends RecurringTransaction {
  category?: {
    id: string;
    name: string;
    color: string | null;
  } | null;
}

interface LinkedTransaction {
  id: string;
  merchant: string | null;
  description: string | null;
  amount: string;
  bookedAt: Date;
  account: {
    name: string;
  };
}

interface SubscriptionDetailSheetProps {
  subscription: SubscriptionWithCategory | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onEdit: (subscription: SubscriptionWithCategory) => void;
  onRefresh: () => void;
}

const frequencyColors: Record<string, string> = {
  monthly: "bg-blue-500/10 text-blue-700 dark:text-blue-400",
  weekly: "bg-green-500/10 text-green-700 dark:text-green-400",
  yearly: "bg-purple-500/10 text-purple-700 dark:text-purple-400",
  quarterly: "bg-orange-500/10 text-orange-700 dark:text-orange-400",
  biweekly: "bg-cyan-500/10 text-cyan-700 dark:text-cyan-400",
};

const frequencyLabels: Record<string, string> = {
  monthly: "Monthly",
  weekly: "Weekly",
  yearly: "Yearly",
  quarterly: "Quarterly",
  biweekly: "Bi-weekly",
};

export function SubscriptionDetailSheet({
  subscription,
  open,
  onOpenChange,
  onEdit,
  onRefresh,
}: SubscriptionDetailSheetProps) {
  const [isLoading, setIsLoading] = useState(true);
  const [isMatching, setIsMatching] = useState(false);
  const [costAggregations, setCostAggregations] = useState<{
    thisYear: number;
    allTime: number;
  }>({ thisYear: 0, allTime: 0 });
  const [linkedTransactions, setLinkedTransactions] = useState<
    LinkedTransaction[]
  >([]);

  // Load data when subscription changes
  useEffect(() => {
    if (open && subscription) {
      loadData();
    }
  }, [open, subscription?.id]);

  const loadData = async () => {
    if (!subscription) return;

    setIsLoading(true);
    try {
      const [aggregations, transactions] = await Promise.all([
        getSubscriptionCostAggregations(subscription.id),
        getLinkedTransactions(subscription.id),
      ]);
      setCostAggregations(aggregations);
      setLinkedTransactions(transactions);
    } catch (error) {
      console.error("Failed to load subscription data:", error);
      toast.error("Failed to load subscription details");
    } finally {
      setIsLoading(false);
    }
  };

  const handleMatchTransactions = async () => {
    if (!subscription) return;

    setIsMatching(true);
    try {
      const result = await matchTransactionsToSubscription(subscription.id);

      if (result.success) {
        const matchedCount = result.matchedCount || 0;

        if (matchedCount === 0) {
          // Provide context based on whether there are already linked transactions
          if (linkedTransactions.length > 0) {
            toast.info(
              `All ${linkedTransactions.length} transaction(s) are already linked to "${subscription.name}"`
            );
          } else {
            toast.info("No matching transactions found");
          }
        } else {
          toast.success(
            `Matched ${matchedCount} new transaction(s) to "${subscription.name}"`
          );
        }
        // Reload data to show new matches
        await loadData();
        onRefresh();
      } else {
        toast.error(result.error || "Failed to match transactions");
      }
    } catch (error) {
      toast.error("Failed to match transactions");
    } finally {
      setIsMatching(false);
    }
  };

  const handleEdit = () => {
    if (subscription) {
      onEdit(subscription);
    }
  };

  if (!subscription) return null;

  const currency = subscription.currency || "EUR";

  // Cap importance at 3 for display
  const importance = Math.min(subscription.importance, 3);

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent className="w-full sm:max-w-lg flex flex-col px-6">
        <SheetHeader className="space-y-3 px-0">
          <div className="flex flex-wrap items-center gap-2">
            <Badge
              variant="secondary"
              className={frequencyColors[subscription.frequency]}
            >
              <RiRepeatLine className="mr-1 h-3 w-3" />
              {frequencyLabels[subscription.frequency] || subscription.frequency}
            </Badge>
            {subscription.category && (
              <Badge
                variant="secondary"
                className="text-white"
                style={{ backgroundColor: subscription.category.color ?? "#6B7280" }}
              >
                {subscription.category.name}
              </Badge>
            )}
          </div>
          <SheetTitle className="text-xl">{subscription.name}</SheetTitle>
          <div className="flex items-center justify-between">
            <SheetDescription className="text-base font-mono">
              {parseFloat(subscription.amount).toFixed(2)} {currency}
            </SheetDescription>
            {/* Importance blocks */}
            <div
              className="flex items-center gap-1 cursor-default"
              title={importance === 3 ? "High importance" : importance === 2 ? "Medium importance" : "Low importance"}
            >
              {Array.from({ length: 3 }).map((_, i) => (
                <div
                  key={i}
                  className={`h-3 w-5 border ${
                    i < importance
                      ? "bg-foreground border-foreground"
                      : "bg-background border-border"
                  }`}
                />
              ))}
            </div>
          </div>
        </SheetHeader>

        {isLoading ? (
          <div className="flex-1 flex items-center justify-center">
            <RiLoader4Line className="h-6 w-6 animate-spin text-muted-foreground" />
          </div>
        ) : (
          <div className="flex-1 flex flex-col gap-6 mt-6 min-h-0 overflow-hidden">
            {/* Cost Aggregations */}
            <div className="grid grid-cols-2 gap-4">
              <div className="bg-muted/50 p-4 space-y-1">
                <div className="text-xs text-muted-foreground uppercase tracking-wider">
                  This Year
                </div>
                <div className="text-xl font-mono font-medium">
                  {costAggregations.thisYear.toFixed(2)} {currency}
                </div>
              </div>
              <div className="bg-muted/50 p-4 space-y-1">
                <div className="text-xs text-muted-foreground uppercase tracking-wider">
                  All Time
                </div>
                <div className="text-xl font-mono font-medium">
                  {costAggregations.allTime.toFixed(2)} {currency}
                </div>
              </div>
            </div>

            {/* Actions */}
            <div className="flex gap-2">
              <Button
                variant="outline"
                className="flex-1"
                onClick={handleMatchTransactions}
                disabled={isMatching}
              >
                <RiLink className="mr-2 h-4 w-4" />
                {isMatching ? "Matching..." : "Match Transactions"}
              </Button>
              <Button variant="outline" onClick={handleEdit}>
                <RiEditLine className="mr-2 h-4 w-4" />
                Edit
              </Button>
            </div>

            <Separator />

            {/* Linked Transactions */}
            <div className="flex-1 flex flex-col min-h-0">
              <div className="flex items-center justify-between mb-3">
                <h3 className="text-sm font-medium">
                  Linked Transactions ({linkedTransactions.length})
                </h3>
              </div>

              {linkedTransactions.length === 0 ? (
                <div className="flex-1 flex items-center justify-center text-sm text-muted-foreground">
                  No transactions linked yet
                </div>
              ) : (
                <ScrollArea className="flex-1 min-h-0">
                  <div className="space-y-1">
                    {linkedTransactions.map((txn) => (
                      <div
                        key={txn.id}
                        className="flex items-center justify-between py-2 hover:bg-muted/50"
                      >
                        <div className="min-w-0 flex-1">
                          <div className="text-sm truncate">
                            {txn.merchant || txn.description || "Transaction"}
                          </div>
                          <div className="text-xs text-muted-foreground">
                            {format(new Date(txn.bookedAt), "MMM d, yyyy")}
                          </div>
                        </div>
                        <div className="text-sm font-mono shrink-0 ml-4">
                          {Math.abs(parseFloat(txn.amount)).toFixed(2)} {currency}
                        </div>
                      </div>
                    ))}
                  </div>
                </ScrollArea>
              )}
            </div>
          </div>
        )}
      </SheetContent>
    </Sheet>
  );
}
