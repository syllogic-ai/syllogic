import { Suspense } from "react";
import { Header } from "@/components/layout/header";
import { CardGridSkeleton, ChartSkeleton, DetailListSkeleton } from "@/components/skeletons/page-skeletons";
import { InvestmentsSection } from "./_sections";

export default function InvestmentsPage() {
  return (
    <>
      <Header title="Investments" />
      <div className="flex flex-1 flex-col gap-6 p-4 pt-0">
        <Suspense
          fallback={
            <>
              <CardGridSkeleton count={3} />
              <ChartSkeleton />
              <DetailListSkeleton rows={6} />
            </>
          }
        >
          <InvestmentsSection />
        </Suspense>
      </div>
    </>
  );
}
