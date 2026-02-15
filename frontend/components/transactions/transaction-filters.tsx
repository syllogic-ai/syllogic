"use client";

import * as React from "react";
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
  subMonths,
  subQuarters,
  subYears,
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
  RiRepeatLine,
  RiLineChartLine,
} from "@remixicon/react";
import type { CategoryForFilter, AccountForFilter } from "@/types";
import type { TransactionsQueryState } from "@/lib/transactions/query-state";
import { cn } from "@/lib/utils";

interface RecurringFilterOption {
  id: string;
  name: string;
  merchant?: string;
  frequency: string;
}

interface TransactionFiltersProps {
  filters: TransactionsQueryState;
  categories: CategoryForFilter[];
  accounts: AccountForFilter[];
  recurringOptions: RecurringFilterOption[];
  action?: React.ReactNode;
  totalCount: number;
  currentPageCount: number;
  onFiltersChange: (
    patch: Partial<TransactionsQueryState>,
    options?: { resetPage?: boolean }
  ) => void;
  onClearFilters: () => void;
}

interface FilterOption {
  id: string;
  label: string;
  color?: string;
}

const datePresets = [
  {
    label: "This Week",
    getValue: () => ({
      from: startOfWeek(new Date(), { weekStartsOn: 1 }),
      to: endOfWeek(new Date(), { weekStartsOn: 1 }),
    }),
  },
  {
    label: "This Month",
    getValue: () => ({ from: startOfMonth(new Date()), to: endOfMonth(new Date()) }),
  },
  {
    label: "Last Month",
    getValue: () => {
      const date = subMonths(new Date(), 1);
      return { from: startOfMonth(date), to: endOfMonth(date) };
    },
  },
  {
    label: "This Quarter",
    getValue: () => ({ from: startOfQuarter(new Date()), to: endOfQuarter(new Date()) }),
  },
  {
    label: "Last Quarter",
    getValue: () => {
      const date = subQuarters(new Date(), 1);
      return { from: startOfQuarter(date), to: endOfQuarter(date) };
    },
  },
  {
    label: "This Year",
    getValue: () => ({ from: startOfYear(new Date()), to: endOfYear(new Date()) }),
  },
  {
    label: "Last Year",
    getValue: () => {
      const date = subYears(new Date(), 1);
      return { from: startOfYear(date), to: endOfYear(date) };
    },
  },
];

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
      onSelectionChange(selectedIds.filter((value) => value !== id));
      return;
    }
    onSelectionChange([...selectedIds, id]);
  };

  const getDisplayText = () => {
    if (selectedIds.length === 0) return "Select...";
    if (selectedIds.length === 1) {
      if (selectedIds[0] === "uncategorized") return "Uncategorized";
      if (selectedIds[0] === "no_subscription") return "No Subscription";
      const option = options.find((item) => item.id === selectedIds[0]);
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
            <div className="border-b p-2">
              <Input
                placeholder={`Search ${label.toLowerCase()}...`}
                value={search}
                onChange={(event) => setSearch(event.target.value)}
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
                <span className="inline-flex items-center bg-muted px-1.5 py-0.5 text-xs text-muted-foreground">
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
                    className="inline-flex items-center truncate px-1.5 py-0.5 text-xs text-white"
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

interface DateRangeFilterProps {
  dateRange: DateRange | undefined;
  onDateRangeChange: (range: DateRange | undefined) => void;
}

function formatDateRangeDisplay(range: DateRange | undefined): string {
  if (!range?.from) return "Range";
  if (!range.to) return format(range.from, "MMM d, yyyy");

  const spansDifferentYears = range.from.getFullYear() !== range.to.getFullYear();
  if (spansDifferentYears) {
    return `${format(range.from, "MMM d, yyyy")} - ${format(range.to, "MMM d, yyyy")}`;
  }

  return `${format(range.from, "MMM d")} - ${format(range.to, "MMM d, yyyy")}`;
}

function DateRangeFilter({ dateRange, onDateRangeChange }: DateRangeFilterProps) {
  const [open, setOpen] = React.useState(false);

  return (
    <div className="space-y-2">
      <Label className="flex items-center gap-2 text-xs text-muted-foreground">
        <RiCalendarLine className="h-4 w-4" />
        Date Range
        {dateRange?.from && <span className="text-foreground">(1)</span>}
      </Label>
      <Popover open={open} onOpenChange={setOpen}>
        <PopoverTrigger className="flex h-8 w-full items-center justify-between border border-input bg-background px-2.5 text-xs hover:bg-accent hover:text-accent-foreground">
          <span className="truncate">{formatDateRangeDisplay(dateRange)}</span>
          <RiArrowDownSLine className="h-4 w-4 shrink-0 text-muted-foreground" />
        </PopoverTrigger>
        <PopoverContent align="start" className="w-auto p-0">
          <div className="flex">
            <div className="w-28 space-y-0.5 border-r p-2">
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
                Clear
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
        {hasFilter && <span className="text-foreground">(1)</span>}
      </Label>
      <div className="flex items-center gap-2">
        <Input
          type="number"
          placeholder="Min"
          value={minAmount}
          onChange={(event) => onMinChange(event.target.value)}
          className="h-8 text-xs"
        />
        <span className="text-xs text-muted-foreground">to</span>
        <Input
          type="number"
          placeholder="Max"
          value={maxAmount}
          onChange={(event) => onMaxChange(event.target.value)}
          className="h-8 text-xs"
        />
      </div>
    </div>
  );
}

function FilterTag({ label, onRemove }: { label: string; onRemove: () => void }) {
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

export function TransactionFilters({
  filters,
  categories,
  accounts,
  recurringOptions,
  action,
  totalCount,
  currentPageCount,
  onFiltersChange,
  onClearFilters,
}: TransactionFiltersProps) {
  const [searchInput, setSearchInput] = React.useState(filters.search ?? "");

  React.useEffect(() => {
    setSearchInput(filters.search ?? "");
  }, [filters.search]);

  React.useEffect(() => {
    const normalizedSearch = searchInput.trim();
    const currentSearch = filters.search ?? "";
    if (normalizedSearch === currentSearch) return;
    const timeout = window.setTimeout(() => {
      onFiltersChange({ search: normalizedSearch || undefined }, { resetPage: true });
    }, 250);

    return () => window.clearTimeout(timeout);
  }, [searchInput, filters.search, onFiltersChange]);

  const dateRange = React.useMemo<DateRange | undefined>(() => {
    if (!filters.from) return undefined;
    const from = new Date(`${filters.from}T00:00:00.000Z`);
    if (Number.isNaN(from.getTime())) return undefined;
    const to = filters.to ? new Date(`${filters.to}T00:00:00.000Z`) : undefined;
    if (to && Number.isNaN(to.getTime())) {
      return { from };
    }
    return { from, to };
  }, [filters.from, filters.to]);

  const activeFilterCount =
    filters.category.length +
    filters.accountIds.length +
    filters.status.length +
    filters.subscription.length +
    filters.analytics.length +
    (filters.from ? 1 : 0) +
    (filters.minAmount || filters.maxAmount ? 1 : 0);
  const hasTimeScope = Boolean(filters.from || filters.horizon);

  const categoryOptions: FilterOption[] = categories.map((category) => ({
    id: category.id,
    label: category.name,
    color: category.color ?? undefined,
  }));

  const accountOptions: FilterOption[] = accounts.map((account) => ({
    id: account.id,
    label: account.name,
  }));

  const statusOptions: FilterOption[] = [
    { id: "completed", label: "Completed" },
    { id: "pending", label: "Pending" },
  ];

  const analyticsOptions: FilterOption[] = [
    { id: "included", label: "Included in Analytics" },
    { id: "excluded", label: "Excluded from Analytics" },
  ];

  const subscriptionOptions: FilterOption[] = [
    { id: "no_subscription", label: "No Subscription" },
    ...recurringOptions.map((recurring) => ({
      id: recurring.id,
      label: recurring.merchant ? `${recurring.name} (${recurring.merchant})` : recurring.name,
    })),
  ];

  const filterTags: { label: string; onRemove: () => void }[] = [];

  filters.category.forEach((id) => {
    if (id === "uncategorized") {
      filterTags.push({
        label: "Uncategorized",
        onRemove: () =>
          onFiltersChange(
            { category: filters.category.filter((value) => value !== id) },
            { resetPage: true }
          ),
      });
      return;
    }
    const category = categories.find((item) => item.id === id);
    if (!category) return;
    filterTags.push({
      label: category.name,
      onRemove: () =>
        onFiltersChange(
          { category: filters.category.filter((value) => value !== id) },
          { resetPage: true }
        ),
    });
  });

  filters.accountIds.forEach((id) => {
    const account = accounts.find((item) => item.id === id);
    if (!account) return;
    filterTags.push({
      label: account.name,
      onRemove: () =>
        onFiltersChange(
          { accountIds: filters.accountIds.filter((value) => value !== id) },
          { resetPage: true }
        ),
    });
  });

  filters.status.forEach((id) => {
    filterTags.push({
      label: id === "pending" ? "Pending" : "Completed",
      onRemove: () =>
        onFiltersChange(
          { status: filters.status.filter((value) => value !== id) },
          { resetPage: true }
        ),
    });
  });

  filters.subscription.forEach((id) => {
    if (id === "no_subscription") {
      filterTags.push({
        label: "No Subscription",
        onRemove: () =>
          onFiltersChange(
            { subscription: filters.subscription.filter((value) => value !== id) },
            { resetPage: true }
          ),
      });
      return;
    }
    const recurring = recurringOptions.find((item) => item.id === id);
    if (!recurring) return;
    filterTags.push({
      label: recurring.merchant ? `${recurring.name} (${recurring.merchant})` : recurring.name,
      onRemove: () =>
        onFiltersChange(
          { subscription: filters.subscription.filter((value) => value !== id) },
          { resetPage: true }
        ),
    });
  });

  filters.analytics.forEach((id) => {
    filterTags.push({
      label: id === "included" ? "In Analytics" : "Excluded from Analytics",
      onRemove: () =>
        onFiltersChange(
          { analytics: filters.analytics.filter((value) => value !== id) },
          { resetPage: true }
        ),
    });
  });

  if (filters.from) {
    filterTags.push({
      label: formatDateRangeDisplay(dateRange),
      onRemove: () =>
        onFiltersChange(
          { from: undefined, to: undefined, horizon: 30 },
          { resetPage: true }
        ),
    });
  } else if (filters.horizon) {
    const horizonLabel = filters.horizon === 365 ? "12M" : `${filters.horizon}D`;
    filterTags.push({
      label: horizonLabel,
      onRemove: () =>
        onFiltersChange(
          { horizon: undefined, from: undefined, to: undefined },
          { resetPage: true }
        ),
    });
  }

  if (filters.minAmount || filters.maxAmount) {
    let amountLabel = "";
    if (filters.minAmount && filters.maxAmount) {
      amountLabel = `EUR ${filters.minAmount} - EUR ${filters.maxAmount}`;
    } else if (filters.minAmount) {
      amountLabel = `>= EUR ${filters.minAmount}`;
    } else {
      amountLabel = `<= EUR ${filters.maxAmount}`;
    }

    filterTags.push({
      label: amountLabel,
      onRemove: () =>
        onFiltersChange(
          { minAmount: undefined, maxAmount: undefined },
          { resetPage: true }
        ),
    });
  }

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <div className="relative w-64">
            <RiSearchLine className="absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
            <Input
              placeholder="Search transactions..."
              value={searchInput}
              onChange={(event) => setSearchInput(event.target.value)}
              className="pl-8"
            />
          </div>

          <Popover>
            <PopoverTrigger className="inline-flex h-8 items-center justify-center gap-2 whitespace-nowrap border border-input bg-transparent px-3 text-xs font-medium transition-colors hover:bg-accent hover:text-accent-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring disabled:pointer-events-none disabled:opacity-50">
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
                    onClick={onClearFilters}
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
                  onDateRangeChange={(range) => {
                    if (!range?.from) {
                      onFiltersChange(
                        { from: undefined, to: undefined, horizon: 30 },
                        { resetPage: true }
                      );
                      return;
                    }
                    const normalizedFrom = format(startOfDay(range.from), "yyyy-MM-dd");
                    const normalizedTo = range.to
                      ? format(endOfDay(range.to), "yyyy-MM-dd")
                      : undefined;
                    onFiltersChange(
                      {
                        from: normalizedFrom,
                        to: normalizedTo,
                        horizon: undefined,
                      },
                      { resetPage: true }
                    );
                  }}
                />

                <MultiSelectFilter
                  label="Category"
                  icon={<RiPriceTag3Line className="h-4 w-4" />}
                  options={categoryOptions}
                  selectedIds={filters.category}
                  onSelectionChange={(ids) =>
                    onFiltersChange({ category: ids }, { resetPage: true })
                  }
                  includeUncategorized
                  searchable
                />

                <MultiSelectFilter
                  label="Account"
                  icon={<RiBankLine className="h-4 w-4" />}
                  options={accountOptions}
                  selectedIds={filters.accountIds}
                  onSelectionChange={(ids) =>
                    onFiltersChange({ accountIds: ids }, { resetPage: true })
                  }
                />

                <MultiSelectFilter
                  label="Status"
                  icon={<RiTimeLine className="h-4 w-4" />}
                  options={statusOptions}
                  selectedIds={filters.status}
                  onSelectionChange={(ids) =>
                    onFiltersChange({ status: ids }, { resetPage: true })
                  }
                />

                <MultiSelectFilter
                  label="Subscription"
                  icon={<RiRepeatLine className="h-4 w-4" />}
                  options={subscriptionOptions}
                  selectedIds={filters.subscription}
                  onSelectionChange={(ids) =>
                    onFiltersChange({ subscription: ids }, { resetPage: true })
                  }
                  searchable
                />

                <AmountRangeFilter
                  minAmount={filters.minAmount ?? ""}
                  maxAmount={filters.maxAmount ?? ""}
                  onMinChange={(value) =>
                    onFiltersChange(
                      { minAmount: value.trim() || undefined },
                      { resetPage: true }
                    )
                  }
                  onMaxChange={(value) =>
                    onFiltersChange(
                      { maxAmount: value.trim() || undefined },
                      { resetPage: true }
                    )
                  }
                />

                <MultiSelectFilter
                  label="Analytics"
                  icon={<RiLineChartLine className="h-4 w-4" />}
                  options={analyticsOptions}
                  selectedIds={filters.analytics}
                  onSelectionChange={(ids) =>
                    onFiltersChange({ analytics: ids }, { resetPage: true })
                  }
                />
              </div>
            </PopoverContent>
          </Popover>
        </div>
        {action}
      </div>

      {filterTags.length > 0 && (
        <div className="flex flex-wrap items-center gap-1.5">
          {filterTags.map((tag, index) => (
            <FilterTag
              key={`${tag.label}-${index}`}
              label={tag.label}
              onRemove={tag.onRemove}
            />
          ))}
        </div>
      )}

      {totalCount !== currentPageCount && (
        <p className="text-xs text-muted-foreground">
          Showing {currentPageCount} of {totalCount} transactions
          {hasTimeScope ? " in current time window" : ""}
        </p>
      )}
    </div>
  );
}
