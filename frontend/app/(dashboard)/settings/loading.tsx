import { HeaderSkeleton, DetailListSkeleton } from "@/components/skeletons/page-skeletons";

export default function Loading() {
  return (
    <>
      <HeaderSkeleton title="Settings" />
      <div className="flex flex-1 flex-col gap-4 p-4 pt-0">
        <DetailListSkeleton rows={10} />
      </div>
    </>
  );
}
