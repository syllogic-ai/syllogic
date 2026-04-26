import { HeaderSkeleton, CardGridSkeleton, DetailListSkeleton } from "@/components/skeletons/page-skeletons";

export default function Loading() {
  return (
    <>
      <HeaderSkeleton title="Accounts" />
      <div className="flex flex-1 flex-col gap-6 p-4 pt-0">
        <CardGridSkeleton count={4} />
        <DetailListSkeleton rows={6} />
      </div>
    </>
  );
}
