"use client";

export function PortfolioChart({
  data,
  currencySymbol,
}: {
  data: number[];
  currencySymbol: string;
}) {
  if (data.length < 2) {
    return (
      <div className="h-[180px] flex items-center justify-center text-xs text-muted-foreground">
        Not enough history
      </div>
    );
  }
  const min = Math.min(...data);
  const max = Math.max(...data);
  const pad = (max - min) * 0.12 || 1;
  const lo = min - pad;
  const hi = max + pad;
  const W = 800;
  const H = 160;
  const toY = (v: number) => H - ((v - lo) / (hi - lo)) * H;
  const toX = (i: number, len: number) => (i / (len - 1)) * W;
  const pts = data.map((v, i) => [toX(i, data.length), toY(v)] as const);
  const linePath = pts
    .map((p, i) => `${i === 0 ? "M" : "L"}${p[0].toFixed(1)},${p[1].toFixed(1)}`)
    .join(" ");
  const areaPath = `${linePath} L${W},${H} L0,${H} Z`;
  const yTicks = [0.25, 0.5, 0.75].map((f) => lo + (hi - lo) * f);
  const lastX = toX(data.length - 1, data.length);
  const lastY = toY(data[data.length - 1]);

  return (
    <svg
      viewBox={`-44 -4 ${W + 52} ${H + 24}`}
      className="w-full h-[180px] block"
      preserveAspectRatio="none"
    >
      <defs>
        <linearGradient id="invAreaGrad" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="var(--primary)" stopOpacity="0.12" />
          <stop offset="100%" stopColor="var(--primary)" stopOpacity="0" />
        </linearGradient>
      </defs>
      {yTicks.map((v, i) => (
        <line
          key={i}
          x1="0"
          y1={toY(v)}
          x2={W}
          y2={toY(v)}
          stroke="var(--border)"
          strokeWidth="1"
        />
      ))}
      {yTicks.map((v, i) => (
        <text
          key={i}
          x="-6"
          y={toY(v) + 4}
          textAnchor="end"
          fontSize="9"
          fill="var(--muted-foreground)"
        >
          {v >= 1000
            ? `${currencySymbol}${(v / 1000).toFixed(0)}k`
            : `${currencySymbol}${v.toFixed(0)}`}
        </text>
      ))}
      <path d={areaPath} fill="url(#invAreaGrad)" />
      <path
        d={linePath}
        fill="none"
        stroke="var(--primary)"
        strokeWidth="1.5"
        strokeLinecap="square"
        strokeLinejoin="miter"
      />
      <circle cx={lastX} cy={lastY} r="3.5" fill="var(--primary)" />
      <circle
        cx={lastX}
        cy={lastY}
        r="6"
        fill="var(--primary)"
        fillOpacity="0.2"
      />
    </svg>
  );
}
