"use client";

import * as React from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { type DateRange } from "react-day-picker";
import { differenceInCalendarDays, format } from "date-fns";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";
import { Checkbox } from "@/components/ui/checkbox";
import { Badge } from "@/components/ui/badge";
import { DateRangePicker } from "@/components/ui/date-range-picker";
import { cn } from "@/lib/utils";
import { RiArrowDownSLine, RiWalletLine } from "@remixicon/react";
import { useFilterPersistence } from "@/lib/hooks/use-filter-persistence";
import { parseGlobalFiltersFromSearchParams } from "@/lib/filters/global-filters";

interface Account {
  id: string;
  name: string;
  institution: string | null;
  accountType: string;
}

interface DashboardFiltersProps {
  accounts: Account[];
}

const HORIZON_OPTIONS = [
  { value: "7", label: "7D" },
  { value: "30", label: "30D" },
  { value: "365", label: "12M" },
] as const;

export function DashboardFilters({ accounts }: DashboardFiltersProps) {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [accountsOpen, setAccountsOpen] = React.useState(false);

  useFilterPersistence();

  const globalFilters = React.useMemo(
    () => parseGlobalFiltersFromSearchParams(searchParams),
    [searchParams]
  );

  const selectedAccountIds = globalFilters.accountIds;

  const selectedAccountSet = React.useMemo(
    () => new Set(selectedAccountIds),
    [selectedAccountIds]
  );

  const isAllAccountsSelected = selectedAccountIds.length === 0;
  const selectedAccountsCount = selectedAccountIds.length;
  const accountTriggerText = isAllAccountsSelected ? "All accounts" : "Accounts";

  const dateFromParam = globalFilters.from;
  const dateToParam = globalFilters.to;
  const dateRange: DateRange | undefined = React.useMemo(() => {
    if (!dateFromParam) return undefined;
    return {
      from: new Date(dateFromParam),
      to: dateToParam ? new Date(dateToParam) : undefined,
    };
  }, [dateFromParam, dateToParam]);

  const isDateRangeActive = Boolean(dateRange?.from);
  const currentHorizon = globalFilters.horizon || "30";
  const effectiveHorizon = isDateRangeActive ? undefined : currentHorizon;

  const matchedSpanDays = React.useMemo(() => {
    if (!dateRange?.from || !dateRange.to) return null;
    return differenceInCalendarDays(dateRange.to, dateRange.from) + 1;
  }, [dateRange?.from, dateRange?.to]);

  const shouldCollapseGap = matchedSpanDays === 7 || matchedSpanDays === 30 || matchedSpanDays === 365;

  const pushParams = React.useCallback(
    (nextParams: URLSearchParams) => {
      const queryString = nextParams.toString();
      router.push(queryString ? `?${queryString}` : "/", { scroll: false });
    },
    [router]
  );

  const updateSelectedAccounts = React.useCallback(
    (nextAccountIds: string[]) => {
      const params = new URLSearchParams(searchParams.toString());
      params.delete("account");
      nextAccountIds.forEach((accountId) => params.append("account", accountId));
      pushParams(params);
    },
    [pushParams, searchParams]
  );

  const toggleAccount = React.useCallback(
    (accountId: string) => {
      if (selectedAccountSet.has(accountId)) {
        updateSelectedAccounts(selectedAccountIds.filter((id) => id !== accountId));
      } else {
        updateSelectedAccounts([...selectedAccountIds, accountId]);
      }
    },
    [selectedAccountIds, selectedAccountSet, updateSelectedAccounts]
  );

  const updateDateRange = React.useCallback(
    (range: DateRange | undefined) => {
      const params = new URLSearchParams(searchParams.toString());
      if (!range?.from) {
        params.delete("from");
        params.delete("to");
      } else {
        params.set("from", format(range.from, "yyyy-MM-dd"));
        if (range.to) {
          params.set("to", format(range.to, "yyyy-MM-dd"));
        } else {
          params.delete("to");
        }
        params.delete("horizon");
      }
      pushParams(params);
    },
    [pushParams, searchParams]
  );

  const updateHorizon = React.useCallback(
    (horizon: string) => {
      const params = new URLSearchParams(searchParams.toString());
      params.delete("from");
      params.delete("to");
      if (horizon === "30") {
        params.delete("horizon");
      } else {
        params.set("horizon", horizon);
      }
      pushParams(params);
    },
    [pushParams, searchParams]
  );

  return (
    <div className="flex items-center gap-2">
      <Popover open={accountsOpen} onOpenChange={setAccountsOpen}>
        <PopoverTrigger
          className={cn(
            "flex !h-9 w-[190px] items-center justify-between border border-input bg-transparent px-2.5 text-xs transition-colors hover:bg-muted"
          )}
        >
          <span className="flex items-center gap-2 truncate">
            <RiWalletLine className="h-4 w-4 text-muted-foreground" />
            <span className="truncate">{accountTriggerText}</span>
          </span>
          <span className="flex items-center gap-1 shrink-0">
            {!isAllAccountsSelected && (
              <Badge variant="outline" className="h-4 min-w-4 px-1 text-[10px] leading-none">
                {selectedAccountsCount}
              </Badge>
            )}
            <RiArrowDownSLine className="h-4 w-4 text-muted-foreground" />
          </span>
        </PopoverTrigger>
        <PopoverContent align="start" className="w-64 p-0">
          <div className="border-b p-1">
            <button
              type="button"
              className="flex w-full items-center gap-2 px-2 py-1.5 text-xs hover:bg-accent"
              onClick={() => updateSelectedAccounts([])}
            >
              <Checkbox
                checked={isAllAccountsSelected}
                className="pointer-events-none"
              />
              <span>All accounts ({accounts.length})</span>
            </button>
          </div>
          <div className="max-h-56 overflow-y-auto p-1">
            {accounts.map((account) => (
              <button
                key={account.id}
                type="button"
                className="flex w-full items-center gap-2 px-2 py-1.5 text-xs hover:bg-accent"
                onClick={() => toggleAccount(account.id)}
              >
                <Checkbox
                  checked={selectedAccountSet.has(account.id)}
                  className="pointer-events-none"
                />
                <span className="truncate">{account.name}</span>
              </button>
            ))}
          </div>
        </PopoverContent>
      </Popover>

      <div className={cn("flex items-center", shouldCollapseGap ? "gap-0" : "gap-2")}>
        <DateRangePicker
          value={dateRange}
          onChange={updateDateRange}
          className="!h-9 w-fit"
          placeholder="Date"
          showSelectedText={false}
          active={isDateRangeActive}
        />

        <div className="flex items-center !h-9 border border-input box-border divide-x divide-border">
          {HORIZON_OPTIONS.map((option) => (
            <button
              key={option.value}
              type="button"
              className={cn(
                "h-full px-3 text-xs font-medium transition-colors",
                effectiveHorizon === option.value
                  ? "bg-primary text-primary-foreground"
                  : "bg-transparent text-foreground hover:bg-muted"
              )}
              onClick={() => updateHorizon(option.value)}
            >
              {option.label}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
