// Mirrors backend/app/routes/analytics.py:get_account_balances and
// backend/app/schemas.py (HoldingResponse, PortfolioSummary). Kept as plain
// types (not Zod) since these are trusted responses from our own backend.

export type AccountBalance = {
  account_id: string;
  name: string;
  balance: number;
  currency: string;
  account_type: string;
};

export type Holding = {
  id: string;
  account_id: string;
  symbol: string;
  name: string | null;
  currency: string;
  instrument_type: string;
  quantity: number;
  current_price: number | null;
  current_value_user_currency: number | null;
  is_stale: boolean;
};

export type PortfolioSummary = {
  total_value: number;
  total_value_today_change: number;
  currency: string;
};

export type SavedViewFilters = {
  account_ids: string[];
  account_types: string[];
  currencies: string[];
};

export type SavedView = {
  id: string;
  name: string;
  filters: SavedViewFilters;
  created_at: string;
};
