import { Body, Container, Head, Html, Preview, Section, Text } from "@react-email/components";
import type { InvestmentPlanOutput } from "@/lib/investment-plans/schema";
import { SuggestedBuysTable } from "./components/SuggestedBuysTable";
import { PinnedSlotCard, DiscretionarySlotCard } from "./components/SlotCard";
import { IdleCashCallout } from "./components/IdleCashCallout";
import { EvidenceList } from "./components/EvidenceList";

export function InvestmentPlanMonthly({
  output,
  runUrl,
  monthLabel,
}: {
  output: InvestmentPlanOutput;
  runUrl?: string;
  monthLabel: string;
}) {
  const buyCount = output.monthlyAction.proposedBuys.length;
  return (
    <Html>
      <Head />
      <Preview>{`${buyCount} suggested buys for ${monthLabel}`}</Preview>
      <Body style={{ background: "#f5f5f5", fontFamily: "-apple-system,BlinkMacSystemFont,sans-serif" }}>
        <Container style={{ background: "#fff", maxWidth: 640, margin: "0 auto", padding: "24px" }}>
          <Section style={{ marginBottom: "16px" }}>
            <Text style={{ fontSize: "20px", fontWeight: 600, margin: 0 }}>
              Investment plan — {monthLabel}
            </Text>
            <Text style={{ fontSize: "14px", color: "#666", margin: "4px 0 0 0" }}>
              {buyCount} suggested {buyCount === 1 ? "buy" : "buys"} totaling{" "}
              {output.totalMonthly.toLocaleString()} {output.currency}
            </Text>
          </Section>

          <SuggestedBuysTable buys={output.monthlyAction.proposedBuys} currency={output.currency} />

          {output.monthlyAction.idleCashNudge && (
            <IdleCashCallout nudge={output.monthlyAction.idleCashNudge} />
          )}

          {output.pinned.length > 0 && (
            <Section style={{ marginBottom: "16px" }}>
              <Text style={{ fontSize: "16px", fontWeight: 600 }}>Pinned slots</Text>
              {output.pinned.map((p) => (
                <PinnedSlotCard key={p.slotId} p={p} />
              ))}
            </Section>
          )}

          {output.discretionary.length > 0 && (
            <Section style={{ marginBottom: "16px" }}>
              <Text style={{ fontSize: "16px", fontWeight: 600 }}>Discretionary slots</Text>
              {output.discretionary.map((d) => (
                <DiscretionarySlotCard key={d.slotId} d={d} />
              ))}
            </Section>
          )}

          <EvidenceList items={output.evidence} />

          {runUrl && (
            <Section style={{ marginTop: "24px", borderTop: "1px solid #ddd", paddingTop: "12px" }}>
              <Text style={{ fontSize: "12px", color: "#888" }}>
                <a href={runUrl}>View full report online</a> · Research and analysis only, not
                financial advice.
              </Text>
            </Section>
          )}
        </Container>
      </Body>
    </Html>
  );
}
