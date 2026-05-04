import { HeaderSkeleton, CardGridSkeleton, ChartSkeleton, DetailListSkeleton } from "@/components/skeletons/page-skeletons";

export default function Loading() {
  return (
    <>
      <HeaderSkeleton title="Investments" />
      <div className="flex flex-1 flex-col gap-6 p-4 pt-0">
        <CardGridSkeleton count={3} />
        <ChartSkeleton />
        <DetailListSkeleton rows={6} />
      </div>
    </>
  );
}
