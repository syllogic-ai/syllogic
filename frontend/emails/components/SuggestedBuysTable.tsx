import { Section, Text } from "@react-email/components";

type Buy = { symbol: string; amount: number; source: "pinned" | "discretionary" };

export function SuggestedBuysTable({ buys, currency }: { buys: Buy[]; currency: string }) {
  if (buys.length === 0) return null;
  return (
    <Section style={{ marginBottom: "16px" }}>
      <Text style={{ fontSize: "16px", fontWeight: 600 }}>Suggested buys this month</Text>
      <table cellPadding={6} style={{ width: "100%", borderCollapse: "collapse", fontSize: "14px" }}>
        <thead>
          <tr style={{ borderBottom: "1px solid #ddd", textAlign: "left" }}>
            <th>Symbol</th>
            <th>Amount</th>
            <th>Source</th>
          </tr>
        </thead>
        <tbody>
          {buys.map((b, i) => (
            <tr key={i} style={{ borderBottom: "1px solid #eee" }}>
              <td>
                <strong>{b.symbol}</strong>
              </td>
              <td>
                {b.amount.toLocaleString()} {currency}
              </td>
              <td style={{ color: "#666" }}>{b.source}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </Section>
  );
}
