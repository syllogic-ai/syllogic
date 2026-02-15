export const GLOBAL_FILTER_STORAGE_KEY = "filters:global:v1";

export interface GlobalFilters {
  accountIds: string[];
  from?: string;
  to?: string;
  horizon?: string;
}

export function parseAccountParams(
  searchParams: Pick<URLSearchParams, "getAll">
): string[] {
  return Array.from(
    new Set(
      searchParams
        .getAll("account")
        .flatMap((value) => value.split(","))
        .map((value) => value.trim())
        .filter((value) => value.length > 0 && value !== "all")
    )
  );
}

export function parseGlobalFiltersFromSearchParams(
  searchParams: Pick<URLSearchParams, "get" | "getAll">
): GlobalFilters {
  const accountIds = parseAccountParams(searchParams);
  const from = searchParams.get("from")?.trim() || undefined;
  const to = searchParams.get("to")?.trim() || undefined;
  const horizon = from ? undefined : searchParams.get("horizon")?.trim() || undefined;

  return {
    accountIds,
    from,
    to,
    horizon,
  };
}

export function parseGlobalFiltersFromQueryString(
  queryString: string
): GlobalFilters {
  const normalized = queryString.startsWith("?")
    ? queryString.slice(1)
    : queryString;
  const params = new URLSearchParams(normalized);
  return parseGlobalFiltersFromSearchParams(params);
}

export function hasGlobalFilters(filters: GlobalFilters): boolean {
  return Boolean(
    filters.accountIds.length > 0 ||
      filters.from ||
      filters.to ||
      filters.horizon
  );
}

export function toGlobalFilterSearchParams(
  filters: GlobalFilters
): URLSearchParams {
  const params = new URLSearchParams();

  filters.accountIds.forEach((accountId) => {
    params.append("account", accountId);
  });

  if (filters.from) {
    params.set("from", filters.from);
    if (filters.to) {
      params.set("to", filters.to);
    }
  } else if (filters.horizon) {
    params.set("horizon", filters.horizon);
  }

  return params;
}

export function getGlobalFilterQueryString(filters: GlobalFilters): string {
  return toGlobalFilterSearchParams(filters).toString();
}

export function normalizeGlobalFilterQueryString(
  queryString: string | null | undefined
): string {
  if (!queryString) {
    return "";
  }

  return getGlobalFilterQueryString(
    parseGlobalFiltersFromQueryString(queryString)
  );
}

export function resolveGlobalFilterQueryString(
  currentQueryString: string,
  storedQueryString: string | null
): string {
  const current = normalizeGlobalFilterQueryString(currentQueryString);
  if (current) {
    return current;
  }

  return normalizeGlobalFilterQueryString(storedQueryString);
}
