import { Section, Text } from "@react-email/components";

type Item = {
  severity: "info" | "monitor" | "act_now";
  title: string;
  rationale: string;
  proposedChange: string | null;
};

const SEV: Record<Item["severity"], string> = {
  info: "#6B7280",
  monitor: "#F59E0B",
  act_now: "#EF4444",
};

export function RecommendationItems({ items }: { items: Item[] }) {
  if (items.length === 0) return null;
  return (
    <Section style={{ marginBottom: "16px" }}>
      <Text style={{ fontSize: "16px", fontWeight: 600 }}>Recommendations</Text>
      {items.map((r, i) => (
        <div
          key={i}
          style={{ borderLeft: `4px solid ${SEV[r.severity]}`, padding: "8px 12px", marginBottom: "8px" }}
        >
          <div style={{ fontWeight: 600 }}>{r.title}</div>
          <div style={{ fontSize: "14px", marginTop: "4px" }}>{r.rationale}</div>
          {r.proposedChange !== null && (
            <div style={{ fontSize: "14px", marginTop: "4px", color: "#333" }}>
              <strong>Proposed change:</strong> {r.proposedChange}
            </div>
          )}
        </div>
      ))}
    </Section>
  );
}
