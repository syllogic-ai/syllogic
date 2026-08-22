// Mirrors backend/app/routes/analytics.py:get_account_balances and
// backend/app/schemas.py (HoldingResponse, PortfolioSummary). Kept as plain
// types (not Zod) since these are trusted responses from our own backend.

export type AccountBalance = {
  account_id: string;
  name: string;
  balance: number;
  currency: string;
  account_type: string;
  logo_url: string | null;
};

// The investments routes declare `response_model=`, so Pydantic v2 serializes
// their Decimal fields as JSON *strings* ("570.30"), unlike the plain-dict
// analytics routes where FastAPI's jsonable_encoder emits numbers. The web
// client models this the same way (frontend/lib/api/investments.ts). These
// `*Wire` types are the raw shape; api/client.ts coerces them to the number
// types below so components can do arithmetic without thinking about it.
export type HoldingWire = Omit<
  Holding,
  'quantity' | 'current_price' | 'current_value_user_currency'
> & {
  quantity: string;
  current_price: string | null;
  current_value_user_currency: string | null;
};

export type PortfolioSummaryWire = Omit<
  PortfolioSummary,
  'total_value' | 'total_value_today_change'
> & {
  total_value: string;
  total_value_today_change: string;
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
