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
const DEFAULT_HORIZON = 30 as SupportedHorizon;
const DEFAULT_SORT = "bookedAt";
const DEFAULT_ORDER = "desc";

export type CategorySpendingSortField =
  | "bookedAt"
  | "amount"
  | "description"
  | "merchant";
export type CategorySpendingSortOrder = "asc" | "desc";

export interface ParsedCategorySpendingQueryParams {
  accountIds?: string[];
  dateFrom?: string;
  dateTo?: string;
  horizon?: SupportedHorizon;
  effectiveHorizon?: SupportedHorizon;
  categoryIds: string[];
  page: number;
  pageSize: number;
  sort: CategorySpendingSortField;
  order: CategorySpendingSortOrder;
}

interface CategorySpendingQueryOptions {
  categoryIds?: string[];
  categoryId?: string | null;
  accountIds?: string[];
  dateFrom?: string;
  dateTo?: string;
  horizon?: number | string | null;
  page?: number;
  pageSize?: number;
  sort?: CategorySpendingSortField;
  order?: CategorySpendingSortOrder;
}

type SearchParamsInput = {
  [key: string]: string | string[] | undefined;
};

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

function parsePositiveInt(value: string | undefined | null, fallback: number): number {
  if (!value) {
    return fallback;
  }

  const parsed = Number.parseInt(value, 10);
  if (!Number.isFinite(parsed) || parsed < 1) {
    return fallback;
  }

  return parsed;
}

function clamp(value: number, min: number, max: number): number {
  return Math.max(min, Math.min(max, value));
}

function parseCategoryParams(
  searchParams: Pick<URLSearchParams, "getAll">
): string[] {
  return Array.from(
    new Set(
      searchParams
        .getAll("category")
        .flatMap((value) => value.split(","))
        .map((value) => value.trim())
        .filter(Boolean)
    )
  );
}

function parseSortField(value: string | undefined | null): CategorySpendingSortField {
  if (
    value === "bookedAt" ||
    value === "amount" ||
    value === "description" ||
    value === "merchant"
  ) {
    return value;
  }
  return DEFAULT_SORT;
}

function parseSortOrder(value: string | undefined | null): CategorySpendingSortOrder {
  if (value === "asc" || value === "desc") {
    return value;
  }
  return DEFAULT_ORDER;
}

export function parseCategorySpendingSearchParams(
  params: SearchParamsInput
): ParsedCategorySpendingQueryParams {
  const searchParams = toURLSearchParams(params);
  const accountIds = parseAccountParams(searchParams);
  const dateFrom = parseIsoDateParam(searchParams.get("from"));
  const parsedDateTo = parseIsoDateParam(searchParams.get("to"));
  const dateTo =
    dateFrom && parsedDateTo && parsedDateTo >= dateFrom
      ? parsedDateTo
      : undefined;

  const categoryIds = parseCategoryParams(searchParams);
  const horizon = dateFrom ? undefined : parseHorizonParam(searchParams.get("horizon"));
  const page = parsePositiveInt(searchParams.get("page"), DEFAULT_PAGE);
  const pageSize = clamp(
    parsePositiveInt(searchParams.get("pageSize"), DEFAULT_PAGE_SIZE),
    MIN_PAGE_SIZE,
    MAX_PAGE_SIZE
  );
  const sort = parseSortField(searchParams.get("sort"));
  const order = parseSortOrder(searchParams.get("order"));

  return {
    accountIds: accountIds.length > 0 ? accountIds : undefined,
    dateFrom,
    dateTo,
    horizon,
    effectiveHorizon: dateFrom ? undefined : (horizon ?? DEFAULT_HORIZON),
    categoryIds,
    page,
    pageSize,
    sort,
    order,
  };
}

export function buildCategorySpendingQuery({
  categoryIds,
  categoryId,
  accountIds,
  dateFrom,
  dateTo,
  horizon,
  page,
  pageSize,
  sort,
  order,
}: CategorySpendingQueryOptions): string {
  const params = new URLSearchParams();

  const normalizedCategoryIds = Array.from(
    new Set(
      (categoryIds ?? [])
        .concat(categoryId ? [categoryId] : [])
        .map((value) => value.trim())
        .filter(Boolean)
    )
  );
  normalizedCategoryIds.forEach((id) => params.append("category", id));

  if (accountIds?.length) {
    Array.from(new Set(accountIds.map((value) => value.trim()).filter(Boolean))).forEach(
      (accountId) => params.append("account", accountId)
    );
  }

  const normalizedFrom = parseIsoDateParam(dateFrom);
  const normalizedTo = parseIsoDateParam(dateTo);

  if (normalizedFrom) {
    params.set("from", normalizedFrom);
    if (normalizedTo && normalizedTo >= normalizedFrom) {
      params.set("to", normalizedTo);
    }
  } else {
    const normalizedHorizon = parseHorizonParam(
      typeof horizon === "number"
        ? String(horizon)
        : typeof horizon === "string"
          ? horizon
          : undefined
    );

    if (normalizedHorizon) {
      if (normalizedHorizon !== DEFAULT_HORIZON) {
        params.set("horizon", String(normalizedHorizon));
      }
    }
  }

  if (typeof page === "number" && Number.isFinite(page) && page > DEFAULT_PAGE) {
    params.set("page", String(Math.floor(page)));
  }

  if (
    typeof pageSize === "number" &&
    Number.isFinite(pageSize)
  ) {
    const normalizedPageSize = clamp(Math.floor(pageSize), MIN_PAGE_SIZE, MAX_PAGE_SIZE);
    if (normalizedPageSize !== DEFAULT_PAGE_SIZE) {
      params.set("pageSize", String(normalizedPageSize));
    }
  }

  if (sort && sort !== DEFAULT_SORT) {
    params.set("sort", sort);
  }

  if (order && order !== DEFAULT_ORDER) {
    params.set("order", order);
  }

  return params.toString();
}
