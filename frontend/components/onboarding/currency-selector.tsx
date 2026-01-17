"use client";

import { RiQuestionLine } from "@remixicon/react";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { Label } from "@/components/ui/label";
import { FUNCTIONAL_CURRENCIES, CURRENCIES, type Currency, type FunctionalCurrency } from "@/lib/constants";

type CurrencyOption = Currency | FunctionalCurrency;

interface CurrencySelectorProps {
  value: string;
  onChange: (value: string) => void;
  label?: string;
  showTooltip?: boolean;
  /** Use all currencies instead of functional currencies only */
  useAllCurrencies?: boolean;
}

export function CurrencySelector({
  value,
  onChange,
  label = "Functional Currency",
  showTooltip = true,
  useAllCurrencies = false,
}: CurrencySelectorProps) {
  const currencies: readonly CurrencyOption[] = useAllCurrencies ? CURRENCIES : FUNCTIONAL_CURRENCIES;

  return (
    <div className="space-y-2">
      <div className="flex items-center gap-2">
        <Label>{label}</Label>
        {showTooltip && (
          <TooltipProvider>
            <Tooltip>
              <TooltipTrigger type="button">
                <RiQuestionLine className="h-4 w-4 text-muted-foreground" />
              </TooltipTrigger>
              <TooltipContent className="max-w-xs">
                <p>
                  Your functional currency is the primary currency you use for budgeting and
                  reporting. All amounts will be converted to this currency for charts and
                  summaries.
                </p>
              </TooltipContent>
            </Tooltip>
          </TooltipProvider>
        )}
      </div>
      <Select value={value} onValueChange={(v) => v && onChange(v)}>
        <SelectTrigger>
          <SelectValue placeholder="Select a currency" />
        </SelectTrigger>
        <SelectContent>
          {currencies.map((currency) => (
            <SelectItem key={currency.code} value={currency.code}>
              <span className="flex items-center gap-2">
                <span className="font-medium">{currency.code}</span>
                <span className="text-muted-foreground">
                  {currency.symbol} - {currency.name}
                </span>
              </span>
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </div>
  );
}
