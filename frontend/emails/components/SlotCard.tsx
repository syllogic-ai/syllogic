import { Section, Text } from "@react-email/components";

export function PinnedSlotCard({
  p,
}: {
  p: {
    symbol: string;
    verdict: string;
    rationale: string;
    allocatedAmount: number;
    riskFlags: string[];
  };
}) {
  const colors: Record<string, string> = {
    keep: "#10B981",
    monitor: "#3B82F6",
    reduce: "#F59E0B",
    replace: "#EF4444",
  };
  return (
    <Section
      style={{
        borderLeft: `4px solid ${colors[p.verdict] ?? "#999"}`,
        padding: "8px 12px",
        marginBottom: "8px",
      }}
    >
      <Text style={{ fontWeight: 600, margin: 0 }}>
        {p.symbol} — {p.verdict.toUpperCase()} ({p.allocatedAmount.toLocaleString()})
      </Text>
      <Text style={{ fontSize: "14px", margin: "4px 0" }}>{p.rationale}</Text>
      {p.riskFlags.length > 0 && (
        <Text style={{ fontSize: "12px", color: "#a16207", margin: 0 }}>
          Risk: {p.riskFlags.join(" · ")}
        </Text>
      )}
    </Section>
  );
}

export function DiscretionarySlotCard({
  d,
}: {
  d: {
    theme: string;
    allocatedAmount: number;
    topPicks: { rank: number; symbol: string; name: string; rationale: string }[];
  };
}) {
  const visible = d.topPicks.slice(0, 3);
  return (
    <Section
      style={{
        borderLeft: "4px solid #6366F1",
        padding: "8px 12px",
        marginBottom: "8px",
      }}
    >
      <Text style={{ fontWeight: 600, margin: 0 }}>
        {d.theme} — {d.allocatedAmount.toLocaleString()}
      </Text>
      {visible.map((p) => (
        <Text key={p.rank} style={{ fontSize: "14px", margin: "4px 0" }}>
          <strong>
            #{p.rank} {p.symbol}
          </strong>{" "}
          ({p.name}) — {p.rationale}
        </Text>
      ))}
    </Section>
  );
}
