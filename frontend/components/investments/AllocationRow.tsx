import { Card, CardContent, CardHeader } from "@/components/ui/card";
import {
  AllocationDonut,
  DONUT_PALETTE,
  type DonutSegment,
} from "./AllocationDonut";

function toSegments(data: Record<string, string | number>): DonutSegment[] {
  const entries = Object.entries(data);
  const total = entries.reduce((s, [, v]) => s + Number(v), 0) || 1;
  return entries.map(([label, v], i) => ({
    label,
    pct: Math.round((Number(v) / total) * 100),
    color: DONUT_PALETTE[i % DONUT_PALETTE.length],
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
    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
      {groups.map((g) => (
        <Card key={g.title}>
          <CardHeader>
            <h3 className="text-sm font-semibold">{g.title}</h3>
          </CardHeader>
          <CardContent className="flex items-center gap-5">
            <AllocationDonut segments={g.segs} size={72} />
            <div className="flex-1 flex flex-col gap-1.5">
              {g.segs.map((s, i) => (
                <div
                  key={i}
                  className="flex items-center gap-2 text-xs"
                >
                  <span
                    className="w-2 h-2 flex-shrink-0"
                    style={{ background: s.color }}
                  />
                  <span className="flex-1 text-muted-foreground">
                    {s.label}
                  </span>
                  <span className="font-semibold tabular-nums">{s.pct}%</span>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      ))}
    </div>
  );
}
