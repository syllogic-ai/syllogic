import { Section, Text } from "@react-email/components";

const COLORS = {
  GREEN: { bg: "#10B981", emoji: "🟢" },
  AMBER: { bg: "#F59E0B", emoji: "🟡" },
  RED: { bg: "#EF4444", emoji: "🔴" },
};

export function StatusBanner({ status, headline }: { status: "GREEN" | "AMBER" | "RED"; headline: string }) {
  const c = COLORS[status];
  return (
    <Section style={{ background: c.bg, padding: "20px", borderRadius: "8px", marginBottom: "16px" }}>
      <Text style={{ color: "#fff", fontSize: "20px", fontWeight: 600, margin: 0 }}>
        {c.emoji}  {status}: {headline}
      </Text>
    </Section>
  );
}
