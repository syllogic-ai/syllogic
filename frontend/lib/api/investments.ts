"use server";

import { getAuthenticatedSession, requireAuth } from "@/lib/auth-helpers";
import { getBackendBaseUrl } from "@/lib/backend-url";
import { createInternalAuthHeaders } from "@/lib/internal-auth";

export type Holding = {
  id: string;
  account_id: string;
  symbol: string;
  provider_symbol?: string | null;
  name: string | null;
  currency: string;
  instrument_type: "equity" | "etf" | "cash";
  quantity: string;
  avg_cost?: string | null;
  as_of_date?: string | null;
  source: "manual" | "ibkr_flex";
  current_price?: string | null;
  current_value_user_currency?: string | null;
  is_stale: boolean;
};

export type PortfolioAccount = {
  id: string;
  name: string;
  balance: string | number;
  type: string;
};

export type PortfolioSummary = {
  total_value: string;
  total_value_today_change: string;
  currency: string;
  accounts: PortfolioAccount[];
  allocation_by_type: Record<string, string>;
  allocation_by_currency: Record<string, string>;
};

export type ValuationPoint = { date: string; value: string };

export type SymbolSearchResult = {
  symbol: string;
  name: string;
  exchange?: string | null;
  currency?: string | null;
};

function buildUrl(path: string, query?: Record<string, string | undefined>): {
  url: string;
  pathWithQuery: string;
} {
  const backendBase = getBackendBaseUrl().replace(/\/+$/, "");
  const search = new URLSearchParams();
  if (query) {
    for (const [k, v] of Object.entries(query)) {
      if (v !== undefined && v !== null && v !== "") search.set(k, v);
    }
  }
  const qs = search.toString();
  const pathWithQuery = qs ? `${path}?${qs}` : path;
  return { url: `${backendBase}${pathWithQuery}`, pathWithQuery };
}

async function signedFetch(
  method: string,
  path: string,
  options: { query?: Record<string, string | undefined>; body?: unknown } = {},
): Promise<Response> {
  const userId = await requireAuth();
  if (!userId) throw new Error("Not authenticated");
  const { url, pathWithQuery } = buildUrl(path, options.query);
  const signatureHeaders = createInternalAuthHeaders({
    method,
    pathWithQuery,
    userId,
  });
  const headers: Record<string, string> = { ...signatureHeaders };
  let body: string | undefined;
  if (options.body !== undefined) {
    headers["Content-Type"] = "application/json";
    body = JSON.stringify(options.body);
  }
  return fetch(url, { method, headers, body, cache: "no-store" });
}

async function readJsonOrThrow<T>(resp: Response): Promise<T> {
  if (!resp.ok) {
    const text = await resp.text().catch(() => "");
    throw new Error(text || `Request failed: ${resp.status}`);
  }
  return (await resp.json()) as T;
}

export async function listHoldings(accountId?: string): Promise<Holding[]> {
  const resp = await signedFetch("GET", "/api/investments/holdings", {
    query: accountId ? { account_id: accountId } : undefined,
  });
  return readJsonOrThrow<Holding[]>(resp);
}

export async function getPortfolio(): Promise<PortfolioSummary> {
  const resp = await signedFetch("GET", "/api/investments/portfolio/summary");
  return readJsonOrThrow<PortfolioSummary>(resp);
}

export type InvestmentAccount = {
  id: string;
  name: string;
  base_currency: string;
  source: "manual" | "ibkr_flex";
};

export async function listInvestmentAccounts(): Promise<InvestmentAccount[]> {
  const portfolio = await getPortfolio();
  return portfolio.accounts.map((a) => ({
    id: a.id,
    name: a.name,
    base_currency: portfolio.currency,
    source: "manual",
  }));
}

export async function getPortfolioHistory(
  from: string,
  to: string,
): Promise<ValuationPoint[]> {
  const resp = await signedFetch("GET", "/api/investments/portfolio/history", {
    query: { from, to },
  });
  return readJsonOrThrow<ValuationPoint[]>(resp);
}

export async function getHoldingHistory(
  holdingId: string,
  from: string,
  to: string,
): Promise<ValuationPoint[]> {
  const resp = await signedFetch(
    "GET",
    `/api/investments/holdings/${holdingId}/history`,
    { query: { from, to } },
  );
  return readJsonOrThrow<ValuationPoint[]>(resp);
}

export async function searchSymbols(q: string): Promise<SymbolSearchResult[]> {
  const resp = await signedFetch("GET", "/api/investments/symbols/search", {
    query: { q },
  });
  return readJsonOrThrow<SymbolSearchResult[]>(resp);
}

export async function createBrokerConnection(payload: {
  provider: "ibkr_flex";
  flex_token: string;
  query_id_positions: string;
  query_id_trades: string;
  account_name: string;
  base_currency: string;
}): Promise<{ connection_id: string; account_id: string }> {
  const resp = await signedFetch("POST", "/api/investments/broker-connections", {
    body: payload,
  });
  return readJsonOrThrow<{ connection_id: string; account_id: string }>(resp);
}

export async function createManualAccount(
  name: string,
  base_currency: string,
): Promise<{ account_id: string }> {
  const resp = await signedFetch("POST", "/api/investments/manual-accounts", {
    body: { name, base_currency },
  });
  return readJsonOrThrow<{ account_id: string }>(resp);
}

export async function addManualHolding(
  accountId: string,
  payload: {
    symbol: string;
    quantity: string;
    instrument_type: "equity" | "etf" | "cash";
    currency: string;
    as_of_date?: string;
    avg_cost?: string;
  },
): Promise<{ holding_id: string }> {
  const resp = await signedFetch(
    "POST",
    `/api/investments/manual-accounts/${accountId}/holdings`,
    { body: payload },
  );
  return readJsonOrThrow<{ holding_id: string }>(resp);
}

export async function deleteHolding(holdingId: string): Promise<void> {
  const session = await getAuthenticatedSession();
  if (!session?.user?.id) throw new Error("Not authenticated");
  await signedFetch("DELETE", `/api/investments/holdings/${holdingId}`);
}

export async function syncAllInvestments(): Promise<{ count: number }> {
  const resp = await signedFetch("POST", "/api/investments/sync-all");
  return readJsonOrThrow<{ count: number }>(resp);
}

export async function updateHolding(
  holdingId: string,
  payload: {
    symbol?: string;
    quantity?: string;
    avg_cost?: string | null;
    as_of_date?: string | null;
    provider_symbol?: string | null;
  },
): Promise<void> {
  const session = await getAuthenticatedSession();
  if (!session?.user?.id) throw new Error("Not authenticated");
  const resp = await signedFetch("PATCH", `/api/investments/holdings/${holdingId}`, {
    body: payload,
  });
  if (!resp.ok) {
    const text = await resp.text().catch(() => "");
    throw new Error(text || `Request failed: ${resp.status}`);
  }
}
