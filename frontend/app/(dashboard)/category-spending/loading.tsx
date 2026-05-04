import { HeaderSkeleton, FiltersSkeleton, ChartSkeleton, TableSkeleton } from "@/components/skeletons/page-skeletons";

export default function Loading() {
  return (
    <>
      <HeaderSkeleton title="Category Spending" />
      <div className="flex flex-1 flex-col gap-4 p-4 pt-0">
        <FiltersSkeleton />
        <ChartSkeleton height={360} />
        <TableSkeleton rows={10} />
      </div>
    </>
  );
}
