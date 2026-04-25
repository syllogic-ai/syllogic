"use server";

import { rangeToDates, type Range } from "@/lib/utils/date-ranges";

// Re-export for consumers that import Range from this module
export type { Range } from "@/lib/utils/date-ranges";

export async function fetchHistoryRange(range: Range) {
  const { getPortfolioHistory } = await import("@/lib/api/investments");
  const { from, to } = rangeToDates(range);
  return getPortfolioHistory(from, to);
}

export async function searchSymbolsAction(q: string) {
  if (!q.trim()) return [];
  const { searchSymbols } = await import("@/lib/api/investments");
  return searchSymbols(q);
}

export async function fetchHoldingHistoryRange(holdingId: string, range: Range) {
  const { getHoldingHistory } = await import("@/lib/api/investments");
  const { from, to } = rangeToDates(range);
  return getHoldingHistory(holdingId, from, to);
}

export async function syncAllInvestmentsAction(): Promise<{ count: number }> {
  const { syncAllInvestments } = await import("@/lib/api/investments");
  return syncAllInvestments();
}
