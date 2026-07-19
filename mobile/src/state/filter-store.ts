import { create } from 'zustand';

import type { SavedViewFilters } from '@/api/types';

export const EMPTY_FILTERS: SavedViewFilters = {
  account_ids: [],
  account_types: [],
  currencies: [],
};

type FilterState = {
  filters: SavedViewFilters;
  setFilters: (filters: SavedViewFilters) => void;
  reset: () => void;
};

export const useFilterStore = create<FilterState>((set) => ({
  filters: EMPTY_FILTERS,
  setFilters: (filters) => set({ filters }),
  reset: () => set({ filters: EMPTY_FILTERS }),
}));

export function applyFilters<T extends { account_id: string; account_type?: string; currency?: string }>(
  items: T[],
  filters: SavedViewFilters,
): T[] {
  return items.filter((item) => {
    if (filters.account_ids.length && !filters.account_ids.includes(item.account_id)) return false;
    if (filters.account_types.length && item.account_type && !filters.account_types.includes(item.account_type))
      return false;
    if (filters.currencies.length && item.currency && !filters.currencies.includes(item.currency)) return false;
    return true;
  });
}
