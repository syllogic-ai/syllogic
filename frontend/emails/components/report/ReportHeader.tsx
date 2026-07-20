import { Section, Text } from "@react-email/components";
import { light } from "./tokens";

export function ReportHeader({
  reportName,
  periodLabel,
  generatedAt,
}: {
  reportName: string;
  periodLabel: string;
  generatedAt: string;
}) {
  const formatted = new Date(generatedAt).toLocaleDateString("en-GB", {
    day: "2-digit",
    month: "short",
    year: "numeric",
  });
  return (
    <Section style={{ padding: "28px 28px 0" }}>
      <Text className="sy-muted" style={{ fontSize: "10px", letterSpacing: "0.18em", textTransform: "uppercase", color: light.mutedForeground, margin: 0 }}>
        Syllogic
      </Text>
      <Text className="sy-fg" style={{ fontSize: "22px", fontWeight: 700, color: light.foreground, margin: "10px 0 0", lineHeight: 1.25 }}>
        {reportName}
      </Text>
      <Text className="sy-muted" style={{ fontSize: "12px", color: light.mutedForeground, margin: "6px 0 0" }}>
        {periodLabel} · {formatted}
      </Text>
    </Section>
  );
}
