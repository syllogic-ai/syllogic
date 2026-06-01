import {
  getPortfolio,
  listHoldings,
  getPortfolioHistory,
} from "@/lib/api/investments";
import { InvestmentsOverview } from "@/components/investments/InvestmentsOverview";
import { InvestmentsEmpty } from "@/components/investments/InvestmentsEmpty";
import { rangeToDates } from "@/lib/utils/date-ranges";
import { getAuthenticatedSession } from "@/lib/auth-helpers";
import { isDemoRestrictedUserEmail } from "@/lib/demo-access";

export async function InvestmentsSection() {
  const { from, to } = rangeToDates("1M");
  const [portfolio, holdings, history, session] = await Promise.all([
    getPortfolio(),
    listHoldings(),
    getPortfolioHistory(from, to),
    getAuthenticatedSession(),
  ]);

  const isDemoRestricted = isDemoRestrictedUserEmail(session?.user?.email);

  if (holdings.length === 0) {
    return <InvestmentsEmpty isDemoRestricted={isDemoRestricted} />;
  }

  return (
    <InvestmentsOverview
      portfolio={portfolio}
      holdings={holdings}
      initialHistory={history}
      initialRange="1M"
      isDemoRestricted={isDemoRestricted}
    />
  );
}
