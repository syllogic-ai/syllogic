import { notFound } from "next/navigation";
import {
  listHoldings,
  getHoldingHistory,
  getPortfolio,
} from "@/lib/api/investments";
import { HoldingDetailView } from "@/components/investments/HoldingDetailView";
import { rangeToDates } from "@/lib/utils/date-ranges";

export const dynamic = "force-dynamic";

export default async function HoldingDetailPage({
  params,
}: {
  params: Promise<{ holdingId: string }>;
}) {
  const { holdingId } = await params;
  const { from, to } = rangeToDates("1M");
  // Backend exposes GET /holdings (list) but not GET /holdings/:id,
  // so we fetch holdings + portfolio first, validate the ID, then fetch history.
  // This ensures notFound() is called before getHoldingHistory so an invalid
  // holdingId never reaches the backend history endpoint.
  const [holdings, portfolio] = await Promise.all([listHoldings(), getPortfolio()]);
  const holding = holdings.find((h) => h.id === holdingId);
  if (!holding) return notFound();
  const history = await getHoldingHistory(holdingId, from, to);
  return (
    <HoldingDetailView
      holding={holding}
      portfolio={portfolio}
      initialHistory={history}
    />
  );
}
