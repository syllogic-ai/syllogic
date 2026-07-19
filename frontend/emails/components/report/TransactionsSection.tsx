import { Section, Text } from "@react-email/components";

export type TransactionItem = {
  description: string;
  category: string | null;
  date: string;
  amount: string;
  currency: string;
  direction: "in" | "out";
};

export function TransactionsSection({ modeLabel, items }: { modeLabel: string; items: TransactionItem[] }) {
  return (
    <Section style={{ padding: "8px 20px 24px" }}>
      <Text style={{ fontSize: "12px", fontWeight: 600, color: "#6B7280", textTransform: "uppercase", margin: "0 0 8px" }}>
        {modeLabel}
      </Text>
      {items.length === 0 ? (
        <Text style={{ fontSize: "13px", color: "#6B7280" }}>No transactions to show.</Text>
      ) : (
        items.map((t, i) => (
          <Section
            key={`${t.description}-${t.date}-${i}`}
            style={{
              borderBottom: "1px solid #E5E7EB",
              padding: "10px 0",
              width: "100%",
            }}
          >
            <Text style={{ fontSize: "14px", color: "#111827", margin: 0, fontWeight: 500 }}>{t.description}</Text>
            <Text style={{ fontSize: "12px", color: "#6B7280", margin: "2px 0 0" }}>
              {t.date}
              {t.category ? ` · ${t.category}` : ""}
            </Text>
            <Text
              style={{
                fontSize: "14px",
                fontWeight: 600,
                margin: "4px 0 0",
                color: t.direction === "out" ? "#EF4444" : "#10B981",
              }}
            >
              {t.direction === "out" ? "-" : "+"}
              {t.amount} {t.currency}
            </Text>
          </Section>
        ))
      )}
    </Section>
  );
}
