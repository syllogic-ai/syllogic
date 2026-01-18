"use client";

import * as React from "react";
import { type Table } from "@tanstack/react-table";
import { type DateRange } from "react-day-picker";
import {
  startOfDay,
  endOfDay,
  startOfWeek,
  endOfWeek,
  startOfMonth,
  endOfMonth,
  startOfQuarter,
  endOfQuarter,
  startOfYear,
  endOfYear,
  subDays,
  format,
} from "date-fns";
import { Input } from "@/components/ui/input";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Label } from "@/components/ui/label";
import { Separator } from "@/components/ui/separator";
import { Calendar } from "@/components/ui/calendar";
import {
  RiSearchLine,
  RiFilter3Line,
  RiPriceTag3Line,
  RiBankLine,
  RiTimeLine,
  RiCalendarLine,
  RiMoneyDollarCircleLine,
  RiArrowDownSLine,
  RiCloseLine,
} from "@remixicon/react";
import type { TransactionWithRelations } from "@/lib/actions/transactions";
import type { CategoryForFilter, AccountForFilter } from "@/types";
import { cn } from "@/lib/utils";

interface TransactionFiltersProps {
  table: Table<TransactionWithRelations>;
  categories: CategoryForFilter[];
  accounts: AccountForFilter[];
  action?: React.ReactNode;
}

interface FilterOption {
  id: string;
  label: string;
  color?: string;
}

// Date range presets
const datePresets = [
  { label: "Today", getValue: () => ({ from: startOfDay(new Date()), to: endOfDay(new Date()) }) },
  { label: "Yesterday", getValue: () => ({ from: startOfDay(subDays(new Date(), 1)), to: endOfDay(subDays(new Date(), 1)) }) },
  { label: "This Week", getValue: () => ({ from: startOfWeek(new Date(), { weekStartsOn: 1 }), to: endOfWeek(new Date(), { weekStartsOn: 1 }) }) },
  { label: "This Month", getValue: () => ({ from: startOfMonth(new Date()), to: endOfMonth(new Date()) }) },
  { label: "This Quarter", getValue: () => ({ from: startOfQuarter(new Date()), to: endOfQuarter(new Date()) }) },
  { label: "This Year", getValue: () => ({ from: startOfYear(new Date()), to: endOfYear(new Date()) }) },
];

// Multi-select filter with search
interface MultiSelectFilterProps {
  label: string;
  icon: React.ReactNode;
  options: FilterOption[];
  selectedIds: string[];
  onSelectionChange: (ids: string[]) => void;
  includeUncategorized?: boolean;
  searchable?: boolean;
}

function MultiSelectFilter({
  label,
  icon,
  options,
  selectedIds,
  onSelectionChange,
  includeUncategorized,
  searchable,
}: MultiSelectFilterProps) {
  const [open, setOpen] = React.useState(false);
  const [search, setSearch] = React.useState("");

  const filteredOptions = React.useMemo(() => {
    if (!search) return options;
    return options.filter((opt) =>
      opt.label.toLowerCase().includes(search.toLowerCase())
    );
  }, [options, search]);

  const toggleOption = (id: string) => {
    if (selectedIds.includes(id)) {
      onSelectionChange(selectedIds.filter((i) => i !== id));
    } else {
      onSelectionChange([...selectedIds, id]);
    }
  };

  const getDisplayText = () => {
    if (selectedIds.length === 0) return "Select...";
    if (selectedIds.length === 1) {
      if (selectedIds[0] === "uncategorized") return "Uncategorized";
      const option = options.find((o) => o.id === selectedIds[0]);
      return option?.label || selectedIds[0];
    }
    return `${selectedIds.length} selected`;
  };

  return (
    <div className="space-y-2">
      <Label className="flex items-center gap-2 text-xs text-muted-foreground">
        {icon}
        {label}
        {selectedIds.length > 0 && (
          <span className="text-foreground">({selectedIds.length})</span>
        )}
      </Label>
      <Popover open={open} onOpenChange={setOpen}>
        <PopoverTrigger className="flex h-8 w-full items-center justify-between border border-input bg-background px-2.5 text-xs hover:bg-accent hover:text-accent-foreground">
          <span className="truncate">{getDisplayText()}</span>
          <RiArrowDownSLine className="h-4 w-4 shrink-0 text-muted-foreground" />
        </PopoverTrigger>
        <PopoverContent align="start" className="w-64 p-0">
          {searchable && (
            <div className="p-2 border-b">
              <Input
                placeholder={`Search ${label.toLowerCase()}...`}
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                className="h-7 text-xs"
              />
            </div>
          )}
          <div className="max-h-48 overflow-y-auto p-1">
            {includeUncategorized && !search && (
              <button
                type="button"
                onClick={() => toggleOption("uncategorized")}
                className="flex w-full items-center gap-2 px-2 py-1.5 text-xs hover:bg-accent"
              >
                <Checkbox
                  checked={selectedIds.includes("uncategorized")}
                  className="pointer-events-none"
                />
                <span className="inline-flex items-center px-1.5 py-0.5 text-xs bg-muted text-muted-foreground">
                  Uncategorized
                </span>
              </button>
            )}
            {filteredOptions.map((option) => (
              <button
                key={option.id}
                type="button"
                onClick={() => toggleOption(option.id)}
                className="flex w-full items-center gap-2 px-2 py-1.5 text-xs hover:bg-accent"
              >
                <Checkbox
                  checked={selectedIds.includes(option.id)}
                  className="pointer-events-none"
                />
                {option.color ? (
                  <span
                    className="inline-flex items-center px-1.5 py-0.5 text-xs text-white truncate"
                    style={{ backgroundColor: option.color }}
                  >
                    {option.label}
                  </span>
                ) : (
                  <span className="truncate">{option.label}</span>
                )}
              </button>
            ))}
            {filteredOptions.length === 0 && (
              <div className="px-2 py-4 text-center text-xs text-muted-foreground">
                No results found
              </div>
            )}
          </div>
        </PopoverContent>
      </Popover>
    </div>
  );
}

// Date range filter component
interface DateRangeFilterProps {
  dateRange: DateRange | undefined;
  onDateRangeChange: (range: DateRange | undefined) => void;
}

function DateRangeFilter({ dateRange, onDateRangeChange }: DateRangeFilterProps) {
  const [open, setOpen] = React.useState(false);

  const getDisplayText = () => {
    if (!dateRange?.from) return "All time";
    if (!dateRange.to) return format(dateRange.from, "MMM d, yyyy");
    return `${format(dateRange.from, "MMM d")} - ${format(dateRange.to, "MMM d, yyyy")}`;
  };

  return (
    <div className="space-y-2">
      <Label className="flex items-center gap-2 text-xs text-muted-foreground">
        <RiCalendarLine className="h-4 w-4" />
        Date Range
        {dateRange?.from && (
          <span className="text-foreground">(1)</span>
        )}
      </Label>
      <Popover open={open} onOpenChange={setOpen}>
        <PopoverTrigger className="flex h-8 w-full items-center justify-between border border-input bg-background px-2.5 text-xs hover:bg-accent hover:text-accent-foreground">
          <span className="truncate">{getDisplayText()}</span>
          <RiArrowDownSLine className="h-4 w-4 shrink-0 text-muted-foreground" />
        </PopoverTrigger>
        <PopoverContent align="start" className="w-auto p-0">
          <div className="flex">
            <div className="border-r p-2 space-y-0.5 w-28">
              <button
                type="button"
                onClick={() => {
                  onDateRangeChange(undefined);
                  setOpen(false);
                }}
                className={cn(
                  "w-full px-2 py-1.5 text-left text-xs hover:bg-accent",
                  !dateRange?.from && "bg-accent"
                )}
              >
                All time
              </button>
              {datePresets.map((preset) => (
                <button
                  key={preset.label}
                  type="button"
                  onClick={() => {
                    onDateRangeChange(preset.getValue());
                    setOpen(false);
                  }}
                  className="w-full px-2 py-1.5 text-left text-xs hover:bg-accent"
                >
                  {preset.label}
                </button>
              ))}
            </div>
            <div className="p-2">
              <Calendar
                mode="range"
                selected={dateRange}
                onSelect={(range) => onDateRangeChange(range)}
                numberOfMonths={1}
                defaultMonth={dateRange?.from}
              />
            </div>
          </div>
        </PopoverContent>
      </Popover>
    </div>
  );
}

// Amount range filter component
interface AmountRangeFilterProps {
  minAmount: string;
  maxAmount: string;
  onMinChange: (value: string) => void;
  onMaxChange: (value: string) => void;
}

function AmountRangeFilter({
  minAmount,
  maxAmount,
  onMinChange,
  onMaxChange,
}: AmountRangeFilterProps) {
  const hasFilter = minAmount || maxAmount;

  return (
    <div className="space-y-2">
      <Label className="flex items-center gap-2 text-xs text-muted-foreground">
        <RiMoneyDollarCircleLine className="h-4 w-4" />
        Amount Range
        {hasFilter && (
          <span className="text-foreground">(1)</span>
        )}
      </Label>
      <div className="flex items-center gap-2">
        <Input
          type="number"
          placeholder="Min"
          value={minAmount}
          onChange={(e) => onMinChange(e.target.value)}
          className="h-8 text-xs"
        />
        <span className="text-muted-foreground text-xs">to</span>
        <Input
          type="number"
          placeholder="Max"
          value={maxAmount}
          onChange={(e) => onMaxChange(e.target.value)}
          className="h-8 text-xs"
        />
      </div>
    </div>
  );
}

// Active filter tag component
interface FilterTagProps {
  label: string;
  onRemove: () => void;
}

function FilterTag({ label, onRemove }: FilterTagProps) {
  return (
    <button
      type="button"
      onClick={onRemove}
      className="inline-flex items-center gap-1 bg-muted px-2 py-0.5 text-xs hover:bg-muted/80"
    >
      {label}
      <RiCloseLine className="h-3 w-3" />
    </button>
  );
}

export function TransactionFilters({ table, categories, accounts, action }: TransactionFiltersProps) {
  const descriptionColumn = table.getColumn("description");
  const categoryColumn = table.getColumn("category");
  const accountColumn = table.getColumn("account");
  const pendingColumn = table.getColumn("pending");
  const bookedAtColumn = table.getColumn("bookedAt");
  const amountColumn = table.getColumn("amount");

  const descriptionValue = (descriptionColumn?.getFilterValue() as string) ?? "";

  // Multi-select filter values
  const categoryValues = (categoryColumn?.getFilterValue() as string[]) ?? [];
  const accountValues = (accountColumn?.getFilterValue() as string[]) ?? [];
  const statusValues = (pendingColumn?.getFilterValue() as string[]) ?? [];

  // Date range filter
  const dateRange = (bookedAtColumn?.getFilterValue() as DateRange | undefined);

  // Amount range filter
  const amountRange = (amountColumn?.getFilterValue() as { min?: string; max?: string } | undefined);
  const minAmount = amountRange?.min ?? "";
  const maxAmount = amountRange?.max ?? "";

  // Count active filters
  const activeFilterCount =
    categoryValues.length +
    accountValues.length +
    statusValues.length +
    (dateRange?.from ? 1 : 0) +
    (minAmount || maxAmount ? 1 : 0);

  const clearFilters = () => {
    categoryColumn?.setFilterValue([]);
    accountColumn?.setFilterValue([]);
    pendingColumn?.setFilterValue([]);
    bookedAtColumn?.setFilterValue(undefined);
    amountColumn?.setFilterValue(undefined);
  };

  // Prepare options from props
  const categoryOptions: FilterOption[] = categories.map((cat) => ({
    id: cat.id,
    label: cat.name,
    color: cat.color ?? undefined,
  }));

  const accountOptions: FilterOption[] = accounts.map((acc) => ({
    id: acc.id,
    label: acc.name,
  }));

  const statusOptions: FilterOption[] = [
    { id: "completed", label: "Completed" },
    { id: "pending", label: "Pending" },
  ];

  // Build active filter tags
  const filterTags: { label: string; onRemove: () => void }[] = [];

  // Category tags
  categoryValues.forEach((id) => {
    if (id === "uncategorized") {
      filterTags.push({
        label: "Uncategorized",
        onRemove: () => categoryColumn?.setFilterValue(categoryValues.filter((v) => v !== id)),
      });
    } else {
      const cat = categories.find((c) => c.id === id);
      if (cat) {
        filterTags.push({
          label: cat.name,
          onRemove: () => categoryColumn?.setFilterValue(categoryValues.filter((v) => v !== id)),
        });
      }
    }
  });

  // Account tags
  accountValues.forEach((id) => {
    const acc = accounts.find((a) => a.id === id);
    if (acc) {
      filterTags.push({
        label: acc.name,
        onRemove: () => accountColumn?.setFilterValue(accountValues.filter((v) => v !== id)),
      });
    }
  });

  // Status tags
  statusValues.forEach((id) => {
    filterTags.push({
      label: id === "pending" ? "Pending" : "Completed",
      onRemove: () => pendingColumn?.setFilterValue(statusValues.filter((v) => v !== id)),
    });
  });

  // Date range tag
  if (dateRange?.from) {
    const label = dateRange.to
      ? `${format(dateRange.from, "MMM d")} - ${format(dateRange.to, "MMM d")}`
      : format(dateRange.from, "MMM d, yyyy");
    filterTags.push({
      label,
      onRemove: () => bookedAtColumn?.setFilterValue(undefined),
    });
  }

  // Amount range tag
  if (minAmount || maxAmount) {
    let label = "";
    if (minAmount && maxAmount) {
      label = `€${minAmount} - €${maxAmount}`;
    } else if (minAmount) {
      label = `≥ €${minAmount}`;
    } else {
      label = `≤ €${maxAmount}`;
    }
    filterTags.push({
      label,
      onRemove: () => amountColumn?.setFilterValue(undefined),
    });
  }

  const totalRows = table.getFilteredRowModel().rows.length;
  const totalUnfiltered = table.getPreFilteredRowModel().rows.length;
  const isFiltered = totalRows !== totalUnfiltered;

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <div className="relative w-64">
            <RiSearchLine className="absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
            <Input
              placeholder="Search transactions..."
              value={descriptionValue}
              onChange={(event) =>
                descriptionColumn?.setFilterValue(event.target.value)
              }
              className="pl-8"
            />
          </div>

          <Popover>
            <PopoverTrigger className="inline-flex items-center justify-center gap-2 whitespace-nowrap text-xs font-medium transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring disabled:pointer-events-none disabled:opacity-50 border border-input bg-transparent hover:bg-accent hover:text-accent-foreground h-8 px-3">
              <RiFilter3Line className="h-4 w-4" />
              Filters
              {activeFilterCount > 0 && (
                <span className="flex h-5 min-w-5 items-center justify-center bg-muted px-1.5 text-[10px] font-medium text-muted-foreground">
                  {activeFilterCount}
                </span>
              )}
            </PopoverTrigger>
          <PopoverContent align="start" className="w-80">
            <div className="flex items-center justify-between">
              <span className="text-sm font-medium">Filters</span>
              {activeFilterCount > 0 && (
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={clearFilters}
                  className="h-auto p-0 text-xs text-muted-foreground hover:text-foreground"
                >
                  Clear all
                </Button>
              )}
            </div>

            <Separator className="my-3" />

            <div className="space-y-4">
              <DateRangeFilter
                dateRange={dateRange}
                onDateRangeChange={(range) => bookedAtColumn?.setFilterValue(range)}
              />

              <MultiSelectFilter
                label="Category"
                icon={<RiPriceTag3Line className="h-4 w-4" />}
                options={categoryOptions}
                selectedIds={categoryValues}
                onSelectionChange={(ids) => categoryColumn?.setFilterValue(ids)}
                includeUncategorized
                searchable
              />

              <MultiSelectFilter
                label="Account"
                icon={<RiBankLine className="h-4 w-4" />}
                options={accountOptions}
                selectedIds={accountValues}
                onSelectionChange={(ids) => accountColumn?.setFilterValue(ids)}
              />

              <MultiSelectFilter
                label="Status"
                icon={<RiTimeLine className="h-4 w-4" />}
                options={statusOptions}
                selectedIds={statusValues}
                onSelectionChange={(ids) => pendingColumn?.setFilterValue(ids)}
              />

              <AmountRangeFilter
                minAmount={minAmount}
                maxAmount={maxAmount}
                onMinChange={(value) =>
                  amountColumn?.setFilterValue({
                    ...amountRange,
                    min: value || undefined,
                  })
                }
                onMaxChange={(value) =>
                  amountColumn?.setFilterValue({
                    ...amountRange,
                    max: value || undefined,
                  })
                }
              />
            </div>
          </PopoverContent>
        </Popover>
        </div>
        {action}
      </div>

      {/* Active filter tags */}
      {filterTags.length > 0 && (
        <div className="flex flex-wrap items-center gap-1.5">
          {filterTags.map((tag, index) => (
            <FilterTag key={index} label={tag.label} onRemove={tag.onRemove} />
          ))}
        </div>
      )}

      {/* Filter summary */}
      {isFiltered && (
        <p className="text-xs text-muted-foreground">
          Showing {totalRows} of {totalUnfiltered} transactions
        </p>
      )}
    </div>
  );
}
