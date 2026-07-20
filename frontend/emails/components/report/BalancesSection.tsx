import { Column, Img, Row, Section, Text } from "@react-email/components";
import { fmtMoney, light } from "./tokens";

export type BalanceItem = {
  name: string;
  institution: string | null;
  balance: string;
  currency: string;
  logoUrl: string | null;
};

export function BalancesSection({ accounts }: { accounts: BalanceItem[] }) {
  if (accounts.length === 0) return null;
  return (
    <Section style={{ padding: "26px 28px 0" }}>
      <Text className="sy-muted" style={{ fontSize: "10px", letterSpacing: "0.14em", textTransform: "uppercase", color: light.mutedForeground, margin: "0 0 10px" }}>
        Accounts
      </Text>
      {accounts.map((a, i) => (
        <Row
          key={`${a.name}-${i}`}
          className="sy-rule"
          style={{ borderTop: i === 0 ? `1px solid ${light.border}` : undefined, borderBottom: `1px solid ${light.border}` }}
        >
          <Column style={{ width: "34px", padding: "12px 0" }}>
            {a.logoUrl ? (
              <Img
                src={a.logoUrl}
                width="26"
                height="26"
                alt={a.institution ?? a.name}
                className="sy-logo"
                style={{ display: "block", border: `1px solid ${light.border}`, backgroundColor: light.background }}
              />
            ) : (
              <Section className="sy-chip" style={{ width: "26px", height: "26px", backgroundColor: light.muted, border: `1px solid ${light.border}` }}>
                <Text className="sy-muted" style={{ fontSize: "11px", color: light.mutedForeground, margin: 0, textAlign: "center", lineHeight: "24px" }}>
                  {a.name.charAt(0).toUpperCase()}
                </Text>
              </Section>
            )}
          </Column>
          <Column style={{ padding: "12px 0 12px 12px" }}>
            <Text className="sy-fg" style={{ fontSize: "13px", fontWeight: 500, color: light.foreground, margin: 0 }}>
              {a.name}
            </Text>
            {a.institution && (
              <Text className="sy-muted" style={{ fontSize: "11px", color: light.mutedForeground, margin: "2px 0 0" }}>
                {a.institution}
              </Text>
            )}
          </Column>
          <Column style={{ padding: "12px 0", textAlign: "right", whiteSpace: "nowrap" }}>
            <Text className="sy-fg" style={{ fontSize: "13px", fontWeight: 600, color: light.foreground, margin: 0 }}>
              {fmtMoney(a.balance, a.currency)}
            </Text>
          </Column>
        </Row>
      ))}
    </Section>
  );
}
