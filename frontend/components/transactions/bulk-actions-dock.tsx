"use client";

import { useState, useMemo } from "react";
import { toast } from "sonner";
import {
  RiPriceTag3Line,
  RiDownloadLine,
  RiCloseLine,
  RiDeleteBinLine,
  RiSearchLine,
} from "@remixicon/react";
import { Dock, DockIcon } from "@/components/ui/dock";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";
import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";
import { Input } from "@/components/ui/input";
import { bulkUpdateTransactionCategory } from "@/lib/actions/transactions";
import { exportTransactionsToCSV } from "@/lib/utils/csv-export";
import type { CategoryDisplay } from "@/types";
import type { TransactionWithRelations } from "@/lib/actions/transactions";

interface BulkActionsDockProps {
  selectedCount: number;
  selectedIds: string[];
  selectedTransactions: TransactionWithRelations[];
  categories: CategoryDisplay[];
  onClearSelection: () => void;
  onBulkUpdate: (categoryId: string | null) => void;
}

export function BulkActionsDock({
  selectedCount,
  selectedIds,
  selectedTransactions,
  categories,
  onClearSelection,
  onBulkUpdate,
}: BulkActionsDockProps) {
  const [isLoading, setIsLoading] = useState(false);
  const [categoryPopoverOpen, setCategoryPopoverOpen] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");

  const filteredCategories = useMemo(() => {
    if (!searchQuery.trim()) return categories;
    return categories.filter((cat) =>
      cat.name.toLowerCase().includes(searchQuery.toLowerCase())
    );
  }, [categories, searchQuery]);

  if (selectedCount === 0) {
    return null;
  }

  const handleCategorize = async (categoryId: string | null) => {
    setIsLoading(true);
    try {
      const result = await bulkUpdateTransactionCategory(selectedIds, categoryId);

      if (result.success) {
        toast.success(`Updated ${result.updatedCount} transactions`);
        onBulkUpdate(categoryId);
        onClearSelection();
        setCategoryPopoverOpen(false);
      } else {
        toast.error(result.error || "Failed to update transactions");
      }
    } catch {
      toast.error("An error occurred. Please try again.");
    } finally {
      setIsLoading(false);
    }
  };

  const handleExport = () => {
    if (selectedTransactions.length === 0) {
      toast.error("No transactions to export");
      return;
    }

    try {
      exportTransactionsToCSV(selectedTransactions);
      toast.success(`Exported ${selectedTransactions.length} transactions`);
    } catch {
      toast.error("Failed to export transactions");
    }
  };

  return (
    <div className="fixed bottom-6 left-1/2 -translate-x-1/2 z-50">
      <Dock
        direction="middle"
        className="h-14 px-4 gap-3 bg-background/95 border shadow-lg"
        disableMagnification
      >
        {/* Selection count */}
        <div className="flex items-center gap-2 px-2 text-sm font-medium">
          <span>{selectedCount} selected</span>
        </div>

        <Separator orientation="vertical" className="h-8" />

        {/* Categorize */}
        <Popover
          open={categoryPopoverOpen}
          onOpenChange={(open) => {
            setCategoryPopoverOpen(open);
            if (!open) setSearchQuery("");
          }}
        >
          <PopoverTrigger
            render={<DockIcon className="bg-muted hover:bg-muted/80" />}
          >
            <RiPriceTag3Line className="size-5" />
          </PopoverTrigger>
          <PopoverContent className="w-56 p-0" align="center" side="top" sideOffset={12}>
            <div className="p-2 border-b space-y-2">
              <p className="text-xs font-medium text-muted-foreground">
                Select category
              </p>
              <div className="relative">
                <RiSearchLine className="absolute left-2 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                <Input
                  placeholder="Search..."
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  className="h-8 pl-8 text-sm"
                />
              </div>
            </div>
            <div className="max-h-48 overflow-y-auto p-1">
              <Button
                variant="ghost"
                size="sm"
                className="w-full justify-start text-muted-foreground"
                onClick={() => handleCategorize(null)}
                disabled={isLoading}
              >
                <RiDeleteBinLine className="mr-2 h-4 w-4" />
                Remove category
              </Button>
              {filteredCategories.map((category) => (
                <Button
                  key={category.id}
                  variant="ghost"
                  size="sm"
                  className="w-full justify-start"
                  onClick={() => handleCategorize(category.id)}
                  disabled={isLoading}
                >
                  <div
                    className="mr-2 h-3 w-3 rounded-full shrink-0"
                    style={{ backgroundColor: category.color || "#666" }}
                  />
                  <span className="truncate">{category.name}</span>
                </Button>
              ))}
              {filteredCategories.length === 0 && searchQuery && (
                <p className="text-xs text-muted-foreground text-center py-2">
                  No categories found
                </p>
              )}
            </div>
          </PopoverContent>
        </Popover>

        {/* Export */}
        <Tooltip>
          <TooltipTrigger
            render={
              <DockIcon
                className="bg-muted hover:bg-muted/80"
                onClick={handleExport}
              />
            }
          >
            <RiDownloadLine className="size-5" />
          </TooltipTrigger>
          <TooltipContent side="top" sideOffset={8}>
            <p>Export CSV</p>
          </TooltipContent>
        </Tooltip>

        <Separator orientation="vertical" className="h-8" />

        {/* Clear selection */}
        <Tooltip>
          <TooltipTrigger
            render={
              <DockIcon
                className="bg-muted hover:bg-destructive/20 hover:text-destructive"
                onClick={onClearSelection}
              />
            }
          >
            <RiCloseLine className="size-5" />
          </TooltipTrigger>
          <TooltipContent side="top" sideOffset={8}>
            <p>Clear selection</p>
          </TooltipContent>
        </Tooltip>
      </Dock>
    </div>
  );
}
