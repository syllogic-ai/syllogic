import { Skeleton } from "@/components/ui/skeleton";

/**
 * Route-group loading boundary for every page under (dashboard). Next.js shows
 * this instantly on navigation while the server renders the target segment
 * (layout session/onboarding checks + the page's data), so the app feels
 * responsive instead of frozen on the previous screen.
 *
 * Kept intentionally generic — it renders for /, /transactions, /settings, etc.
 * — so it must not assume any one page's title or layout. Page-specific
 * skeletons (e.g. DashboardSkeleton) live behind in-page <Suspense> boundaries.
 */
export default function DashboardSegmentLoading() {
  return (
    <>
      {/* Header bar placeholder (matches the 48px Header height) */}
      <div className="flex h-12 shrink-0 items-center px-4">
        <Skeleton className="h-4 w-32" />
      </div>
      <div className="flex flex-1 flex-col gap-4 p-4 pt-0">
        <div className="grid gap-4 md:grid-cols-3">
          <Skeleton className="h-28 w-full" />
          <Skeleton className="h-28 w-full" />
          <Skeleton className="h-28 w-full" />
        </div>
        <Skeleton className="h-72 w-full" />
        <Skeleton className="h-48 w-full" />
      </div>
    </>
  );
}
