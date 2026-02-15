import {
  parseHorizonParam,
  parseIsoDateParam,
  type SupportedHorizon,
} from "@/lib/dashboard/query-params";
import { parseAccountParams } from "@/lib/filters/global-filters";

const DEFAULT_PAGE = 1;
const DEFAULT_PAGE_SIZE = 20;
const MIN_PAGE_SIZE = 10;
const MAX_PAGE_SIZE = 100;
const DEFAULT_HORIZON: SupportedHorizon = 30;
const DEFAULT_SORT = "bookedAt";
const DEFAULT_ORDER = "desc";

export type TransactionSortField = "bookedAt" | "amount" | "description" | "merchant";
export type TransactionSortOrder = "asc" | "desc";

export interface TransactionsQueryState {
  page: number;
  pageSize: number;
  search?: string;
  category: string[];
  accountIds: string[];
  status: string[];
  subscription: string[];
  analytics: string[];
  minAmount?: string;
  maxAmount?: string;
  from?: string;
  to?: string;
  horizon?: SupportedHorizon;
  sort: TransactionSortField;
  order: TransactionSortOrder;
}

type SearchParamsInput = {
  [key: string]: string | string[] | undefined;
};

function clamp(value: number, min: number, max: number): number {
  return Math.max(min, Math.min(max, value));
}

function parsePositiveInt(value: string | undefined | null, fallback: number): number {
  if (!value) return fallback;
  const parsed = Number.parseInt(value, 10);
  if (!Number.isFinite(parsed) || parsed < 1) {
    return fallback;
  }
  return parsed;
}

function parseMultiValueParam(
  searchParams: Pick<URLSearchParams, "getAll">,
  key: string
): string[] {
  return Array.from(
    new Set(
      searchParams
        .getAll(key)
        .flatMap((value) => value.split(","))
        .map((value) => value.trim())
        .filter(Boolean)
    )
  );
}

function toURLSearchParams(params: SearchParamsInput): URLSearchParams {
  const nextParams = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (Array.isArray(value)) {
      value.forEach((entry) => nextParams.append(key, entry));
    } else if (typeof value === "string") {
      nextParams.append(key, value);
    }
  }
  return nextParams;
}

function parseSortField(value: string | undefined | null): TransactionSortField {
  if (value === "bookedAt" || value === "amount" || value === "description" || value === "merchant") {
    return value;
  }
  return DEFAULT_SORT;
}

function parseSortOrder(value: string | undefined | null): TransactionSortOrder {
  if (value === "asc" || value === "desc") {
    return value;
  }
  return DEFAULT_ORDER;
}

function normalizeDateRange(
  fromRaw: string | undefined,
  toRaw: string | undefined
): { from?: string; to?: string } {
  const from = parseIsoDateParam(fromRaw);
  const toCandidate = parseIsoDateParam(toRaw);
  if (!from) {
    return {};
  }

  if (!toCandidate) {
    return { from };
  }

  if (toCandidate < from) {
    return { from };
  }

  return { from, to: toCandidate };
}

function parseInternal(searchParams: URLSearchParams): TransactionsQueryState {
  const page = parsePositiveInt(searchParams.get("page"), DEFAULT_PAGE);
  const pageSize = clamp(
    parsePositiveInt(searchParams.get("pageSize"), DEFAULT_PAGE_SIZE),
    MIN_PAGE_SIZE,
    MAX_PAGE_SIZE
  );

  const search = searchParams.get("search")?.trim() || undefined;
  const category = parseMultiValueParam(searchParams, "category");
  const accountIds = parseAccountParams(searchParams);
  const status = parseMultiValueParam(searchParams, "status");
  const subscription = parseMultiValueParam(searchParams, "subscription");
  const analytics = parseMultiValueParam(searchParams, "analytics");
  const minAmount = searchParams.get("minAmount")?.trim() || undefined;
  const maxAmount = searchParams.get("maxAmount")?.trim() || undefined;
  const { from, to } = normalizeDateRange(searchParams.get("from") || undefined, searchParams.get("to") || undefined);
  const horizon = from
    ? undefined
    : parseHorizonParam(searchParams.get("horizon")) ?? DEFAULT_HORIZON;
  const sort = parseSortField(searchParams.get("sort"));
  const order = parseSortOrder(searchParams.get("order"));

  return {
    page,
    pageSize,
    search,
    category,
    accountIds,
    status,
    subscription,
    analytics,
    minAmount,
    maxAmount,
    from,
    to,
    horizon,
    sort,
    order,
  };
}

export function parseTransactionsSearchParams(
  searchParams: SearchParamsInput
): TransactionsQueryState {
  return parseInternal(toURLSearchParams(searchParams));
}

export function parseTransactionsSearchParamsFromUrlSearchParams(
  searchParams: URLSearchParams
): TransactionsQueryState {
  return parseInternal(searchParams);
}

export function toTransactionsSearchParams(
  state: TransactionsQueryState
): URLSearchParams {
  const params = new URLSearchParams();

  if (state.page !== DEFAULT_PAGE) {
    params.set("page", String(state.page));
  }
  if (state.pageSize !== DEFAULT_PAGE_SIZE) {
    params.set("pageSize", String(state.pageSize));
  }
  if (state.search) {
    params.set("search", state.search);
  }

  state.category.forEach((id) => params.append("category", id));
  state.accountIds.forEach((id) => params.append("account", id));
  state.status.forEach((id) => params.append("status", id));
  state.subscription.forEach((id) => params.append("subscription", id));
  state.analytics.forEach((id) => params.append("analytics", id));

  if (state.minAmount) {
    params.set("minAmount", state.minAmount);
  }
  if (state.maxAmount) {
    params.set("maxAmount", state.maxAmount);
  }

  if (state.from) {
    params.set("from", state.from);
    if (state.to) {
      params.set("to", state.to);
    }
  } else if (state.horizon) {
    params.set("horizon", String(state.horizon));
  }

  if (state.sort !== DEFAULT_SORT) {
    params.set("sort", state.sort);
  }
  if (state.order !== DEFAULT_ORDER) {
    params.set("order", state.order);
  }

  return params;
}

export function applyTransactionsQueryPatch(
  currentSearchParams: URLSearchParams,
  patch: Partial<TransactionsQueryState>
): URLSearchParams {
  const currentState = parseTransactionsSearchParamsFromUrlSearchParams(currentSearchParams);
  const nextState: TransactionsQueryState = {
    ...currentState,
    ...patch,
  };

  if (nextState.page < 1 || !Number.isFinite(nextState.page)) {
    nextState.page = DEFAULT_PAGE;
  }
  nextState.pageSize = clamp(nextState.pageSize, MIN_PAGE_SIZE, MAX_PAGE_SIZE);

  return toTransactionsSearchParams(nextState);
}
