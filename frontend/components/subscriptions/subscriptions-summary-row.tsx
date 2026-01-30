"use client";

import type { SubscriptionOrSuggestion } from "./subscriptions-client";

interface SubscriptionsSummaryRowProps {
  data: SubscriptionOrSuggestion[];
}

/**
 * Monthly equivalent multipliers for different frequencies
 */
const frequencyMultipliers: Record<string, number> = {
  weekly: 4,      // 4 weeks per month
  biweekly: 2,    // 2 bi-weeks per month
  monthly: 1,     // 1:1
  quarterly: 1/3, // once per 3 months
  yearly: 1/12,   // once per 12 months
};

/**
 * Calculate the monthly equivalent for a subscription
 */
function calculateMonthlyEquivalent(item: SubscriptionOrSuggestion): number {
  const amount = Math.abs(parseFloat(item.amount || "0"));
  const multiplier = frequencyMultipliers[item.frequency] || 1;
  return amount * multiplier;
}

export function SubscriptionsSummaryRow({
  data,
}: SubscriptionsSummaryRowProps) {
  // Only sum active subscriptions (exclude suggestions)
  const activeSubscriptions = data.filter((s) => !s.isSuggestion && s.isActive);

  const monthlyTotal = activeSubscriptions.reduce((sum, subscription) => {
    return sum + calculateMonthlyEquivalent(subscription);
  }, 0);

  // Get currency from first subscription (assuming all use same currency)
  const currency = data.find((d) => !d.isSuggestion)?.currency || "EUR";

  return (
    <div className="border-t bg-muted/30 px-4 py-3 flex items-center justify-between">
      <span className="text-sm font-medium text-muted-foreground">
        Monthly Total
      </span>
      <span className="text-sm font-mono font-semibold">
        {monthlyTotal.toFixed(2)} {currency}
      </span>
    </div>
  );
}
