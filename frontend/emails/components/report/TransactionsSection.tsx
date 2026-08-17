import { Column, Row, Section, Text } from "@react-email/components";
import { fmtMoney, light } from "./tokens";

export type TransactionItem = {
  description: string;
  date: string;
  amount: string;
  currency: string;
  direction: "in" | "out";
};

export function TransactionsSection({ modeLabel, items }: { modeLabel: string; items: TransactionItem[] }) {
  return (
    <Section style={{ padding: "26px 28px 0" }}>
      <Text className="sy-muted" style={{ fontSize: "10px", letterSpacing: "0.14em", textTransform: "uppercase", color: light.mutedForeground, margin: "0 0 10px" }}>
        {modeLabel}
      </Text>
      {items.length === 0 ? (
        <Text className="sy-muted" style={{ fontSize: "12px", color: light.mutedForeground, margin: 0, padding: "12px 0" }}>
          No transactions in this period.
        </Text>
      ) : (
        items.map((t, i) => (
          <Row
            key={`${t.description}-${i}`}
            className="sy-rule"
            style={{ borderTop: i === 0 ? `1px solid ${light.border}` : undefined, borderBottom: `1px solid ${light.border}` }}
          >
            <Column style={{ padding: "11px 0" }}>
              <Text className="sy-fg" style={{ fontSize: "13px", color: light.foreground, margin: 0 }}>
                {t.description}
              </Text>
              <Text className="sy-muted" style={{ fontSize: "11px", color: light.mutedForeground, margin: "2px 0 0" }}>
                {t.date}
              </Text>
            </Column>
            <Column style={{ padding: "11px 0", textAlign: "right", whiteSpace: "nowrap" }}>
              {/* No success token exists in the design system, so inflows use
                  --foreground rather than a green. */}
              <Text
                className={t.direction === "out" ? "sy-out" : "sy-fg"}
                style={{ fontSize: "13px", fontWeight: 600, margin: 0, color: t.direction === "out" ? light.destructive : light.foreground }}
              >
                {t.direction === "out" ? "−" : "+"}
                {fmtMoney(t.amount, t.currency)}
              </Text>
            </Column>
          </Row>
        ))
      )}
    </Section>
  );
}
