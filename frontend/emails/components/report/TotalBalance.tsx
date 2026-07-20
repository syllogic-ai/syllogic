import { Section, Text } from "@react-email/components";
import { fmtMoney, light } from "./tokens";

/**
 * Withheld entirely when the backend could not produce a single-currency
 * total, rather than showing a number that silently mixes currencies.
 */
export function TotalBalance({ amount, currency }: { amount: string | null; currency: string }) {
  if (!amount) return null;
  return (
    <Section style={{ padding: "22px 28px 0" }}>
      <Section className="sy-chip" style={{ backgroundColor: light.muted, padding: "18px 20px", width: "100%" }}>
        <Text className="sy-muted" style={{ fontSize: "10px", letterSpacing: "0.14em", textTransform: "uppercase", color: light.mutedForeground, margin: 0 }}>
          TOTAL BALANCE
        </Text>
        <Text className="sy-fg" style={{ fontSize: "28px", fontWeight: 700, color: light.foreground, margin: "6px 0 0", letterSpacing: "-0.02em" }}>
          {fmtMoney(amount, currency)}
        </Text>
      </Section>
    </Section>
  );
}
