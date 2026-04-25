import { AllocationDonut, type DonutSegment } from "./AllocationDonut";
import { T } from "./_tokens";

const PALETTE = [T.chart1, T.chart2, T.chart3];

function toSegments(data: Record<string, string | number>): DonutSegment[] {
  const entries = Object.entries(data);
  const total = entries.reduce((s, [, v]) => s + Number(v), 0) || 1;
  return entries.map(([label, v], i) => ({
    label,
    pct: Math.round((Number(v) / total) * 100),
    color: PALETTE[i % PALETTE.length],
  }));
}

export function AllocationRow({
  byInstrument,
  byCurrency,
}: {
  byInstrument: Record<string, string>;
  byCurrency: Record<string, string>;
}) {
  const groups = [
    { title: "By instrument", segs: toSegments(byInstrument) },
    { title: "By currency", segs: toSegments(byCurrency) },
  ];
  return (
    <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
      {groups.map((g, gi) => (
        <div
          key={gi}
          style={{
            background: T.card,
            border: `1px solid ${T.border}`,
            padding: 18,
            display: "flex",
            gap: 20,
            alignItems: "center",
          }}
        >
          <AllocationDonut segments={g.segs} size={72} />
          <div style={{ flex: 1 }}>
            <div style={{ fontSize: 11, fontWeight: 600, marginBottom: 10 }}>
              {g.title}
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: 5 }}>
              {g.segs.map((s, i) => (
                <div
                  key={i}
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: 8,
                    fontSize: 11,
                  }}
                >
                  <span
                    style={{
                      width: 8,
                      height: 8,
                      background: s.color,
                      flexShrink: 0,
                    }}
                  />
                  <span style={{ flex: 1, color: T.mutedFg }}>{s.label}</span>
                  <span
                    style={{
                      fontWeight: 600,
                      fontVariantNumeric: "tabular-nums",
                    }}
                  >
                    {s.pct}%
                  </span>
                </div>
              ))}
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}
