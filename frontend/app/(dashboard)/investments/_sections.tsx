import {
  getPortfolio,
  listHoldings,
  getPortfolioHistory,
} from "@/lib/api/investments";
import { InvestmentsOverview } from "@/components/investments/InvestmentsOverview";
import { InvestmentsEmpty } from "@/components/investments/InvestmentsEmpty";
import { rangeToDates } from "@/lib/utils/date-ranges";

export async function InvestmentsSection() {
  const [portfolio, holdings] = await Promise.all([
    getPortfolio(),
    listHoldings(),
  ]);

  if (holdings.length === 0) {
    return <InvestmentsEmpty />;
  }

  const { from, to } = rangeToDates("1M");
  const history = await getPortfolioHistory(from, to);

  return (
    <InvestmentsOverview
      portfolio={portfolio}
      holdings={holdings}
      initialHistory={history}
      initialRange="1M"
    />
  );
}
