import { notFound } from "next/navigation";
import {
  listHoldings,
  getHoldingHistory,
  getPortfolio,
} from "@/lib/api/investments";
import { HoldingDetailView } from "@/components/investments/HoldingDetailView";
import { rangeToDates } from "@/lib/actions/investments";

export const dynamic = "force-dynamic";

export default async function HoldingDetailPage({
  params,
}: {
  params: Promise<{ holdingId: string }>;
}) {
  const { holdingId } = await params;
  const { from, to } = rangeToDates("1M");
  const [holdings, history, portfolio] = await Promise.all([
    listHoldings(),
    getHoldingHistory(holdingId, from, to),
    getPortfolio(),
  ]);
  const holding = holdings.find((h) => h.id === holdingId);
  if (!holding) return notFound();
  return (
    <HoldingDetailView
      holding={holding}
      portfolio={portfolio}
      initialHistory={history}
    />
  );
}
