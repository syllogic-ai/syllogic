import { parseAccountParams } from "@/lib/filters/global-filters";

export type SupportedHorizon = 7 | 30 | 365;
const SUPPORTED_HORIZONS = new Set<number>([7, 30, 365]);

export interface ParsedDashboardQueryParams {
  accountIds?: string[];
  dateFrom?: string;
  dateTo?: string;
  horizon: SupportedHorizon;
  effectiveHorizon?: SupportedHorizon;
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

export function parseIsoDateParam(value: string | undefined | null): string | undefined {
  if (!value) {
    return undefined;
  }

  const trimmed = value.trim();
  if (!/^\d{4}-\d{2}-\d{2}$/.test(trimmed)) {
    return undefined;
  }

  const date = new Date(`${trimmed}T00:00:00.000Z`);
  if (Number.isNaN(date.getTime())) {
    return undefined;
  }

  return date.toISOString().slice(0, 10) === trimmed ? trimmed : undefined;
}

export function parseHorizonParam(value: string | undefined | null): SupportedHorizon | undefined {
  if (!value) {
    return undefined;
  }

  const parsed = Number.parseInt(value.trim(), 10);
  if (!Number.isFinite(parsed) || !SUPPORTED_HORIZONS.has(parsed)) {
    return undefined;
  }

  return parsed as SupportedHorizon;
}

export function parseDashboardSearchParams(
  params: SearchParamsInput
): ParsedDashboardQueryParams {
  const urlSearchParams = toURLSearchParams(params);
  const accountIds = parseAccountParams(urlSearchParams);

  const dateFrom = parseIsoDateParam(urlSearchParams.get("from"));
  const parsedDateTo = parseIsoDateParam(urlSearchParams.get("to"));
  const dateTo =
    dateFrom && parsedDateTo && parsedDateTo < dateFrom ? undefined : parsedDateTo;

  const horizon = parseHorizonParam(urlSearchParams.get("horizon")) ?? 30;

  return {
    accountIds: accountIds.length > 0 ? accountIds : undefined,
    dateFrom,
    dateTo,
    horizon,
    effectiveHorizon: dateFrom ? undefined : horizon,
  };
}
