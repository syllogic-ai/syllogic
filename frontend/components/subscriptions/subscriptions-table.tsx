"use client";

import { useState } from "react";
import { DataTable } from "@/components/ui/data-table";
import { Button } from "@/components/ui/button";
import { createSubscriptionColumns } from "./columns";
import { SubscriptionsSummaryRow } from "./subscriptions-summary-row";
import { RiAddLine } from "@remixicon/react";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import type { SubscriptionOrSuggestion } from "./subscriptions-client";

interface SubscriptionsTableProps {
  data: SubscriptionOrSuggestion[];
  onAdd: () => void;
  onEdit: (row: SubscriptionOrSuggestion) => void;
  onDelete: (row: SubscriptionOrSuggestion) => void;
  onToggleActive: (row: SubscriptionOrSuggestion) => void;
  onRowClick: (row: SubscriptionOrSuggestion) => void;
  onVerify: (row: SubscriptionOrSuggestion) => void;
  onDismiss: (row: SubscriptionOrSuggestion) => void;
}

export function SubscriptionsTable({
  data,
  onAdd,
  onEdit,
  onDelete,
  onToggleActive,
  onRowClick,
  onVerify,
  onDismiss,
}: SubscriptionsTableProps) {
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);
  const [rowToDelete, setRowToDelete] = useState<SubscriptionOrSuggestion | null>(null);

  const handleDeleteClick = (row: SubscriptionOrSuggestion) => {
    setRowToDelete(row);
    setDeleteDialogOpen(true);
  };

  const handleConfirmDelete = () => {
    if (rowToDelete) {
      onDelete(rowToDelete);
    }
    setDeleteDialogOpen(false);
    setRowToDelete(null);
  };

  // Count only verified subscriptions (not suggestions)
  const subscriptionCount = data.filter((d) => !d.isSuggestion).length;
  const suggestionCount = data.filter((d) => d.isSuggestion).length;

  const columns = createSubscriptionColumns({
    onEdit,
    onDelete: handleDeleteClick,
    onToggleActive,
    onVerify,
    onDismiss,
  });

  return (
    <>
      <DataTable
        columns={columns}
        data={data}
        onRowClick={onRowClick}
        enableColumnResizing={true}
        enableRowSelection={false}
        enablePagination={true}
        pageSize={20}
        toolbar={() => (
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <h2 className="text-lg font-semibold">Subscriptions</h2>
              <span className="text-sm text-muted-foreground">
                ({subscriptionCount})
              </span>
              {suggestionCount > 0 && (
                <span className="text-sm text-yellow-600">
                  +{suggestionCount} suggestion{suggestionCount !== 1 ? "s" : ""}
                </span>
              )}
            </div>
            <Button onClick={onAdd}>
              <RiAddLine className="mr-2 h-4 w-4" />
              Add Subscription
            </Button>
          </div>
        )}
        footer={<SubscriptionsSummaryRow data={data} />}
      />

      {/* Delete Confirmation Dialog */}
      <AlertDialog open={deleteDialogOpen} onOpenChange={setDeleteDialogOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete Subscription?</AlertDialogTitle>
            <AlertDialogDescription>
              Are you sure you want to delete "{rowToDelete?.name}"? This
              action cannot be undone. Linked transactions will be unlinked but not
              deleted.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
              onClick={handleConfirmDelete}
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
            >
              Delete
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  );
}
