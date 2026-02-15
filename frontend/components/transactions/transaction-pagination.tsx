"use client";

import { type Table } from "@tanstack/react-table";
import { Button } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  RiArrowLeftSLine,
  RiArrowRightSLine,
  RiSkipLeftLine,
  RiSkipRightLine,
} from "@remixicon/react";
import type { TransactionWithRelations } from "@/lib/actions/transactions";

interface TransactionPaginationProps {
  table: Table<TransactionWithRelations>;
  totalCount?: number;
  page?: number;
  pageSize?: number;
  onPageChange?: (page: number) => void;
  onPageSizeChange?: (pageSize: number) => void;
}

export function TransactionPagination({
  table,
  totalCount,
  page,
  pageSize,
  onPageChange,
  onPageSizeChange,
}: TransactionPaginationProps) {
  const legacyPageSize = table.getState().pagination.pageSize;
  const legacyPage = table.getState().pagination.pageIndex + 1;
  const legacyTotalCount = table.getFilteredRowModel().rows.length;
  const resolvedPageSize = pageSize ?? legacyPageSize;
  const resolvedPage = page ?? legacyPage;
  const resolvedTotalCount = totalCount ?? legacyTotalCount;
  const pageCount = totalCount
    ? Math.max(1, Math.ceil(totalCount / resolvedPageSize))
    : Math.max(1, table.getPageCount());
  const selectedRows = table.getSelectedRowModel().rows.length;
  const currentPageRows = table.getRowModel().rows.length;
  const startRow = resolvedTotalCount === 0 ? 0 : (resolvedPage - 1) * resolvedPageSize + 1;
  const endRow = resolvedTotalCount === 0
    ? 0
    : Math.min(resolvedTotalCount, (resolvedPage - 1) * resolvedPageSize + currentPageRows);
  const canPrevious = totalCount ? resolvedPage > 1 : table.getCanPreviousPage();
  const canNext = totalCount ? resolvedPage < pageCount : table.getCanNextPage();
  const goToPage = (nextPage: number) => {
    if (onPageChange) {
      onPageChange(nextPage);
      return;
    }
    table.setPageIndex(Math.max(0, nextPage - 1));
  };
  const setRowsPerPage = (nextPageSize: number) => {
    if (onPageSizeChange) {
      onPageSizeChange(nextPageSize);
      return;
    }
    table.setPageSize(nextPageSize);
  };

  return (
    <div className="flex items-center justify-between py-4">
      <div className="flex items-center gap-4">
        <p className="text-xs text-muted-foreground">
          {selectedRows > 0 ? (
            <>
              {selectedRows} of {currentPageRows} row(s) selected
            </>
          ) : (
            <>
              {startRow}-{endRow} of {resolvedTotalCount} transaction{resolvedTotalCount !== 1 ? "s" : ""}
            </>
          )}
        </p>
      </div>

      <div className="flex items-center gap-4">
        <div className="flex items-center gap-2">
          <p className="text-xs text-muted-foreground">Rows per page</p>
          <Select
            value={resolvedPageSize.toString()}
            onValueChange={(value) => setRowsPerPage(Number(value))}
          >
            <SelectTrigger className="w-[70px]" size="sm">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {[10, 20, 30, 50, 100].map((size) => (
                <SelectItem key={size} value={size.toString()}>
                  {size}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        <div className="flex items-center gap-1">
          <p className="text-xs text-muted-foreground">
            Page {resolvedPage} of {pageCount}
          </p>
        </div>

        <div className="flex items-center gap-1">
          <Button
            variant="outline"
            size="icon"
            className="h-7 w-7"
            onClick={() => goToPage(1)}
            disabled={!canPrevious}
          >
            <RiSkipLeftLine className="h-4 w-4" />
          </Button>
          <Button
            variant="outline"
            size="icon"
            className="h-7 w-7"
            onClick={() => goToPage(resolvedPage - 1)}
            disabled={!canPrevious}
          >
            <RiArrowLeftSLine className="h-4 w-4" />
          </Button>
          <Button
            variant="outline"
            size="icon"
            className="h-7 w-7"
            onClick={() => goToPage(resolvedPage + 1)}
            disabled={!canNext}
          >
            <RiArrowRightSLine className="h-4 w-4" />
          </Button>
          <Button
            variant="outline"
            size="icon"
            className="h-7 w-7"
            onClick={() => goToPage(pageCount)}
            disabled={!canNext}
          >
            <RiSkipRightLine className="h-4 w-4" />
          </Button>
        </div>
      </div>
    </div>
  );
}
