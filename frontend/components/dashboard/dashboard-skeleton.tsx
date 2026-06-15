import { Skeleton } from "@/components/ui/skeleton";

/**
 * Layout-matching placeholder for the dashboard body. Rendered while the
 * dashboard's server-side data (`getDashboardData` + `getUserAccounts`) is
 * still resolving, so navigation paints instantly instead of blocking on
 * ~10 DB queries. Mirrors the row structure in `app/(dashboard)/page.tsx`.
 */
export function DashboardSkeleton() {
  return (
    <div className="flex flex-1 flex-col gap-4 p-4 pt-0">
      {/* Filters row */}
      <div className="flex items-center justify-between">
        <Skeleton className="h-9 w-64" />
        <Skeleton className="h-9 w-28" />
      </div>

      {/* Row 1: KPI cards */}
      <div className="grid gap-4 md:grid-cols-4">
        {Array.from({ length: 4 }).map((_, i) => (
          <Skeleton key={i} className="h-32 w-full" />
        ))}
      </div>

      {/* Row 2: charts */}
      <div className="grid gap-4 md:grid-cols-5">
        <Skeleton className="col-span-3 h-80 w-full" />
        <Skeleton className="col-span-2 h-80 w-full" />
      </div>

      {/* Row 3: cash flow sankey */}
      <Skeleton className="h-96 w-full" />

      {/* Row 4: assets overview */}
      <Skeleton className="h-64 w-full" />

      {/* Row 5: investments summary */}
      <Skeleton className="h-48 w-full" />
    </div>
  );
}
