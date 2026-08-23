import { API_URL } from '@/config';
import { getSessionToken, getAuthHeader } from '@/auth/session';
import type {
  AccountBalance,
  Holding,
  HoldingWire,
  PortfolioSummary,
  PortfolioSummaryWire,
  SavedView,
  SavedViewFilters,
} from './types';

class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const cookie = await getSessionToken();
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...getAuthHeader(cookie),
    ...(init?.headers as Record<string, string> | undefined),
  };
  const res = await fetch(`${API_URL}/api${path}`, { ...init, headers });

  if (!res.ok) {
    const body = await res.text().catch(() => '');
    throw new ApiError(res.status, body || res.statusText);
  }
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

// Decimal-as-string → number. Returns null for null/undefined so optional
// money fields stay optional rather than becoming NaN.
function num(value: string | null | undefined): number | null {
  if (value == null) return null;
  const parsed = Number(value);
  return Number.isNaN(parsed) ? null : parsed;
}

function toHolding(wire: HoldingWire): Holding {
  return {
    ...wire,
    quantity: num(wire.quantity) ?? 0,
    current_price: num(wire.current_price),
    current_value_user_currency: num(wire.current_value_user_currency),
  };
}

function toPortfolioSummary(wire: PortfolioSummaryWire): PortfolioSummary {
  return {
    ...wire,
    total_value: num(wire.total_value) ?? 0,
    total_value_today_change: num(wire.total_value_today_change) ?? 0,
  };
}

export const api = {
  getAccountBalances: () => request<AccountBalance[]>('/analytics/account-balances'),
  getHoldings: () => request<HoldingWire[]>('/investments/holdings').then((h) => h.map(toHolding)),
  getPortfolioSummary: () =>
    request<PortfolioSummaryWire>('/investments/portfolio/summary').then(toPortfolioSummary),
  // The trailing slashes below are load-bearing. These backend routes are
  // declared as `@router.get("/")` under the `/api/saved-views` prefix, so a
  // request without the slash gets a 307 from FastAPI. That is harmless in
  // local dev, where we talk to FastAPI directly and our session cookie
  // survives the redirect — but in production we go through the Next.js proxy,
  // which signs an HMAC bound to the exact path. Following the redirect
  // changes the path, the signature no longer matches, and the request 401s.
  // See docs/mobile-widget-manual-checklist.md.
  listSavedViews: () => request<SavedView[]>('/saved-views/'),
  createSavedView: (name: string, filters: SavedViewFilters) =>
    request<SavedView>('/saved-views/', {
      method: 'POST',
      body: JSON.stringify({ name, filters }),
    }),
  deleteSavedView: (id: string) => request<void>(`/saved-views/${id}`, { method: 'DELETE' }),
};

export { ApiError };
