"use client";

import { useEffect } from "react";
import { useSearchParams } from "next/navigation";
import {
  GLOBAL_FILTER_STORAGE_KEY,
  getGlobalFilterQueryString,
  hasGlobalFilters,
  parseGlobalFiltersFromSearchParams,
} from "@/lib/filters/global-filters";

export function useFilterPersistence() {
  const searchParams = useSearchParams();

  useEffect(() => {
    const filters = parseGlobalFiltersFromSearchParams(searchParams);
    const queryString = getGlobalFilterQueryString(filters);

    if (!hasGlobalFilters(filters) || !queryString) {
      localStorage.removeItem(GLOBAL_FILTER_STORAGE_KEY);
      return;
    }

    localStorage.setItem(GLOBAL_FILTER_STORAGE_KEY, queryString);
  }, [searchParams]);
}
