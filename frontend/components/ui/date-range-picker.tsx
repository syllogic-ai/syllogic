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
  subDays,
  subMonths,
  format,
} from "date-fns";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";
import { Calendar } from "@/components/ui/calendar";
import { RiCalendarLine, RiArrowDownSLine } from "@remixicon/react";
import { cn } from "@/lib/utils";

// Date range presets
const datePresets = [
  { label: "Today", getValue: () => ({ from: startOfDay(new Date()), to: endOfDay(new Date()) }) },
  { label: "Yesterday", getValue: () => ({ from: startOfDay(subDays(new Date(), 1)), to: endOfDay(subDays(new Date(), 1)) }) },
  { label: "This Week", getValue: () => ({ from: startOfWeek(new Date(), { weekStartsOn: 1 }), to: endOfWeek(new Date(), { weekStartsOn: 1 }) }) },
  { label: "This Month", getValue: () => ({ from: startOfMonth(new Date()), to: endOfMonth(new Date()) }) },
  { label: "Last Month", getValue: () => ({ from: startOfMonth(subMonths(new Date(), 1)), to: endOfMonth(subMonths(new Date(), 1)) }) },
  { label: "This Quarter", getValue: () => ({ from: startOfQuarter(new Date()), to: endOfQuarter(new Date()) }) },
  { label: "This Year", getValue: () => ({ from: startOfYear(new Date()), to: endOfYear(new Date()) }) },
];

interface DateRangePickerProps {
  value: DateRange | undefined;
  onChange: (range: DateRange | undefined) => void;
  className?: string;
  placeholder?: string;
  showIcon?: boolean;
}

export function DateRangePicker({
  value,
  onChange,
  className,
  placeholder = "All time",
  showIcon = true,
}: DateRangePickerProps) {
  const [open, setOpen] = React.useState(false);

  const getDisplayText = () => {
    if (!value?.from) return placeholder;
    if (!value.to) return format(value.from, "MMM d, yyyy");
    return `${format(value.from, "MMM d")} - ${format(value.to, "MMM d, yyyy")}`;
  };

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger
        className={cn(
          "flex items-center justify-between gap-2 border border-input bg-transparent px-2.5 text-xs hover:bg-muted transition-colors",
          className
        )}
      >
        {showIcon && <RiCalendarLine className="h-4 w-4 text-muted-foreground" />}
        <span className="truncate">{getDisplayText()}</span>
        <RiArrowDownSLine className="h-4 w-4 shrink-0 text-muted-foreground" />
      </PopoverTrigger>
      <PopoverContent align="start" className="w-auto p-0">
        <div className="flex">
          <div className="border-r p-2 space-y-0.5 w-28">
            <button
              type="button"
              onClick={() => {
                onChange(undefined);
                setOpen(false);
              }}
              className={cn(
                "w-full px-2 py-1.5 text-left text-xs hover:bg-accent",
                !value?.from && "bg-accent"
              )}
            >
              All time
            </button>
            {datePresets.map((preset) => (
              <button
                key={preset.label}
                type="button"
                onClick={() => {
                  onChange(preset.getValue());
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
              selected={value}
              onSelect={(range) => onChange(range)}
              numberOfMonths={1}
              defaultMonth={value?.from}
            />
          </div>
        </div>
      </PopoverContent>
    </Popover>
  );
}
