import { Suspense } from "react";
import { CardGridSkeleton, DetailListSkeleton } from "@/components/skeletons/page-skeletons";
import { SubscriptionsSection } from "./_sections";

export default function SubscriptionsPage() {
  return (
    <div className="flex min-h-[calc(100vh-4rem)] flex-col gap-4 p-4">
      <Suspense
        fallback={
          <>
            <CardGridSkeleton count={4} />
            <DetailListSkeleton rows={8} />
          </>
        }
      >
        <SubscriptionsSection />
      </Suspense>
    </div>
  );
}
