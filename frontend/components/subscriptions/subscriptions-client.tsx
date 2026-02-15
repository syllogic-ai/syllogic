"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { SubscriptionsGroupedList } from "./subscriptions-grouped-list";
import { SubscriptionFormDialog } from "./subscription-form-dialog";
import { SubscriptionDetailSheet } from "./subscription-detail-sheet";
import { toast } from "sonner";
import {
  deleteSubscription,
  toggleSubscriptionActive,
  type SubscriptionKpis,
} from "@/lib/actions/subscriptions";
import {
  dismissSuggestion,
  type SubscriptionSuggestionWithMeta,
} from "@/lib/actions/subscription-suggestions";
import type { RecurringTransaction } from "@/lib/db/schema";
import { withAssetVersion } from "@/lib/utils/asset-url";

interface SubscriptionWithCategory extends RecurringTransaction {
  category?: {
    id: string;
    name: string;
    color: string | null;
  } | null;
  logo?: {
    id: string;
    logoUrl: string | null;
    updatedAt?: Date | null;
  } | null;
}

// Extended type for table rows that can be either a subscription or a suggestion
export interface SubscriptionOrSuggestion {
  id: string;
  name: string;
  amount: string;
  currency: string | null;
  frequency: string;
  isActive?: boolean | null;
  isSuggestion?: boolean;
  confidence?: number;
  matchCount?: number;
  merchant?: string | null;
  importance?: number;
  category?: {
    id: string;
    name: string;
    color: string | null;
  } | null;
  logoUrl?: string | null;
}

interface SubscriptionsClientProps {
  initialSubscriptions: SubscriptionWithCategory[];
  categories: Array<{ id: string; name: string; color: string | null }>;
  suggestions?: SubscriptionSuggestionWithMeta[];
  kpis: SubscriptionKpis;
}

export function SubscriptionsClient({
  initialSubscriptions,
  categories,
  suggestions: initialSuggestions = [],
  kpis,
}: SubscriptionsClientProps) {
  const router = useRouter();
  const [subscriptions, setSubscriptions] = useState(initialSubscriptions);
  const [suggestions, setSuggestions] = useState(initialSuggestions);
  const [formDialogOpen, setFormDialogOpen] = useState(false);
  const [editingSubscription, setEditingSubscription] =
    useState<SubscriptionWithCategory | null>(null);
  const [verifyingSuggestion, setVerifyingSuggestion] =
    useState<SubscriptionSuggestionWithMeta | null>(null);
  const [detailSheetOpen, setDetailSheetOpen] = useState(false);
  const [selectedSubscription, setSelectedSubscription] =
    useState<SubscriptionWithCategory | null>(null);

  // Keep local state in sync with server-refreshes.
  // This prevents "stale" rows (e.g. missing logo relation) after router.refresh().
  useEffect(() => {
    setSubscriptions(initialSubscriptions);
  }, [initialSubscriptions]);

  useEffect(() => {
    setSuggestions(initialSuggestions);
  }, [initialSuggestions]);

  // Combine subscriptions and suggestions for table display
  // Order: Active subscriptions first, then suggestions, then inactive subscriptions
  const activeSubscriptions = subscriptions
    .filter((s) => s.isActive)
    .map((s) => ({
      ...s,
      isSuggestion: false,
      logoUrl: withAssetVersion(s.logo?.logoUrl, s.logo?.updatedAt),
    }));

  const inactiveSubscriptions = subscriptions
    .filter((s) => !s.isActive)
    .map((s) => ({
      ...s,
      isSuggestion: false,
      logoUrl: withAssetVersion(s.logo?.logoUrl, s.logo?.updatedAt),
    }));

  const suggestionRows = suggestions.map((s) => ({
    id: s.id,
    name: s.suggestedName,
    amount: s.suggestedAmount,
    currency: s.currency,
    frequency: s.detectedFrequency,
    isActive: null, // Suggestions don't have active status
    isSuggestion: true,
    confidence: s.confidence,
    matchCount: s.matchCount,
    category: null,
  }));

  const tableData: SubscriptionOrSuggestion[] = [
    // Active subscriptions first
    ...activeSubscriptions,
    // Then suggestions
    ...suggestionRows,
    // Then inactive subscriptions
    ...inactiveSubscriptions,
  ];

  const handleAdd = () => {
    setEditingSubscription(null);
    setVerifyingSuggestion(null);
    setFormDialogOpen(true);
  };

  const handleEdit = (subscription: SubscriptionWithCategory) => {
    setEditingSubscription(subscription);
    setVerifyingSuggestion(null);
    setFormDialogOpen(true);
  };

  const handleVerify = (row: SubscriptionOrSuggestion) => {
    // Find the suggestion to get full data
    const suggestion = suggestions.find((s) => s.id === row.id);
    if (suggestion) {
      setVerifyingSuggestion(suggestion);
      setEditingSubscription(null);
      setFormDialogOpen(true);
    }
  };

  const handleDismiss = async (row: SubscriptionOrSuggestion) => {
    const result = await dismissSuggestion(row.id);

    if (result.success) {
      toast.success("Suggestion dismissed");
      setSuggestions((prev) => prev.filter((s) => s.id !== row.id));
    } else {
      toast.error(result.error || "Failed to dismiss suggestion");
    }
  };

  const handleDelete = async (subscription: SubscriptionWithCategory) => {
    const result = await deleteSubscription(subscription.id);

    if (result.success) {
      toast.success("Subscription deleted");
      setSubscriptions((prev) => prev.filter((t) => t.id !== subscription.id));
      router.refresh();
    } else {
      toast.error(result.error || "Failed to delete");
    }
  };

  const handleToggleActive = async (
    subscription: SubscriptionWithCategory
  ) => {
    const newStatus = !subscription.isActive;
    const result = await toggleSubscriptionActive(
      subscription.id,
      newStatus
    );

    if (result.success) {
      toast.success(
        newStatus
          ? "Subscription activated"
          : "Subscription deactivated"
      );
      setSubscriptions((prev) =>
        prev.map((t) =>
          t.id === subscription.id ? { ...t, isActive: newStatus } : t
        )
      );
      router.refresh();
    } else {
      toast.error(result.error || "Failed to update status");
    }
  };

  const handleFormSuccess = (suggestionId?: string, subscriptionData?: SubscriptionWithCategory) => {
    // If we were verifying a suggestion, remove it from the list
    if (suggestionId) {
      setSuggestions((prev) => prev.filter((s) => s.id !== suggestionId));
    }

    if (subscriptionData) {
      // Check if this is an update (subscription exists) or a new subscription
      const existingIndex = subscriptions.findIndex((s) => s.id === subscriptionData.id);
      if (existingIndex >= 0) {
        // Update existing subscription in the list
        setSubscriptions((prev) =>
          prev.map((s) => (s.id === subscriptionData.id ? subscriptionData : s))
        );
      } else {
        // Add new subscription to the list
        setSubscriptions((prev) => [...prev, subscriptionData]);
      }
    }

    setVerifyingSuggestion(null);
    router.refresh();
  };

  const handleRowClick = (row: SubscriptionOrSuggestion) => {
    // Don't open detail sheet for suggestions
    if (row.isSuggestion) {
      return;
    }
    // Find the full subscription data
    const subscription = subscriptions.find((s) => s.id === row.id);
    if (subscription) {
      setSelectedSubscription(subscription);
      setDetailSheetOpen(true);
    }
  };

  const handleEditFromDetail = (subscription: SubscriptionWithCategory) => {
    setDetailSheetOpen(false);
    handleEdit(subscription);
  };

  return (
    <>
      <SubscriptionsGroupedList
        data={tableData}
        kpis={kpis}
        onAdd={handleAdd}
        onEdit={(row) => {
          const subscription = subscriptions.find((s) => s.id === row.id);
          if (subscription) handleEdit(subscription);
        }}
        onDelete={(row) => {
          const subscription = subscriptions.find((s) => s.id === row.id);
          if (subscription) handleDelete(subscription);
        }}
        onToggleActive={(row) => {
          const subscription = subscriptions.find((s) => s.id === row.id);
          if (subscription) handleToggleActive(subscription);
        }}
        onRowClick={handleRowClick}
        onVerify={handleVerify}
        onDismiss={handleDismiss}
      />

      <SubscriptionFormDialog
        open={formDialogOpen}
        onOpenChange={setFormDialogOpen}
        subscription={editingSubscription}
        suggestion={verifyingSuggestion}
        categories={categories}
        onSuccess={handleFormSuccess}
      />

      <SubscriptionDetailSheet
        subscription={selectedSubscription}
        open={detailSheetOpen}
        onOpenChange={setDetailSheetOpen}
        onEdit={handleEditFromDetail}
        onRefresh={() => router.refresh()}
      />
    </>
  );
}
