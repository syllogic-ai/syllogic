import {
  getPortfolio,
  listHoldings,
  getPortfolioHistory,
} from "@/lib/api/investments";
import { InvestmentsOverview } from "@/components/investments/InvestmentsOverview";
import { InvestmentsEmpty } from "@/components/investments/InvestmentsEmpty";
import { rangeToDates } from "@/lib/utils/date-ranges";

export async function InvestmentsSection() {
  const { from, to } = rangeToDates("1M");
  const [portfolio, holdings, history] = await Promise.all([
    getPortfolio(),
    listHoldings(),
    getPortfolioHistory(from, to),
  ]);

  if (holdings.length === 0) {
    return <InvestmentsEmpty />;
  }

  return (
    <InvestmentsOverview
      portfolio={portfolio}
      holdings={holdings}
      initialHistory={history}
      initialRange="1M"
    />
  );
}
