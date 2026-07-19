import { API_URL } from '@/config';
import { getSessionToken, getAuthHeader } from '@/auth/session';
import type { AccountBalance, Holding, PortfolioSummary, SavedView, SavedViewFilters } from './types';

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

export const api = {
  getAccountBalances: () => request<AccountBalance[]>('/analytics/account-balances'),
  getHoldings: () => request<Holding[]>('/investments/holdings'),
  getPortfolioSummary: () => request<PortfolioSummary>('/investments/portfolio/summary'),
  listSavedViews: () => request<SavedView[]>('/saved-views'),
  createSavedView: (name: string, filters: SavedViewFilters) =>
    request<SavedView>('/saved-views', {
      method: 'POST',
      body: JSON.stringify({ name, filters }),
    }),
  deleteSavedView: (id: string) => request<void>(`/saved-views/${id}`, { method: 'DELETE' }),
};

export { ApiError };
