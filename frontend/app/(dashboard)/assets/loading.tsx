import { HeaderSkeleton, CardGridSkeleton, DetailListSkeleton } from "@/components/skeletons/page-skeletons";

export default function Loading() {
  return (
    <>
      <HeaderSkeleton title="Assets" />
      <div className="flex flex-1 flex-col gap-6 p-4 pt-0">
        <CardGridSkeleton count={3} />
        <DetailListSkeleton rows={8} />
      </div>
    </>
  );
}
