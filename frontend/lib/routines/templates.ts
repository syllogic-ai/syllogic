export type RoutineTemplate = {
  key: string;
  name: string;
  description: string;
  cron: string;
  timezone: string;
  scheduleHuman: string;
  prompt: string;
};

export const INVESTMENT_REVIEW_TEMPLATE: RoutineTemplate = {
  key: "investment-review",
  name: "Investment Strategy Review",
  description: "Weekly evidence-backed audit of household portfolio vs. strategy. Default GREEN unless ≥3 sources support a change.",
  cron: "0 8 * * 1",
  timezone: "Europe/Amsterdam",
  scheduleHuman: "Every Monday at 8:00 AM (Europe/Amsterdam)",
  prompt: `You are reviewing the household investment strategy for Giannis and Aliki.

Context:
- Current date: {current_date}
- Household location/tax context: Netherlands now, planned Greece move in Q4 2029.
- Combined monthly savings/investment capacity: €3,600/month, split €1,800 Giannis and €1,800 Aliki.
- Strategic objective: maximize expected household capital in a reasonable way while preserving at least €150,000 safe Greece relocation capital by Q4 2029.
- Current base plan is asymmetric:
  - Giannis is the growth engine.
  - Aliki is the safety/liquidity engine.
  - Aliki uses only ABN and IBKR. Do not recommend Trade Republic, bunq, Lightyear, Revolut, or other tools for Aliki.
- Wedding savings are ring-fenced and must not be used for either investment plan.
- Changing course requires high conviction and evidence. Default answer should be GREEN LIGHT / proceed as is unless evidence clearly supports a change.

Current Giannis monthly plan:
- XEON: €600
- IBGS: €200
- VUAA: €400
- VWCE: €200
- XAIX: €125
- RBOT: €100
- Cybersecurity UCITS ETF: €75
- Defence UCITS ETF: €50
- India UCITS ETF: €50
- Total: €1,800

Current Aliki starting plan:
- Keep €33,419 in ABN savings.
- Transfer €10,000 to IBKR:
  - VWCE: €4,000
  - XEON: €4,000
  - IBGS: €2,000

Current Aliki monthly plan:
- ABN savings: €950
- XEON in IBKR: €300
- IBGS in IBKR: €200
- VWCE in IBKR: €350
- Total: €1,800

Your tasks:
1. Use Syllogic as the primary source for current portfolio holdings, balances, prices, and recurring investments. If Syllogic is unavailable, ask for a current pasted portfolio snapshot and clearly state that live portfolio validation could not be completed.
2. Search current prices and market data for all portfolio instruments and proposed ETFs.
3. Search recent news and authoritative market commentary for:
   - AI capex and hyperscaler spending
   - semiconductor and Taiwan / China risk
   - Middle East energy and shipping risk
   - European defence / NATO / EU defence spending
   - cybersecurity and AI-security risk
   - ECB rates, euro inflation, and cash/money-market yields
   - India growth and valuation signals
4. Recompute:
   - Current household allocation by asset class
   - Giannis and Aliki safe-bucket progress versus the Q4 2029 €150,000 household target
   - Single-stock concentration
   - AI / semiconductor / thematic concentration
   - Estimated downside sensitivity under at least five scenarios: base case, AI capex disappointment, Taiwan/chip shock, Middle East energy shock, and rates/inflation shock
5. Apply the change-control rule:
   - Do not recommend a strategy change unless there are at least three independent high-quality sources or a hard portfolio guardrail breach.
   - A single headline is not enough.
   - Short-term price movement alone is not enough.
   - A recommendation to change must quantify the risk or opportunity and explain why the original strategy is no longer sufficient.
6. Output one of:
   - GREEN LIGHT: proceed as is.
   - AMBER: keep strategy but monitor specific risks.
   - RED: change required now.
7. If AMBER or RED, provide exact proposed changes in euros per month, not just percentages.
8. Always include a final table with:
   - Current strategy
   - Evidence reviewed
   - Risk status
   - Recommended action
   - Confidence level

Important:
- This is research and analysis only, not financial advice.
- Prefer doing nothing unless evidence is strong.
- Preserve the household objective: at least €150,000 safe Greece relocation capital by Q4 2029 plus lifetime investments.`,
};

export const ALL_TEMPLATES: RoutineTemplate[] = [INVESTMENT_REVIEW_TEMPLATE];
