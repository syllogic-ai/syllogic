import { HeaderSkeleton, FiltersSkeleton, TableSkeleton } from "@/components/skeletons/page-skeletons";

export default function Loading() {
  return (
    <>
      <HeaderSkeleton title="Transactions" />
      <div className="flex h-[calc(100vh-4rem)] flex-col gap-4 p-4 pt-0">
        <FiltersSkeleton />
        <TableSkeleton rows={14} />
      </div>
    </>
  );
}
