"use client";

import { useEffect } from "react";
import { useRouter, useSearchParams } from "next/navigation";

const STORAGE_KEY = "dashboardFilters";

export function useFilterPersistence() {
  const router = useRouter();
  const searchParams = useSearchParams();

  useEffect(() => {
    const current = searchParams.toString();
    if (!current) {
      return;
    }

    localStorage.setItem(STORAGE_KEY, current);
  }, [searchParams]);

  useEffect(() => {
    const current = searchParams.toString();
    if (current) {
      return;
    }

    const stored = localStorage.getItem(STORAGE_KEY);
    if (!stored) {
      return;
    }

    router.replace(`?${stored}`, { scroll: false });
  }, [searchParams, router]);
}
