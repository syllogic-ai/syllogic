export type DonutSegment = { label: string; pct: number; color: string };

export const DONUT_PALETTE = [
  "var(--chart-1)",
  "var(--chart-2)",
  "var(--chart-3)",
  "var(--chart-4)",
  "var(--chart-5)",
];

export function AllocationDonut({
  segments,
  size = 72,
}: {
  segments: DonutSegment[];
  size?: number;
}) {
  const r = 28;
  const cx = 40;
  const cy = 40;
  const C = 2 * Math.PI * r;
  const cumulative = segments.reduce<number[]>((arr, s) => {
    arr.push((arr[arr.length - 1] ?? 0) + s.pct);
    return arr;
  }, []);
  const segs = segments.map((s, i) => ({
    color: s.color,
    dash: (s.pct / 100) * C,
    offset: -((cumulative[i - 1] ?? 0) / 100) * C,
  }));
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 80 80"
      className="text-muted-foreground/30"
    >
      <circle
        cx={cx}
        cy={cy}
        r={r}
        fill="none"
        stroke="var(--border)"
        strokeWidth="12"
      />
      {segs.map((s, i) => {
        return (
          <circle
            key={i}
            cx={cx}
            cy={cy}
            r={r}
            fill="none"
            stroke={s.color}
            strokeWidth="12"
            strokeDasharray={`${s.dash} ${C}`}
            strokeDashoffset={s.offset}
            transform="rotate(-90 40 40)"
          />
        );
      })}
    </svg>
  );
}
