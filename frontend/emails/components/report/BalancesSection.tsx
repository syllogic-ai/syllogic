import { Section, Text } from "@react-email/components";

export type BalanceItem = {
  name: string;
  institution: string | null;
  balance: string;
  currency: string;
};

export function BalancesSection({ accounts }: { accounts: BalanceItem[] }) {
  if (accounts.length === 0) return null;
  return (
    <Section style={{ padding: "8px 20px" }}>
      <Text style={{ fontSize: "12px", fontWeight: 600, color: "#6B7280", textTransform: "uppercase", margin: "0 0 8px" }}>
        Account Balances
      </Text>
      {accounts.map((a, index) => (
        <Section
          key={`${a.name}-${index}`}
          style={{
            background: "#F9FAFB",
            borderRadius: "8px",
            padding: "14px 16px",
            marginBottom: "8px",
            width: "100%",
          }}
        >
          <Text style={{ fontSize: "14px", fontWeight: 600, color: "#111827", margin: 0 }}>{a.name}</Text>
          {a.institution ? (
            <Text style={{ fontSize: "12px", color: "#6B7280", margin: "2px 0 6px" }}>{a.institution}</Text>
          ) : null}
          <Text style={{ fontSize: "18px", fontWeight: 700, color: "#111827", margin: 0 }}>
            {a.balance} {a.currency}
          </Text>
        </Section>
      ))}
    </Section>
  );
}
