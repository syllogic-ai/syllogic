"use client";

import * as React from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { type DateRange } from "react-day-picker";
import { format } from "date-fns";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
} from "@/components/ui/select";
import { DateRangePicker } from "@/components/ui/date-range-picker";
import { cn } from "@/lib/utils";
import { RiWalletLine } from "@remixicon/react";

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

export function DashboardFilters({
  accounts,
}: DashboardFiltersProps) {
  const router = useRouter();
  const searchParams = useSearchParams();

  // Get current filter values from URL or use defaults
  const currentAccount = searchParams.get("account") || "all";
  const currentHorizon = searchParams.get("horizon") || "7";

  // Parse date range from URL
  const dateFromParam = searchParams.get("from");
  const dateToParam = searchParams.get("to");
  const dateRange: DateRange | undefined = React.useMemo(() => {
    if (!dateFromParam) return undefined;
    return {
      from: new Date(dateFromParam),
      to: dateToParam ? new Date(dateToParam) : undefined,
    };
  }, [dateFromParam, dateToParam]);

  // Update URL with new filter values
  const updateFilters = React.useCallback(
    (key: string, value: string | undefined) => {
      const params = new URLSearchParams(searchParams.toString());
      if (!value || value === "all" || (key === "horizon" && value === "7")) {
        params.delete(key);
      } else {
        params.set(key, value);
      }
      const queryString = params.toString();
      router.push(queryString ? `?${queryString}` : "/", { scroll: false });
    },
    [searchParams, router]
  );

  // Update date range in URL
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
      }
      const queryString = params.toString();
      router.push(queryString ? `?${queryString}` : "/", { scroll: false });
    },
    [searchParams, router]
  );

  return (
    <div className="flex items-center gap-2">
      {/* Account Selector */}
      <Select
        value={currentAccount}
        onValueChange={(value) => updateFilters("account", value)}
      >
        <SelectTrigger className="!h-9 w-[160px]">
          {currentAccount === "all" ? (
            <div className="flex items-center gap-2">
              <RiWalletLine className="h-4 w-4 text-muted-foreground" />
              <span>Accounts</span>
            </div>
          ) : (
            <span>{accounts.find(a => a.id === currentAccount)?.name || "Account"}</span>
          )}
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="all">
            <div className="flex items-center gap-2">
              <RiWalletLine className="h-4 w-4 text-muted-foreground" />
              <span>All Accounts</span>
            </div>
          </SelectItem>
          {accounts.map((account) => (
            <SelectItem key={account.id} value={account.id}>
              {account.name}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>

      {/* Date Range Selector */}
      <DateRangePicker
        value={dateRange}
        onChange={updateDateRange}
        className="!h-9 w-fit"
        placeholder="Date"
      />

      {/* Horizon Selector */}
      <div className="flex items-center !h-9 border border-input box-border">
        {HORIZON_OPTIONS.map((option) => (
          <button
            key={option.value}
            type="button"
            className={cn(
              "h-full px-3 text-xs font-medium transition-colors",
              currentHorizon === option.value
                ? "bg-primary text-primary-foreground"
                : "bg-transparent text-foreground hover:bg-muted"
            )}
            onClick={() => updateFilters("horizon", option.value)}
          >
            {option.label}
          </button>
        ))}
      </div>
    </div>
  );
}
