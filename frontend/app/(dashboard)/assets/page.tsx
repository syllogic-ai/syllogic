import { Suspense } from "react";
import { Header } from "@/components/layout/header";
import { CardGridSkeleton, DetailListSkeleton } from "@/components/skeletons/page-skeletons";
import { AssetsSection } from "./_sections";

export default function AssetsPage() {
  return (
    <>
      <Header title="Assets" />
      <div className="flex flex-1 flex-col gap-6 p-4 pt-0">
        <Suspense
          fallback={
            <>
              <CardGridSkeleton count={3} />
              <DetailListSkeleton rows={8} />
            </>
          }
        >
          <AssetsSection />
        </Suspense>
      </div>
    </>
  );
}
